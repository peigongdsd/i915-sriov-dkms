# Release readiness

## Current decision

**Functional native VF bring-up is demonstrated; production readiness is not.**
The user is evaluating the exact tested v8.2 driver in a normal host profile.
This clean branch is separate and must not silently replace that build.

### 1. Uncertain GGTT completion still retains an operation indefinitely

`xe_gt_sriov_vf_retain()` deliberately does not return. The PF may have applied
an update whose acknowledgment was lost. Letting the stack unwind could free
DMA backing or reuse an address still referenced by the GPU or queued PF work.
The v8.2 mutex-release/ioctl-failure changes reduce collateral blocking, but
object reservations and teardown can still wait indefinitely.

The production replacement needs a confirmed completion/cancellation boundary,
then bounded error propagation through normal Xe reset/removal and TTM lifetime.
Audit partial batches, late replies, reset races, scratch and CT/memirq backing,
and the pinned-DMA unmap path during PCI removal. Neither changing an epoch nor
sending a VF reset alone proves that queued PF requests are cancelled. Do not
replace the hold with `return -EIO` and call that recovery.

### 2. Receive starvation is observed, not solved

The completed v8.2 host run (`d50cc0c`, Linux 7.3.3) unbound in about 9.9 seconds.
VF1 GT0 fences 2011–2019 each needed one deadline kick. At the sampled deadline:

* CT was enabled; the memory tail was six dwords beyond the software/memory head.
* The worker was not pending. Software IRQ and memirq enabled flags were both 1.
* Source/status bytes were pending (`0xff`).
* Each queued receive pass consumed a successful GuC acknowledgment and a
  matched PF relay response, RIDs 670–678.

The captured VF events in the unbind window contain no IRQ-entry or dispatch
trace events and no worker PM-skip event. All 22 CPUs reported zero trace loss.
This narrows investigation toward interrupt delivery/dispatch before receive
work is queued; software flags alone do not prove the physical MSI path remained
functional. It does not prove where the interrupt was lost or explain the older
Vulkan stall. A receive pass is not a new interrupt implementation.

Rebind, the checked store and the VF cube did not require kicks. Keep that
normal success separate from teardown success dependent on assistance. The
next receive change should address a demonstrated ordering/delivery defect,
not simply shorten the deadline, poll forever, or keep the GPU awake.

### 3. Validation coverage is still limited

The consolidated tree has no hardware result yet. The parent has a successful
v8.1 guest lifecycle and v8.2 host Vulkan/lifecycle result, with the above
qualification. Extended usage, guest Vulkan, repeated lifecycle, runtime idle
transitions, system suspend/resume, reset/error recovery and multiple VFs are
not certified. Migration was reported unavailable for the tested GuC ABI 1.26.0.
Do not add speculative platform exceptions just to make this list shorter.

## Completion criteria

1. Rebuild the clean branch for the exact target kernel and repeat the known
   guest/host acceptance workloads, recording its own module identity.
2. Complete realistic repeated application and teardown use without receive
   starvation, or explain and fix its specific cause with captured evidence.
3. Return errors and complete removal without indefinitely retained operations,
   with tests proving backing is not freed while a remote update can use it.
4. Audit the PF service and submission/reset interaction, and run the relevant
   idle, suspend and multi-VF cases before claiming those capabilities.
5. Submit the minimal platform/backend/lifetime changes for review, keeping
   optional evidence collection and unresolved workarounds separately visible.

Do not advertise this branch as production-ready until these items are resolved.
