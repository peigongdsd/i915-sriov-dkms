# `i915` SR-IOV Codeflow, With MTL / ARL Special Cases Called Out

## 1. Where Intel Put The SR-IOV Code

The old Intel `i915` SR-IOV line is easy to locate:

- `drivers/gpu/drm/i915/README.sriov`
- `drivers/gpu/drm/i915/i915_sriov.c`
- `drivers/gpu/drm/i915/gt/iov/*`

The `README.sriov` file makes the intended split explicit:

- `drm/i915/iov`
- `drm/i915/pf`
- `drm/i915/vf`

So the mental model is:

- common GT virtualization logic under `gt/iov`
- PF policy and provisioning around it
- VF bootstrap and recovery around it

## 2. The `i915` SR-IOV Lifecycle In One Pass

### 2.1 Early Mode Setup

Key file:

- `drivers/gpu/drm/i915/gt/iov/intel_iov.c`

Entry point:

- `intel_iov_init_early()`

What it does:

- on PF:
  - `intel_iov_provisioning_init_early()`
  - `intel_iov_service_init_early()`
  - `intel_iov_state_init_early()`
- on VF:
  - `intel_iov_ggtt_vf_init_early()`
- on both:
  - `intel_iov_relay_init_early()`

Interpretation:

- PF gets early provisioning, service, and state machinery.
- VF gets early GGTT virtualization state.
- relay support is fundamental enough to exist before later phases.

### 2.2 MMIO Bootstrap Query Phase

Key files:

- `drivers/gpu/drm/i915/gt/iov/intel_iov.c`
- `drivers/gpu/drm/i915/gt/iov/intel_iov_query.c`

Entry point:

- `intel_iov_init_mmio()`

VF flow:

1. `intel_iov_query_bootstrap()`
2. `intel_iov_query_config()`
3. `intel_iov_query_runtime(iov, true)`

The bootstrap phase in `intel_iov_query.c` is worth reading literally:

- `vf_reset_guc_state()`
- `vf_handshake_with_guc()`
- version negotiation through `GUC_ACTION_VF2GUC_MATCH_VERSION`

This is Intel's first statement of SR-IOV discipline:

- the VF does not assume a valid execution environment,
- it re-establishes GuC state and negotiates ABI first,
- then it pulls config and runtime KLV data.

### 2.3 Second-Stage VF Init

Still in `intel_iov_init()`:

- PF:
  - does initial provisioning partitioning
- VF:
  - re-queries bootstrap info
  - tweaks GuC submission limits with `vf_tweak_guc_submission()`
  - initializes memory interrupt support via `intel_iov_memirq_init()`

The second bootstrap query is not accidental. It reflects a careful model:

- config/runtime/bootstrap state is not assumed to stay valid across the early
  transition.

## 3. GGTT Virtualization In `i915`

This is the most MTL-sensitive part of the old `i915` SR-IOV path.

### 3.1 VF GGTT Space Is Ballooned, Not Shared

In `intel_iov.c`:

- `vf_balloon_ggtt()`
- `intel_iov_init_ggtt()`

The VF only gets its provisioned GGTT window:

- lower space ballooned away
- upper space ballooned away
- only assigned region remains usable

This is the normal SR-IOV isolation story.

### 3.2 PF Shadow/Binder Init Is Conditional And MTL-Relevant

Still in `intel_iov_init_ggtt()`:

- PF checks `i915_ggtt_require_binder(i915)`
- if true and the GT is not media, it initializes GGTT shadow state

That makes the MTL-specific workaround part of normal PF initialization rather
than a later emergency path.

### 3.3 VF GGTT Updates Can Be Switched To Relay

Key file:

- `drivers/gpu/drm/i915/gt/intel_ggtt.c`

Key behavior:

- `gen12vf_ggtt_probe()` checks `i915_ggtt_require_binder(i915)`
- if the binder workaround is needed:
  - VF GGTT insertion switches to relay-aware insertion functions
  - a debug message says:
    `VF update GGTT via VF2PF relay WA is enabled!`

This is the old `i915` MTL SR-IOV message in one sentence:

- direct VF GGTT programming is not the path Intel wanted to trust on MTL.

