# Local Experiment Branch Ledger

This file is the local-experiment companion to:

- [01-platform-properties.md](./01-platform-properties.md)
- [02-i915-sriov-codeflow.md](./02-i915-sriov-codeflow.md)
- [03-xe-codeflow.md](./03-xe-codeflow.md)
- [04-i915-vs-xe-comparison.md](./04-i915-vs-xe-comparison.md)
- [05-upstream-commit-ledger.md](./05-upstream-commit-ledger.md)

Those files explain upstream code and Intel's own messages. This file explains
the later local branch work created by `peigongdsd`, grouped by branch line and
experiment intent.

The purpose here is not to restate the full patch diff. The purpose is to make
the local branch history readable as an investigation log:

- which branch line pursued which hypothesis,
- which commits were functional versus diagnostic,
- what each functional commit was trying to change in behavior,
- what each logging-only commit was designed to reveal.

## 1. Scope And Rules

Included here:

- branches and commits authored by `peigongdsd`,
- commits that changed runtime behavior,
- commits whose only job was to expose runtime state or dataflow.

Excluded or only noted briefly:

- docs-only commits,
- merge commits,
- trivial build-warning fixes unless they are required to understand a logging
  branch,
- generic repo maintenance unrelated to the investigation.

## 2. Classification Legend

### 2.1 Functional

A commit is classified as `functional` when it tries to alter driver behavior
in order to solve or narrow a bug.

Typical sub-intentions in this ledger:

- `bring-up`
  - enable a code path that did not exist before.
- `transport`
  - change how VF/PF state or GGTT updates move between sides.
- `synchronization`
  - change ordering, staging, invalidation, or ownership rules.
- `platform-policy`
  - apply an MTL-specific assumption from `i915` or upstream `xe`.
- `display/composition`
  - change final display-facing behavior.
- `guard`
  - reject a state that was hypothesized to be invalid.

### 2.2 Logging

A commit is classified as `logging` when it is intended to expose state without
changing the underlying policy. A logging commit may still slightly perturb
timing, but its intention is observational.

Typical sub-intentions in this ledger:

- `trace handshake`
  - show who talks to whom and with which opcode/offset.
- `trace ownership/state machine`
  - show GGTT, FLR, or VF state transitions.
- `trace dataflow`
  - show how PAT, scanout, or migration state propagates.
- `trace gatekeeping`
  - show whether a particular workaround or path really engaged.

## 3. Branch Families At A Glance

| Branch family | Main topic | Dominant intent |
|---|---|---|
| `wip/sriov-experiments`, early `master` | MMIO relay, runtime register query, FLR tracing | establish basic observability and fix VF/PF query plumbing |
| `3e70-6.19-buildfix` | early MTL GGTT invalidation experiments | test PF-side update/invalidate semantics |
| `upstream-mtl-boot` | MTL VF/PF GGTT transport bring-up | make MTL VF boot through bootstrap + relay + PF apply |
| `upstream-master-i915-trace` | reference instrumentation in `i915` | compare `xe` against `i915` packet and FLR semantics |
| `upstream-mtl-prebind` | prebind/coalescing/shadow timing | test whether packet shaping and sync policy are wrong |
| `upstream-mtl-pfdebug`, `upstream-mtl-pfdebug-postabi` | PF direct-apply and literal-update variants | test whether PF shadow/relay abstractions are the wrong layer |
| `upstream-mtl-shadowverify` | shadow/invalidate/FLR verification | validate staged-apply and cleanup assumptions |
| `upstream-mtl-cleanpath` | cleaned baseline after GGTT experiments | keep only judged-useful behavior, remove scaffolding |
| `bucketA-mtl-policy` | non-SR-IOV MTL memory-policy suspicions | test stolen-memory and pagetable-policy theories |
| `bucketA-mtl-composition` | display composition/scanout alignment | test display-side framebuffer alignment |
| `upstream-mtl-validate-*`, `upstream-mtl-flush-display`, `upstream-mtl-scanout-pat-guard`, `upstream-mtl-rcs-ccs-wa` | post-cleanpath targeted validation | test specific scanout, GuC WA, or VF-CCS theories |

## 4. Family A: `wip/sriov-experiments` And Early `master`

