# Meteor Lake native Xe VF roadmap

The implementation target is a usable Linux guest VF first, followed by native
host VF binding with the same driver path. Maximize reuse of Xe's ordinary
allocation, interrupt, CT, submission, reset and power-management infrastructure.
Keep platform differences at the GGTT access and early transport boundaries.

## Evidence and next gates

| Stage | Status | Evidence or acceptance condition |
| --- | --- | --- |
| PF and assigned Windows VF | Reported working | Preserve host generation 204 / PF 02acd04 as the test baseline. |
| Native guest bootstrap and CT GGTT | V6 reported passed | Memirq delivery, native CT query, temporary mapping/release/reuse and acknowledged cleanup. |
| Scratch and expected communication reset | V7 implemented, awaiting hardware | Normal hole setup, CT reconnection, post-reset temporary lifetimes, full-range cleanup. |
| First engine work | Implementation remains | Ordinary default-context WA/NOP jobs with successful fence status and a defined timeout/queue-retirement path. |
| Complete guest probe | Implementation remains | Primary and media initialization, supported engine classes and DRM render-node registration. |
| Useful guest workload | Not tested | Verify GPU-written results, then a small graphics workload and repeated allocate/submit/release. |
| Lifecycle and native host VF | Not ready | Failed-probe cleanup, unload, reset/recovery and rebinding; then native host VF tests. |
| Upstream review series | Not ready | Remove experiments, complete error handling, review normal-path cost and document hardware coverage. |

V6's PF acknowledgements and interrupts do not prove engine execution or
independent PTE readback. V7's scratch test will not close that gap. MTL supports
memory-based VF interrupts in Xe; its restricted VF GGTT writes are a separate
platform characteristic. The original direct-BAR hang remains a strong source
hypothesis rather than a captured failing instruction.

## Work before an engine experiment

The normal path calls `xe_uc_sanitize_reset()` again during VF hardware load,
then enables submission and records default LRCs. Preserve mapped backing and
refresh transport negotiation across each expected reset. Reuse ordinary Xe
queue/job creation and completion; check fence error status as well as whether
the wait completed.

A probe-thread hold alone cannot contain an engine timeout: scheduler work and
GuC deregistration run asynchronously. Their ownership, backing release and
consumer-quiescence ordering must be accounted for before enabling submission.
A successful job also needs its queue retired before clearing mappings. Do not
add a second submission implementation to avoid this audit.

## Shape of the eventual review series

This is a proposed split, not a statement that these production patches exist:

1. Retain only justified PF/platform enablement changes from the conservative
   review series, with accurate firmware/GSM capability checks.
2. Add narrowly scoped transport completion/error handling needed by
   non-replayable VF GGTT updates, preserving existing callers' behavior.
3. Route affected VF GGTT ranges through the common PF ABI with coalescing,
   bounds/PTE validation and PF-owned invalidation. Keep ordinary Xe allocators,
   PAT selection, scratch setup and power-management ownership.
4. Integrate backing lifetime, transport transitions and failure/recovery
   behavior into normal BO and device lifecycles. A timed-out request is not
   cancelled merely because a local epoch changed or a VF reset was sent.
5. Add focused automated tests and platform notes, backed by guest and native
   host results. Remove diagnostic flags, intentional -95 stops and indefinite
   holds from the production proposal.

Keep the v6 and v7 diagnostic branches as reproducible evidence. Do not present
an accumulated stack of experiments as the final upstream patch series. Request
new hardware runs only when the code has a concrete new checkpoint that static
analysis and local tests cannot establish.
