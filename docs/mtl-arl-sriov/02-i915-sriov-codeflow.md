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

## 7. What The `i915` Codeflow Says Overall

The old `i915` SR-IOV design says:

- PF is authoritative for provisioning, runtime state, and fixup sequencing.
- VF bootstrap is a negotiated, MMIO-first handshake with GuC.
- GGTT virtualization is isolated and can be rerouted through PF when the
  platform requires it.
- MTL is not a small tweak. It gets its own runtime-register exposure,
  GGTT-relay workaround, stolen-memory distrust, and scheduler workarounds.