This is the first serious local investigation line. It precedes the cleaner
`upstream-mtl-*` branches and is more exploratory. It maps closely to the
runtime-register and relay-control phases described in
[02-i915-sriov-codeflow.md](./02-i915-sriov-codeflow.md) and
[03-xe-codeflow.md](./03-xe-codeflow.md).

### 4.1 Functional Commits

#### `ee32c8e` / `0bbf46a` `xe: enable MTL SR-IOV and handle GSC/PXP`

- Type: `functional / bring-up`
- Branch context:
  - early `master`
  - inherited into `upstream-mtl-boot`
- Intended problem:
  - MTL was not yet treated as a supported SR-IOV platform in the local `xe`
    line.
- Expected solve path:
  - enable MTL PF/VF support and handle MTL-specific GSC/PXP interaction during
    bring-up.
- Relation to the main study:
  - corresponds to the platform-gating and GSC treatment differences explained
    in [01-platform-properties.md](./01-platform-properties.md) and
    [03-xe-codeflow.md](./03-xe-codeflow.md).

#### `0286b13` / `e74cb07` `xe: hold GSC forcewake during MTL VF gating`

- Type: `functional / bring-up`
- Intended problem:
  - VF gating on MTL was suspected to be racing with GSC-managed state.
- Expected solve path:
  - keep the relevant GSC forcewake domain held while VF gating is performed.

#### `70aa4bd` `xe: handle G2H MMIO relay service for SR-IOV`

- Type: `functional / transport`
- Intended problem:
  - VF-to-PF MMIO relay service path was incomplete on the PF side.
- Expected solve path:
  - parse and service GuC-delivered MMIO relay requests instead of only logging
    or dropping them.

#### `9ecfc53` `xe: dispatch VF FLR across multi-GT`

- Type: `functional / synchronization`
- Intended problem:
  - FLR handling was too GT-local, while MTL exposes multiple GT slices that
    both need coherent VF reset handling.
- Expected solve path:
  - fan FLR work across GTs instead of assuming a single-GT ownership model.

#### `297409f` `xe: defer VF GGTT invalidation out of G2H worker`

- Type: `functional / synchronization`
- Intended problem:
  - GGTT invalidation was being executed too directly from the relay/G2H worker.
- Expected solve path:
  - defer invalidation to a safer context, reducing reentrancy and ordering
    hazards.

#### `a7543fa` `xe: pm-runtime guard deferred GGTT invalidate`

- Type: `functional / synchronization`
- Intended problem:
  - deferred invalidation could run without the required runtime-PM protection.
- Expected solve path:
  - add PM-runtime guarding around the deferred invalidate path.

#### `e90fba7` `xe: add VF2PF_UPDATE_GGTT32 relay support`

- Type: `functional / transport`
- Intended problem:
  - only part of the GGTT update ABI was handled; 32-bit update packets still
    needed support.
- Expected solve path:
  - complete the VF2PF GGTT relay ABI sufficiently for MTL VF traffic.

#### `2cfeee1` `xe: extend MTL runtime MMIO relay set`

- Type: `functional / platform-policy`
- Intended problem:
  - the VF-visible MTL runtime register set was incomplete.
- Expected solve path:
  - extend the relay-exposed runtime set so MTL VF queries stop seeing missing
    values for MTL-specific runtime registers.
- Cross-reference:
  - this is an earlier version of the later clean functional fix
    `90befe5`, which is discussed in Section 10 of this file and in
    [04-i915-vs-xe-comparison.md](./04-i915-vs-xe-comparison.md).

#### `e9377b5` `xe/sriov: use explicit MTL runtime regs list`

- Type: `functional / platform-policy`
- Intended problem:
  - the runtime-register exposure policy was too generic for MTL.
- Expected solve path:
  - stop inferring from broad graphics-version buckets and use an explicit MTL
    register list.

#### `7d1defd` `xe/sriov: retry VF MMIO handshake and runtime query`

- Type: `functional / transport`
- Intended problem:
  - VF runtime query handshake could fail transiently during early bring-up.
- Expected solve path:
  - add retry behavior rather than treating the first handshake failure as
    fatal.

#### `333391e` `xe/sriov: fix VF MMIO relay request length/CRC`

- Type: `functional / transport`
- Intended problem:
  - relay packets were malformed at the request encoding level.
- Expected solve path:
  - fix request length and CRC so VF runtime relay traffic becomes valid.

#### `9db9700` `xe/sriov: refresh runtime values on query`

