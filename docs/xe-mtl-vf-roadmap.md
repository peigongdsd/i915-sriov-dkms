# Meteor Lake native Xe VF roadmap

The implementation target is a usable Linux guest VF first, followed by native
host VF binding with the same driver path. Maximize reuse of Xe's ordinary
allocation, interrupt, CT, submission, reset and power-management infrastructure.
Keep platform differences at the GGTT access and early transport boundaries.

## Evidence and next gates

| Stage | Status | Evidence or acceptance condition |
| --- | --- | --- |
| PF and assigned Windows VF | Reported working | Current guest test host is generation 207 / PF b0aa9a8; preserve its pin. |
| Native guest bootstrap and CT GGTT | V6 reported passed | Memirq delivery, native CT query, temporary mapping/release/reuse and acknowledged cleanup. |
| Scratch and expected communication reset | V7 standalone diagnostic untested | V8 subsequently exercised normal scratch/probe; diagnostic reset cycle remains separate. |
| First engine work | V8 passed | Ten ordinary initialization jobs across rcs0, bcs0, ccs0, vcs0 and vecs0, positive waits and fence status 1. |
| Complete guest probe | V8 passed | Both GTs, native probe return 0, DRM render node and normal PM initialization. |
| Useful guest workload | V8 basic-store passed | IGT checked a GPU store in system memory; graphics workloads and sustained reuse remain. |
| Lifecycle and native host VF | V8 unload failed; V8.1 fix prepared | Validate interface restoration and unload/reload/store in the guest, then native host VF with the same implementation. |
| Upstream review series | Not ready | Remove experiments, complete error handling, review normal-path cost and document hardware coverage. |

V6's PF acknowledgements and interrupts do not prove engine execution or
independent PTE readback. V7's scratch test will not close that gap. MTL supports
memory-based VF interrupts in Xe; its restricted VF GGTT writes are a separate
platform characteristic. The original direct-BAR hang remains a strong source
hypothesis rather than a captured failing instruction.

## Native implementation approach

The normal path calls `xe_uc_sanitize_reset()` again during VF hardware load,
then enables submission and records default LRCs. Preserve mapped backing and
refresh transport negotiation across each expected reset. Reuse ordinary Xe
queue/job creation and completion; check fence error status as well as whether
the wait completed.

V8 uses normal Xe queue lifetime and recovery. It does not add a private queue
counter, force scheduler threads into holds, change timeouts or pin the device
awake. The full-probe option selects the PF-mediated GGTT backend while leaving
the old bootstrap-only diagnostic separate. Test normal workload and cleanup
with ample diagnostics, then fix concrete failures at their actual boundary.

V8.1 addresses the observed late-unload MMIO handshake rejection. Restore the
GuC version interface through the existing helper before the PF handshake, and
invalidate the cached relay state on normal client soft reset as well as VF
reset. Preserve the ordinary reset, CT shutdown and BO release ordering. This
is a candidate fix for a captured failure, not a completed lifecycle result.

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