### 3.4 PF Runtime Service Shares Register State With VFs

Key file:

- `drivers/gpu/drm/i915/gt/iov/intel_iov_service.c`

Important data:

- `tgl_runtime_regs[]`
- `mtl_runtime_regs[]`

The MTL list is materially larger and includes MTL-specific registers such as:

- `CTC_MODE`
- `GEN9_TIMESTAMP_OVERRIDE`
- `0x10100C`
- `HECI_FWSTS5(MTL_GSC_HECI1_BASE)`
- `MTL_GT_ACTIVITY_FACTOR`
- `0x389140`
- `0x38C1DC`

The important point is not the exact count. It is the design:

- Intel did not expose "generic gen12 runtime state".
- Intel exposed an explicitly MTL-shaped runtime contract to VFs.

### 3.5 PF Updates Runtime State Actively

`intel_iov_service_update()`:

- optionally forcewakes media GT around `0x38c1dc`
- reads the runtime register set into PF-owned storage
- that storage becomes the VF-visible runtime snapshot

This is not passive. The PF is the authority for runtime register state that
the VF cannot access directly.

## 4. Hardware Init And Service Bring-Up

### 4.1 `intel_iov_init_hw()`

The hardware-init phase is where PF behavior becomes operational:

- PF can enable GGTT guest update support
- PF refreshes runtime service state
- PF updates/reset service state
- PF restarts provisioning/state service as needed

The function is the bridge between:

- "we know this is PF/VF"
- and
- "the virtualized hardware contract is actually active"

### 4.2 `intel_iov_notify_resfix_done()`

In `intel_iov_query.c`, `intel_iov_notify_resfix_done()` sends:

- `GUC_ACTION_VF2GUC_NOTIFY_RESFIX_DONE`

This is a small function with a big meaning:

- VF resource fixups are explicit state transitions,
- GuC must be told when they are complete,
- recovery is part of the documented control plane, not incidental.

## 5. Migration And Post-Migration Recovery In `i915`

The most readable explanation is in kernel-doc itself.

Key file:

- `drivers/gpu/drm/i915/i915_sriov.c`

Relevant kernel-doc blocks:

- `DOC: VM Migration with SR-IOV`
- `DOC: VF Post-migration worker`

This is not lightweight documentation. It describes a real recovery protocol.

### 5.1 The Recovery Story

The documented model is:

1. VF is paused and migrated.
2. On the new host, the VF driver starts on a fresh VF PCI function.
3. It can only talk to GuC over MMIO at first.
4. It waits for the PF/GuC migration handshake to finish.
5. It rebases GGTT and other address-dependent state.
6. It fixes queues, rings, and CT buffers.
7. It notifies GuC with `RESFIX_DONE`.
8. Only then does normal operation resume.

### 5.2 Why This Matters

This is one of the best illustrations of old `i915` SR-IOV maturity:

- migration is not just "save some config and continue"
- the driver documents and implements a full resynchronization story
- MMIO-only early communication, rebasing, and final notification are all
  first-class concepts

## 6. MTL / ARL Special Parts Inside `i915` SR-IOV

### 6.1 MTL Runtime Register Exposure

Commit:

- `drm/i915/iov: Expose early runtime registers for MTL`
- SHA noted during this study:
  `c031d1a2aaea6d9804a6a12af67b424642171836`

Code impact:

- `mtl_runtime_regs[]` in `intel_iov_service.c`

Meaning:

- MTL VFs needed an explicitly larger early runtime register contract.
- Intel did not treat TGL and MTL as equivalent here.

### 6.2 MTL GGTT Relay Workaround

Commit:

- `drm/i915/gt/iov: Add MTL WA for update VF GGTT via VF2PF relay`
- SHA noted during this study:
  `bcf6f14318c852a7319cf3ebeb0978432e314c0e`

Code impact:

- `i915_ggtt_require_binder()`
- VF insert-page / insert-entries redirection
- PF shadow/binder setup

Meaning:

- MTL needed a different GGTT update path, not just a different register table.

### 6.3 GuC Workaround Layer For MTL RCS/CCS

Relevant files:

- `drivers/gpu/drm/i915/gt/uc/intel_guc.c`
- `drivers/gpu/drm/i915/gt/uc/intel_guc_ads.c`
- `drivers/gpu/drm/i915/gt/uc/intel_guc_fwif.h`
- `drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c`

What `i915` adds for MTL:

- `GUC_WA_RCS_CCS_SWITCHOUT`
- ADS KLVs:
  - `GUC_WORKAROUND_KLV_SERIALIZED_RA_MODE`
  - `GUC_WORKAROUND_KLV_AVOID_GFX_CLEAR_WHILE_ACTIVE`
- hold-switchout treatment for render/compute paths on MTL generations

This is not core SR-IOV code, but it is still important:

- it changes the execution model around MTL render/compute scheduling,
- and SR-IOV VFs inherit that environment.

## 7. Cross-Reference: Which Local Commits Tried To Address Which MTL-Specific Deficiency

This section maps the MTL-specific `i915` special cases above to the later
local experiment lines documented in
[06-local-experiment-branch-ledger.md](./06-local-experiment-branch-ledger.md).

The question here is narrow:

- given a specific MTL-specific `i915` treatment,
- which local commits explicitly tried to make `xe` behave more like that
  treatment,
- and which commits only existed to observe whether that treatment gap was
  active?

### 7.1 MTL Runtime Register Exposure

The `i915` deficiency statement in this chapter is:

- MTL VFs need a larger early runtime-register contract than older platforms,
- PF must actively source and expose that contract,
- the VF cannot be left with only a generic runtime bucket.

Local commits that targeted that same deficiency directly:

- `2cfeee1` `xe: extend MTL runtime MMIO relay set`
  - early functional attempt to enlarge the MTL-visible runtime set.
- `e9377b5` `xe/sriov: use explicit MTL runtime regs list`
  - moved from a generic-bucket model toward an explicit MTL list.
- `9db9700` `xe/sriov: refresh runtime values on query`
  - addressed stale runtime values rather than only missing offsets.
- `48d7d5c` `xe/sriov: read runtime regs from owning GT`
  - addressed wrong-GT sourcing for runtime state on multi-GT MTL.
- `b2b8fdd` `xe/sriov: read runtime regs via MCR when needed`
  - addressed MTL/ARL registers that need MCR-aware access.
- `a700610` `xe/sriov: hold runtime PM during runtime queries`
  - addressed runtime-state collection while GT power state was unstable.
- `e526a6d` `xe/sriov: forcewake runtime register snapshot`
  - addressed runtime-state reads from gated registers.
- `7d1defd` `xe/sriov: retry VF MMIO handshake and runtime query`
  - addressed fragility in the VF-side query sequence.
- `333391e` `xe/sriov: fix VF MMIO relay request length/CRC`
  - addressed malformed VF query traffic, which prevented runtime exposure from
    being trustworthy.
- `90befe5` `drm/xe/sriov: mirror i915 MTL runtime register exposure`
  - the clean baseline commit that most directly mirrors the old `i915`
    MTL-specific contract.

Local logging commits that existed to detect this exact deficiency:

- `5301a2e` `xe: trace VF runtime MMIO relay offsets`
  - showed which runtime offsets the VF was actually requesting.
- `d1a5d2d` `xe: trace VF runtime query relay`
  - showed the VF query sequence end-to-end.
- `15028aa` `xe: track VF relay/MMIO handshake and opcode usage`
  - showed whether the handshake and runtime-query opcodes were even reaching
    the PF.
- `db91746` `xe/sriov: log runtime regs returned to VF`
  - showed the actual runtime values being exposed to the VF.
- `1a4aa7b` `xe/sriov: trace MTL runtime and MMIO service paths`
  - showed how MTL runtime service requests flowed on the PF side.

Cross-reference:

- the branch-family view of the same work is in Section 4 and Section 11 of
  [06-local-experiment-branch-ledger.md](./06-local-experiment-branch-ledger.md).

### 7.2 MTL GGTT Relay Workaround

The `i915` deficiency statement in this chapter is:

- on MTL, direct VF GGTT programming is not the trusted path,
- VF GGTT updates can be rerouted through a PF-mediated relay path,
- PF shadow/binder state becomes part of normal initialization.

Local commits that targeted that same deficiency directly:

- `70aa4bd` `xe: handle G2H MMIO relay service for SR-IOV`
  - established PF-side handling of MMIO relay traffic.
- `e90fba7` `xe: add VF2PF_UPDATE_GGTT32 relay support`
  - filled out the GGTT relay ABI itself.
- `297409f` `xe: defer VF GGTT invalidation out of G2H worker`
  - changed invalidation timing inside the relay-driven GGTT path.
- `a7543fa` `xe: pm-runtime guard deferred GGTT invalidate`
  - protected the deferred invalidation path.
- `581ea7a` / `4f7a59b` `xe/sriov: track PF shadow GGTT updates`
  - established PF shadow tracking, which is the local analogue to the PF
    binder/shadow idea.
- `ec0f9b9` `xe/sriov: use relay for steady-state VF GGTT updates`
  - moved steady-state GGTT traffic onto relay.
- `1dceebf` `xe/sriov: keep MMIO bootstrap and delay GGTT relay`
  - split bootstrap from steady-state relay activation.
- `996c7e6` `xe/sriov: use explicit MMIO GGTT bootstrap on MTL VF`
  - made bootstrap explicitly MTL-specific.
- `0a3545f` `xe/sriov: parse MMIO GGTT relay responses on MTL`
  - completed the MTL relay round trip.
- `4cee2b9` `xe/sriov: stage MTL PF GGTT apply through shadow`
  - tested whether PF shadow staging was the missing behavior.
- `e28ee35` `xe/sriov: bind MTL PF GGTT updates on copy engine`
  - tested an engine-bound PF apply model.
- `244bdbc` `xe/sriov: gate MTL bind-engine GGTT flush on relay`
  - tested whether relay readiness had to gate flush/commit timing.
- `d886462` `xe/sriov: arm MTL bind flush after VF bring-up`
  - delayed flush arming until later in VF life.
- `a917143` `xe/sriov: use upstream bind queue for MTL GGTT flush`
  - aligned queueing with upstream semantics.
- `6485483` `xe/sriov: defer MTL bind-ready notify until late VF init`
  - deferred readiness until the GGTT transport was further initialized.
- `0b67ed3` `xe/sriov: keep MTL VF GGTT updates on CPU apply`
  - tested CPU-side apply instead of more engine mediation.
- `89bdb7f` `xe/sriov: apply MTL VF GGTT shadow synchronously`
  - tested whether shadow application had to be synchronous.
- `6e27a95` `xe/sriov: keep MMIO bootstrap GGTT apply async`
  - tested a different sync policy for bootstrap.
- `d713541` `xe/sriov: use i915-like VF GGTT PTE coalescing`
  - directly tried to import one `i915`-like packet-shaping idea.
- `4c58eef` `xe/sriov: debug MTL PF GGTT with direct sync apply`
  - tested whether PF direct synchronous apply was closer to correct than the
    staged path.
- `c2e6132` `xe/sriov: debug negotiated MTL PF GGTT direct apply`
  - narrowed the direct-apply experiment.
- `b1936f5` `xe/sriov: try i915-style MTL PF direct GSM GGTT access`
  - directly tested one of the most literal `i915`-style PF access ideas.
- `5efe0aa` `xe/sriov: force literal MMIO GGTT bootstrap updates`
  - removed higher-level interpretation from bootstrap updates.
- `73c181b` `xe/sriov: force literal-only VF GGTT updates`
  - removed higher-level interpretation from VF-originating updates.
- `0e1e4e1` `xe/sriov: literalize PF MMIO bootstrap GGTT updates`
  - did the same on the PF bootstrap side.
- `42502ce` `xe/sriov: validate guc-backed GGTT invalidation`
  - tested whether invalidation belonged on the GuC-backed path instead.
- `9abcb52` `xe/sriov: force synchronous PF GGTT apply on MTL`
  - tested whether MTL required stricter PF-side apply ordering.
- `74549de` `xe/sriov: resanitize VF resources before FLR finish`
  - targeted the cleanup edge of the same transport/reset story.
- `168f20e` `Revert "xe/sriov: use i915-like VF GGTT PTE coalescing"`
  - recorded that the direct `i915`-like coalescing import was not kept in the
    clean baseline.