- Type: `functional / platform-policy`
- Intended problem:
  - runtime query results were too static and could become stale.
- Expected solve path:
  - refresh values at query time instead of reusing old snapshots.

#### `a700610` `xe/sriov: hold runtime PM during runtime queries`

- Type: `functional / synchronization`
- Intended problem:
  - runtime queries could run while the owning GT was not held active.
- Expected solve path:
  - hold runtime PM for the duration of runtime-register collection.

#### `e526a6d` `xe/sriov: forcewake runtime register snapshot`

- Type: `functional / synchronization`
- Intended problem:
  - snapshots could read power-gated runtime registers incorrectly.
- Expected solve path:
  - forcewake around runtime-register capture.

#### `48d7d5c` `xe/sriov: read runtime regs from owning GT`

- Type: `functional / platform-policy`
- Intended problem:
  - multi-GT runtime registers were being read from the wrong GT context.
- Expected solve path:
  - read from the owning GT, matching the platform's GT topology.

#### `b2b8fdd` `xe/sriov: read runtime regs via MCR when needed`

- Type: `functional / platform-policy`
- Branch context:
  - tip of `wip/sriov-experiments`
- Intended problem:
  - some runtime registers on MTL/ARL need MCR-aware access rather than plain
    MMIO.
- Expected solve path:
  - use MCR access where required so runtime-register reads are directed at the
    correct GT instance.

#### `581ea7a` `xe/sriov: track PF shadow GGTT updates`

- Type: `functional / transport`
- Intended problem:
  - the PF needed a shadow view of VF GGTT state to reason about staged
    application and later invalidation.
- Expected solve path:
  - introduce or strengthen PF shadow tracking of GGTT updates.

### 4.2 Logging Commits

These commits mostly created the observability needed for the later
`upstream-mtl-*` lines.

#### GSC / relay visibility

- `b2e47b6` `[DEBUGMTLXE] add noisy SR-IOV GSC tracing`
  - Detects:
    - when MTL GSC-facing SR-IOV handling is entered,
    - whether GSC/PXP gating is involved in VF enablement.
- `0ced8bb` `xe: add relay failure tracing`
  - Detects:
    - relay failures and the context in which they occur.
- `d5baad2` `xe: relax relay ratelimit for debug`
  - Detects:
    - the same relay failures/events, but less aggressively suppressed.
- `4da991d` `xe: disable relay ratelimit for debug`
  - Detects:
    - full relay traffic/failure volume without rate limiting.
- `206f50b` `xe: trace relay requests at notice level`
  - Detects:
    - every relay request at visible log level.
- `5301a2e` `xe: trace VF runtime MMIO relay offsets`
  - Detects:
    - which exact MMIO offsets the VF is asking the PF to serve.
- `d1a5d2d` `xe: trace VF runtime query relay`
  - Detects:
    - the runtime-query relay sequence end to end.
- `15028aa` `xe: track VF relay/MMIO handshake and opcode usage`
  - Detects:
    - which opcodes and handshake phases are actually exercised.
- `402ea20` `xe: add PF relay trace debugfs`
  - Detects:
    - relay history through a PF-side debugfs view.
- `db91746` `xe/sriov: log runtime regs returned to VF`
  - Detects:
    - the actual values returned to the VF for runtime registers.
- `b4604d0` `xe/sriov: add detailed MMIO relay trace`
  - Detects:
    - detailed packet-level relay sequencing.
- `d3a94ab` `xe/sriov: refine relay trace telemetry`
  - Detects:
    - the same relay sequence, but in a more structured form.

#### FLR / GGTT / state-machine visibility

- `e832066` `[DEBUGMTLXE] add noisy PF VF-FLR state logging`
  - Detects:
    - PF view of VF FLR state transitions.
- `5527108` `[DEBUGMTLXE] log full VF FLR control path`
  - Detects:
    - the full FLR control path, not just the final state changes.
- `46c1d51` `[DEBUGMTLXE] add SR-IOV PF FLR state snapshots`
  - Detects:
    - state bitmasks/snapshots at key FLR transitions.

#### Cleanup of excessive noise

- `11d4dfb`, `65f83c7`, `8b9cc41`
  - Type: `logging cleanup`
  - Purpose:
    - remove earlier broad debug noise once more targeted tracing existed.

## 5. Family B: `3e70-6.19-buildfix`

This branch preserved the early runtime/MMIO work while pivoting into the first
direct PF GGTT invalidation experiments on the 6.19-forward-ported tree.

### 5.1 Functional Commits

#### `8022280` `xe/sriov: sanitize PF VF GGTT PTE updates`

- Type: `functional / synchronization`
- Intended problem:
  - PF-side application of VF GGTT PTE updates might be writing malformed or
    stale values.
- Expected solve path:
  - sanitize update values before they are applied.

#### `6f27264` `xe/sriov: test immediate PF GGTT invalidate on MTL`

- Type: `functional / synchronization`
- Intended problem:
  - deferred invalidation may have been too late for MTL VF correctness.
- Expected solve path:
  - invalidate PF-observed GGTT updates immediately.

### 5.2 Logging Commits

- `4b38666` `xe/sriov: instrument MTL/ARL relay and VF MMIO paths`
  - Detects:
    - where MTL/ARL-specific relay and VF MMIO paths diverge from generic flow.
- `0c9f8a4` / `dfc1a1d` `xe/sriov: unsuppress relay diagnostics`
  - Detects:
    - relay events that were previously hidden by suppression.
- `1a4aa7b` `xe/sriov: trace MTL runtime and MMIO service paths`
  - Detects:
    - runtime-register service flow and MMIO service routing on MTL.
- `43633f8` `xe/sriov: trace deferred PF GGTT invalidation`
  - Detects:
    - when deferred invalidation actually fires.
- `6320862` `xe/sriov: trace overlapping PF GGTT update ranges`
  - Detects:
    - overlapping or conflicting GGTT update ranges on the PF side.

### 5.3 Support / Cleanup

- `1ad2ed5` `display: forward-port 3e70 to drm_colorop on 6.19`
  - Not part of the SR-IOV theory itself.
  - It was a compatibility forward-port needed to keep the tree buildable.
- `c89f9e1` `xe/sriov: drop MTL runtime snapshot experiment`
  - Housekeeping:
    - remove a judged-bad experiment once targeted tracing existed.

## 6. Family C: `upstream-mtl-boot`

This is the first clean MTL SR-IOV bring-up line after the noisier exploratory
stage. It is the foundational branch for most later `upstream-mtl-*` work.

It maps directly to the GGTT virtualization and PF/VF transport phases in
[03-xe-codeflow.md](./03-xe-codeflow.md).

### 6.1 Functional Commits

#### `ec0f9b9` `xe/sriov: use relay for steady-state VF GGTT updates`

- Type: `functional / transport`
- Intended problem:
  - after initial bootstrap, VF GGTT updates still needed a stable steady-state
    transport.
- Expected solve path:
  - switch ongoing updates to relay service rather than bootstrap-only handling.

#### `1dceebf` `xe/sriov: keep MMIO bootstrap and delay GGTT relay`

- Type: `functional / transport`
- Intended problem:
  - relay was being activated too early in the VF life cycle.
- Expected solve path:
  - keep explicit bootstrap MMIO updates first, then enable relay later.

#### `996c7e6` `xe/sriov: use explicit MMIO GGTT bootstrap on MTL VF`

- Type: `functional / platform-policy`
- Intended problem:
  - MTL VF bootstrap needed an explicit MMIO GGTT path rather than generic
    assumptions.
- Expected solve path:
  - add MTL-specific bootstrap sender behavior on the VF side.

#### `0a3545f` `xe/sriov: parse MMIO GGTT relay responses on MTL`

- Type: `functional / transport`
- Intended problem:
  - MTL-specific relay responses were not being parsed/consumed correctly.
- Expected solve path:
  - parse relay responses so PF/VF GGTT synchronization becomes complete.

#### `4f7a59b` `xe/sriov: track MTL PF GGTT shadow updates`

- Type: `functional / transport`
- Intended problem:
  - PF shadow state for MTL GGTT updates needed explicit tracking.
- Expected solve path:
  - keep an MTL-aware shadow history of PF-side staged updates.

#### `13ce808` `xe/sriov: fix MTL PF GGTT shadow build regression`

- Type: `functional / support`
- Intended problem:
  - the prior shadow-tracking line introduced a build regression.
- Expected solve path:
  - repair the build while preserving the shadow path.

#### `4cee2b9` `xe/sriov: stage MTL PF GGTT apply through shadow`