Local logging commits that existed to detect this exact deficiency:

- `4b38666` `xe/sriov: instrument MTL/ARL relay and VF MMIO paths`
  - exposed the MTL/ARL relay path itself.
- `0c9f8a4` / `dfc1a1d` `xe/sriov: unsuppress relay diagnostics`
  - made relay behavior visible enough to compare runs.
- `43633f8` `xe/sriov: trace deferred PF GGTT invalidation`
  - showed when deferred invalidation actually occurred.
- `6320862` `xe/sriov: trace overlapping PF GGTT update ranges`
  - exposed overlapping or conflicting PF update windows.
- `3f80cca` `xe/sriov: trace ggtt packet semantics`
  - made `xe` packet semantics visible.
- `eaf6b5d` `i915/iov: trace ggtt packet semantics`
  - provided the `i915` comparison point for the same packet semantics.
- `a05e5be` `i915/iov: trace ggtt flr ownership lifecycle`
  - provided the `i915` comparison point for reset/ownership sequencing.
- `2d9c528` `xe/sriov: verify staged shadow GGTT applies`
  - exposed whether shadow state really matched PF application.
- `17a5203` `xe/sriov: clarify synchronous GGTT validation log`
  - made the sync-apply experiment readable.

Cross-reference:

- the branch-family narrative is in Section 5 through Section 11 of
  [06-local-experiment-branch-ledger.md](./06-local-experiment-branch-ledger.md).

### 7.3 MTL GuC RCS/CCS Workaround Layer

The `i915` deficiency statement in this chapter is:

- MTL needs a distinct render/compute scheduling workaround layer,
- that layer includes explicit GuC WA bits and ADS KLVs,
- and the VF executes inside that environment even if the code is not labeled
  "SR-IOV core logic."

Local commits that targeted that same deficiency directly:

- `0526c5a` `xe/guc: add MTL RCS/CCS workaround path`
  - the direct functional experiment that imported the missing MTL GuC WA bit
    and ADS workaround KLVs into local `xe`.

Local logging commits that existed to detect this exact deficiency:

- `d4005e1` `xe/guc: log MTL workaround validation state`
  - showed:
    - which GuC WA flags were really set,
    - whether the suspected MTL ADS KLVs were emitted,
    - whether the local `xe` line was missing the same MTL workaround layer
      that `i915` carried.

Cross-reference:

- the later experiment-branch view is in Section 14.5 and Section 14.6 of
  [06-local-experiment-branch-ledger.md](./06-local-experiment-branch-ledger.md).

### 7.4 Recovery / Fixup Maturity Around MTL-Like VF Bring-Up

This chapter's migration discussion is not one single MTL-only deficiency, but
it still mattered to the local investigation because the old `i915` line treats
MMIO-first recovery, rebasing, and explicit `RESFIX_DONE` notification as a
first-class contract.

Local commits that targeted adjacent fixup/recovery gaps:

- `74549de` `xe/sriov: resanitize VF resources before FLR finish`
  - tried to tighten resource cleanup near reset completion.
- `0424d6d` `xe/sriov: log VF CCS metadata flow`
  - did not change recovery policy, but instrumented whether VF CCS
    save/restore-style state movement was active at all.

Local logging/support commits that existed to detect this exact deficiency:

- `e832066`, `5527108`, `46c1d51`
  - exposed VF FLR state and control-path sequencing.
- `0424d6d`
  - exposed VF CCS metadata save/restore activity.
- `1ef7555`
  - support commit needed to make the VF-CCS logging branch build.

Cross-reference:

- see Section 4, Section 10, and Section 14.7 of
  [06-local-experiment-branch-ledger.md](./06-local-experiment-branch-ledger.md).

## 8. What The `i915` Codeflow Says Overall

The old `i915` SR-IOV design says:

- PF is authoritative for provisioning, runtime state, and fixup sequencing.
- VF bootstrap is a negotiated, MMIO-first handshake with GuC.
- GGTT virtualization is isolated and can be rerouted through PF when the
  platform requires it.
- MTL is not a small tweak. It gets its own runtime-register exposure,
  GGTT-relay workaround, stolen-memory distrust, and scheduler workarounds.