- Type: `functional / synchronization`
- Intended problem:
  - PF update application needed a staged shadow layer rather than direct
    application.
- Expected solve path:
  - build and validate the update in shadow state before final PF apply.

#### `e28ee35` `xe/sriov: bind MTL PF GGTT updates on copy engine`

- Type: `functional / synchronization`
- Intended problem:
  - PF update application needed a dedicated engine-bound execution context.
- Expected solve path:
  - bind GGTT updates to the copy engine instead of looser execution.

#### `244bdbc` `xe/sriov: gate MTL bind-engine GGTT flush on relay`

- Type: `functional / synchronization`
- Intended problem:
  - PF-side bind-engine flush could race ahead of valid relay state.
- Expected solve path:
  - only flush when relay conditions indicate it is safe and meaningful.

#### `d886462` `xe/sriov: arm MTL bind flush after VF bring-up`

- Type: `functional / synchronization`
- Intended problem:
  - flush machinery was armed too early relative to VF readiness.
- Expected solve path:
  - delay armament until VF bring-up is complete.

#### `a917143` `xe/sriov: use upstream bind queue for MTL GGTT flush`

- Type: `functional / synchronization`
- Intended problem:
  - a local queueing path diverged from upstream queue semantics.
- Expected solve path:
  - reuse the upstream bind queue for MTL flush work.

#### `6485483` `xe/sriov: defer MTL bind-ready notify until late VF init`

- Type: `functional / synchronization`
- Intended problem:
  - the VF was being told "bind-ready" before GGTT transport was truly ready.
- Expected solve path:
  - move bind-ready notification later in VF initialization.

#### `0b67ed3` `xe/sriov: keep MTL VF GGTT updates on CPU apply`

- Type: `functional / synchronization`
- Intended problem:
  - engine-mediated application was suspected to be the wrong abstraction on
    MTL.
- Expected solve path:
  - keep GGTT application on the CPU side rather than pushing more of it into an
    engine path.

### 6.2 Logging Commits

- `0fb82b6` `xe/sriov: scope MTL GGTT path and log transitions`
  - Detects:
    - which phase is active:
      bootstrap, delayed relay, or steady-state relay.

## 7. Family D: `upstream-master-i915-trace`

This branch exists only to create a reference trace baseline in `i915`. It is
useful only in comparison with [02-i915-sriov-codeflow.md](./02-i915-sriov-codeflow.md)
and [04-i915-vs-xe-comparison.md](./04-i915-vs-xe-comparison.md).

### 7.1 Logging Commits

- `a05e5be` `i915/iov: trace ggtt flr ownership lifecycle`
  - Detects:
    - how `i915` moves FLR ownership and related GGTT control through the reset
      lifecycle.
- `eaf6b5d` `i915/iov: trace ggtt packet semantics`
  - Detects:
    - how `i915` interprets GGTT packets semantically.

These commits were not meant to fix `i915`. They were meant to provide
reference semantics for the later `xe` experiments.

## 8. Family E: `upstream-mtl-prebind`

This family asked whether the wrong behavior was in packet shaping, coalescing,
or sync/async staging policy rather than in the basic existence of the MTL
transport.

### 8.1 Functional Commits

#### `89bdb7f` `xe/sriov: apply MTL VF GGTT shadow synchronously`

- Type: `functional / synchronization`
- Intended problem:
  - asynchronous shadow application might allow stale or reordered GGTT state.
- Expected solve path:
  - apply the shadow synchronously.

#### `6e27a95` `xe/sriov: keep MMIO bootstrap GGTT apply async`

- Type: `functional / synchronization`
- Intended problem:
  - bootstrap and steady-state paths may require different sync policies.
- Expected solve path:
  - keep bootstrap asynchronous while other paths are examined separately.

#### `9374be0` `Revert "xe/sriov: keep MMIO bootstrap GGTT apply async"`

- Type: `functional / cleanup`
- Intended meaning:
  - the async bootstrap experiment did not look promising enough to keep.

#### `a229c16` `Revert "xe/sriov: apply MTL VF GGTT shadow synchronously"`

- Type: `functional / cleanup`
- Intended meaning:
  - likewise, the fully synchronous shadow-apply experiment was not retained as
    baseline policy.

#### `c9ff841` `xe/sriov: test MTL foundation GGTT paths`

- Type: `functional / platform-policy`
- Intended problem:
  - basic MTL GGTT assumptions were still too loose.
- Expected solve path:
  - reduce the system to a more explicit "foundation path" set for MTL GGTT.

#### `d713541` `xe/sriov: use i915-like VF GGTT PTE coalescing`

- Type: `functional / platform-policy`
- Intended problem:
  - VF GGTT PTE shaping in `xe` may have diverged from `i915` too far.
- Expected solve path:
  - mimic `i915`-style PTE coalescing to see whether the packet/update shape is
    the real issue.
- Later status:
  - eventually reverted in the cleanpath line by `168f20e`.

### 8.2 Logging Commits

- `9b39bc6` `xe/sriov: drop MTL no-op PTE sanitize experiment`
  - Mostly cleanup, but it records that an earlier no-op sanitize variant was
    judged unhelpful.
- `3f80cca` `xe/sriov: trace ggtt packet semantics`
  - Detects:
    - `xe` packet interpretation so it can be compared directly with the
      `i915` trace branch.

## 9. Family F: `upstream-mtl-pfdebug` And `upstream-mtl-pfdebug-postabi`

This family asked a narrower question: what if the PF shadow/relay stack itself
is the wrong layer, and MTL needs more literal PF-side application?

### 9.1 Functional Commits

#### `4c58eef` `xe/sriov: debug MTL PF GGTT with direct sync apply`

- Type: `functional / synchronization`
- Intended problem:
  - staged or deferred PF apply may be obscuring the real bug.
- Expected solve path:
  - apply GGTT updates directly and synchronously on the PF.

#### `c2e6132` `xe/sriov: debug negotiated MTL PF GGTT direct apply`

- Type: `functional / synchronization`
- Intended problem:
  - PF direct-apply might need to honor negotiated runtime conditions rather
    than being unconditional.
- Expected solve path:
  - keep direct PF apply, but under negotiated conditions.

#### `b1936f5` `xe/sriov: try i915-style MTL PF direct GSM GGTT access`

- Type: `functional / platform-policy`
- Intended problem:
  - PF GGTT access path on MTL might need to look more like `i915`'s direct GSM
    model.
- Expected solve path:
  - try direct GSM-based PF GGTT access.

#### `5efe0aa` `xe/sriov: force literal MMIO GGTT bootstrap updates`

- Type: `functional / transport`
- Intended problem:
  - higher-level abstractions around bootstrap updates might be mistranslating
    the actual MMIO intent.
- Expected solve path:
  - force literal MMIO bootstrap update handling.

## 10. Family G: `upstream-mtl-shadowverify`

This line kept the PF/literal/shadow experiments but tried to verify them more
strictly and reduce accidental ambiguity.

### 10.1 Functional Commits

#### `73c181b` `xe/sriov: force literal-only VF GGTT updates`

- Type: `functional / transport`
- Intended problem:
  - mixed update encodings on the VF side made it hard to know what the PF was
    really receiving.
- Expected solve path:
  - keep VF updates literal-only.

#### `0e1e4e1` `xe/sriov: literalize PF MMIO bootstrap GGTT updates`

- Type: `functional / transport`
- Intended problem:
  - the PF bootstrap path still had abstraction-induced ambiguity.
- Expected solve path:
  - mirror the VF-side literalization on the PF bootstrap path.

#### `42502ce` `xe/sriov: validate guc-backed GGTT invalidation`

- Type: `functional / synchronization`
- Intended problem:
  - perhaps GuC-backed invalidation, not CPU-side invalidation, was the missing
    piece.
- Expected solve path:
  - explicitly test a GuC-backed invalidation path.
- Later status:
  - rejected and undone by `395bdee`.

#### `395bdee` `xe/sriov: revert guc-backed GGTT invalidate experiment`

- Type: `functional / cleanup`
- Intended meaning:
  - the GuC-backed invalidate experiment was not retained as correct baseline.

#### `9abcb52` `xe/sriov: force synchronous PF GGTT apply on MTL`

- Type: `functional / synchronization`
- Intended problem:
  - PF update application on MTL still looked too asynchronous or reordered.
- Expected solve path:
  - make PF apply synchronous specifically on MTL.

#### `74549de` `xe/sriov: resanitize VF resources before FLR finish`

- Type: `functional / synchronization`
- Intended problem:
  - stale VF resources may survive too far into FLR completion.
- Expected solve path:
  - resanitize VF resources immediately before FLR finish.

### 10.2 Logging Commits

- `2d9c528` `xe/sriov: verify staged shadow GGTT applies`
  - Detects:
    - whether staged shadow GGTT state matches what the PF later applies.
- `25a89c7` `xe/sriov: reduce GGTT debug log noise`
  - Logging cleanup:
    - keep verification logs readable.
- `17a5203` `xe/sriov: clarify synchronous GGTT validation log`
  - Detects:
    - sync-apply timing more explicitly, not a new behavior change.

## 11. Family H: `upstream-mtl-cleanpath`

This branch is the post-GGTT cleanup baseline. It keeps the judged-useful parts
of the MTL bring-up line and removes scaffolding that was only useful during the
heaviest GGTT transport debugging.

### 11.1 Functional Commits

#### `168f20e` `Revert "xe/sriov: use i915-like VF GGTT PTE coalescing"`

- Type: `functional / cleanup`
- Intended meaning:
  - the `i915`-like PTE coalescing experiment was not judged good enough to
    remain in the clean baseline.

#### `90befe5` `drm/xe/sriov: mirror i915 MTL runtime register exposure`

- Type: `functional / platform-policy`
- Intended problem:
  - local cleanbase `xe` still under-exposed the MTL runtime register contract
    compared with Intel's old `i915` SR-IOV line.
- Expected solve path:
  - explicitly mirror the MTL runtime-register exposure that Intel's `i915`
    used.
- Cross-reference:
  - this is one of the clearest concrete gaps identified in
    [04-i915-vs-xe-comparison.md](./04-i915-vs-xe-comparison.md).

### 11.2 Logging / support commits

- `1d297d7` `xe/sriov: trim MTL GGTT validation scaffolding`
  - Logging cleanup:
    - remove heavy scaffolding once the clean baseline was selected.

## 12. Family I: `bucketA-mtl-policy`

This family is deliberately outside the narrow SR-IOV transport path. It tested
whether the bug belonged to a broader MTL memory-policy bucket already visible
in upstream `i915` and `xe`.

See [01-platform-properties.md](./01-platform-properties.md) and
[05-upstream-commit-ledger.md](./05-upstream-commit-ledger.md) for the upstream
motivation behind these guesses.

### 12.1 Functional Commits

#### `728d8fa` `xe/mtl: try i915-style direct DSMBASE stolen access`

- Type: `functional / platform-policy`
- Intended problem:
  - MTL stolen-memory access policy may have been wrong in the local `xe` line.
- Expected solve path:
  - use the more `i915`-like direct DSMBASE access model.

#### `01d3531` `xe/mtl: surface pagetable WC policy at runtime`

- Type: `functional / platform-policy`
- Intended problem:
  - missing MTL pagetable WC policy might underlie corruption.
- Expected solve path:
  - make the WC pagetable-policy path visible and active at runtime.

## 13. Family J: `bucketA-mtl-composition`

This branch shifted from low-level MTL memory policy to final display
composition.

### 13.1 Functional Commits

#### `a342f77` `xe/display: honor scanout fb alignment in GGTT pinning`

- Type: `functional / display/composition`
- Intended problem:
  - user scanout framebuffers might be pinned without respecting the alignment
    the display hardware expects.
- Expected solve path:
  - propagate framebuffer alignment into GGTT pinning so the scanout path is
    consistent with upstream `xe` alignment fixes.

## 14. Family K: Post-Cleanpath Validation Branches

These branches do not all share one theory. They all branch from the cleaner
baseline and test one narrow hypothesis at a time.

### 14.1 `upstream-mtl-validate-dataflow`

#### `5a03129` `xe: add validation logs for mtl display dataflow`

- Type: `logging / trace dataflow`
- Detects:
  - whether scanout BOs are already VM-bound before fb init,
  - whether the same BO later appears in the display pin path,
  - whether the `xe` frontbuffer display-flush hook is actually exercised.
- Why it mattered:
  - this is the branch that first exposed a real dataflow mismatch between
    scanout BO state and display pinning assumptions.

### 14.2 `upstream-mtl-validate-patflow`

#### `38100d9` `xe: trace scanout PAT state across bind and madvise`

- Type: `logging / trace dataflow`
- Detects:
  - PAT state on all VMAs associated with a scanout BO,
  - whether live PAT differs from default PAT,
  - whether divergence was caused by `VM_MADVISE` or by original bind layout.
- Why it mattered:
  - it proved that mixed PAT state on scanout BOs was an original bind-layout
    property, not a later mutation.

### 14.3 `upstream-mtl-flush-display`

#### `57eceee` `xe/display: add sysmem scanout flush hook`

- Type: `functional / display/composition`
- Intended problem:
  - unlike `i915`, local `xe` had no real CPU-side display flush hook for
    sysmem-backed scanout BOs.
- Expected solve path:
  - add a CPU `clflush`-based display-flush backend for sysmem scanout BOs.

### 14.4 `upstream-mtl-scanout-pat-guard`

#### `525165e` `xe/vm: reject non-UC binds for scanout BOs`

- Type: `functional / guard`
- Intended problem:
  - if scanout BOs must be uncached on the display path, perhaps `xe` should
    reject conflicting ppGTT PAT choices up front.
- Expected solve path:
  - hard-reject `VM_BIND` of scanout BOs when the PAT is not `XE_CACHE_NONE`.

### 14.5 `upstream-mtl-validate-guc-wa`

#### `d4005e1` `xe/guc: log MTL workaround validation state`

- Type: `logging / trace gatekeeping`
- Detects:
  - which GuC workaround bits are actually set at boot,
  - which workaround KLVs are emitted into ADS,
  - whether the suspected MTL `i915` workaround stack is present or absent.

### 14.6 `upstream-mtl-rcs-ccs-wa`

#### `0526c5a` `xe/guc: add MTL RCS/CCS workaround path`

- Type: `functional / platform-policy`
- Intended problem:
  - local `xe` lacked part of the MTL graphics-GT GuC workaround stack that
    `i915` carried for RCS/CCS switchout behavior.
- Expected solve path:
  - add the missing GuC WA bit and the MTL-specific ADS workaround KLVs.
- Cross-reference:
  - this was motivated by the upstream comparison work summarized in
    [05-upstream-commit-ledger.md](./05-upstream-commit-ledger.md).

### 14.7 `upstream-mtl-validate-vf-ccs`

#### `0424d6d` `xe/sriov: log VF CCS metadata flow`

- Type: `logging / trace dataflow`
- Detects:
  - whether the VF CCS metadata save/restore path is active at all,
  - when BOs enter VF CCS migration or restore batches,
  - whether VF CCS post-migration fixups execute.

#### `1ef7555` `xe/migrate: include sriov printk helpers`

- Type: `support`
- Purpose:
  - make `0424d6d` build cleanly by pulling in the SR-IOV printk helpers.

## 15. What This Ledger Says About The Investigation

Three broad patterns emerge.

### 15.1 Early local work was about making MTL VF/PF traffic visible and valid

The oldest branches were not yet about one narrow fix. They were about getting
enough truth out of the system to know:

- whether VF runtime queries were valid,
- whether PF relay service was handling the right packets,
- whether FLR and GGTT invalidation were occurring in sane contexts.

That is why the early history is rich in relay/MMIO/FLR tracing.

### 15.2 The central 2026 line was a GGTT transport and ordering investigation

The `upstream-mtl-boot` through `upstream-mtl-shadowverify` families are best
read as one long question:

- is the MTL VF/PF GGTT transport wrong,
- or is the transport right but the ordering, shadow, flush, or apply policy
  wrong?

The cleanpath branch exists only after that line had been simplified to a
smaller baseline.

### 15.3 The later branches intentionally pivoted away from raw GGTT transport

The branches after `upstream-mtl-cleanpath` show three pivots:

- broader MTL memory-policy guesses,
- display/scanout dataflow validation,
- MTL-specific GuC workaround and VF-CCS side hypotheses.

Those later branches should be read together with the upstream comparison
chapters, because they are direct local tests of mismatches first noticed in
upstream code or commit messages.

## 16. Recommended Reading Order Inside This Pack

If the goal is to understand the local investigation in context, the best order
is:

1. [03-xe-codeflow.md](./03-xe-codeflow.md)
2. [04-i915-vs-xe-comparison.md](./04-i915-vs-xe-comparison.md)
3. [05-upstream-commit-ledger.md](./05-upstream-commit-ledger.md)
4. this file

That order gives:

- the `xe` code structure first,
- then the major `i915` versus `xe` mismatches,
- then Intel's own messages,
- then the local branch history that tried to test those mismatches one by one.
