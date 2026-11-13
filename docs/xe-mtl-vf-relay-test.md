# MTL VF single-page PF relay experiment, v4

V4 completed downstream at `70dd8d6`. Continue with the
[v5 functional bootstrap handoff](xe-mtl-vf-bootstrap-test.md) on the new branch.

Branch: `codex/xe-mtl-vf-relay-test-v4`, based on tested v3 `1759b27`.
Identity: `diagnostic=mtl-relay-test-v4`.
Explicit guest module parameter: `mtl_vf_relay_test=1`.
The default is false and retains software-only PTE planning and rollback.

This is a diagnostic branch, not native VF graphics enablement or an
upstream-ready implementation. It changes the assigned guest's module;
the working host PF at `02acd04` stays unchanged.

## What v3 established

The supplied serial and GDB logs were inspected. They show successful BO
validation, the memirq caller, a 4096-byte BO with flags `0x260a2`, relative
node offset zero and absolute GGTT address `0x7ec00000`. The live DMA address
was `0x1e58e000`, with PTE `0x2000001e58e001`, PAT 2, BAR offset `0xbf6000`
inside a 16 MiB BAR, and writer `xe_ggtt_set_pte`. Software rollback and
ordinary probe failure completed, followed by alive and shutdown markers.
The supplied host log shows VFIO reset/FLR events. No allocator/TTM warning
appears in the supplied serial log. Module identities and generation 204
are reported by the tester; the actual module files were not supplied.

This verifies preparation of the first mapping in that guest. It does not
prove VF BAR access permission or establish the original hanging instruction.
There is no evidence here that memory-based interrupts are unsupported.

## Exact transaction

At the first observed one-page system-memory BO, keep existing validation,
allocation, SG/DMA selection and PAT encoding. Before the BO can become a
memirq buffer:

1. Negotiate the existing MMIO relay ABI 1.0, using magic 1.
2. Send one PTE through the primary GT's existing MMIO update opcode, using
   magic 2 and a VF-relative page offset. Require a success reply carrying
   both the matching magic and count 1.
3. Send the ownership-only value `0x1` to that same relative page, using
   magic 3. Require matching magic and count 1 again. The working PF adds
   the authenticated VFID, restoring the PRESENT/ownership-only form used
   by its allocation/sanitization path. This is not an invalid PTE and must
   not be used as a general unmap policy for an active VF.
4. Only then release the software node and return the intentional `-95`.

The test never installs the BO as a memirq buffer, enables CT, submits work
or directly accesses the VF GGTT BAR window. No additional VF GGTT flush or
invalidation is issued. PF `02acd04` performs the store, posting flush and
strict invalidation for both GTs before returning success. Receipt of that
reply is a software completion check, not independent GPU readback of the PTE.

The bootstrap transport shares Xe's existing MMIO implementation. Its new
single-attempt entry point disables resubmission after lost replies, FLR
scratch clearing or GuC RETRY. BUSY still waits for a final response. Existing
callers retain their existing retry behavior. No retry is added in the test.

## Failure behavior is different from v3

A handshake failure occurs before a PTE request, so the diagnostic can remove
its unused node and return `-95`. Capture its error; this is not test success.

After either PTE request is submitted, every negative result, wrong count or
wrong magic is treated as uncertain completion. The probe sleeps indefinitely
in `vf_ggtt_test_hold()` without unwinding. The still-active probe retains the
BO reservation, DMA mapping, GGTT node, runtime-PM reference and device
infrastructure. This avoids the withdrawn scheme of merely retaining GEM
references after device cleanup. No reset, retry or cleanup request is sent
on this path.

This intentional hold is diagnostic containment, not a production recovery
solution. It depends on keeping the guest and its VF assignment intact.
Do not use a launcher that kills QEMU, shuts down/reboots the guest or reuses
the VF when module loading times out. Do not force module removal, hot-unplug,
reset the VF, start Windows, alter `sriov_numvfs`, or bypass the hold in GDB.
On the hold marker, leave the VM running and report the logs for a separately
planned recovery. There is no claim that forced VM destruction safely drains
an uncertain PF request. Host-local logs cannot survive every host failure.

## Preparation and one-run handoff

- Preserve host generation 204, PF `02acd04`, Nix pins and boot entries.
  Verify current state rather than relying on the previous report.
- Reuse the prepared exact Linux 7.3.3 guest build tree and minimal VM.
  Build matching Xe and compatibility modules from the supplied v4 commit,
  append `KCFLAGS=-g`, and retain unstripped modules. Record source SHA,
  SHA-256, vermagic and srcversion. Do not reuse the local 7.3.4 binaries.
- Confirm Windows is shut down and VF1 is exclusively owned by host VFIO.
  Use the fresh assignment/FLR setup that preceded v3; verify reset completes
  and no reset or assignment change occurs during this transaction.
- Establish guest serial and host-log capture at an independent receiver.
  If unavailable, prepare artifacts and report before the hardware probe.
- Remove automatic VM/module-load timeout cleanup, watchdog restart and
  panic-on-hung-task behavior from this diagnostic launcher. On the hold
  path, `insmod` will not return; a shell timeout must not trigger VM teardown.
  Do not automatically restart Windows after any result.
- In the guest, explicitly load this Xe module with `mtl_vf_relay_test=1`.
  A build/pin alone does not enable the transaction. A host-local native VF
  (`pdev->is_virtfn`) is refused by the test before submission.
- Use `loglevel=7`, the current module section addresses and new symbols.
  Useful GDB breakpoints are `xe_ggtt_vf_probe_pte`,
  `xe_gt_sriov_vf_test_ggtt` and `vf_ggtt_test_hold`. Inspect before submission;
  avoid stepping the transport while a PF reply is pending. Do not force
  return values or resume past the intentional final rejection.

Expected successful checkpoints, in order:

```text
VFPROBE: diagnostic=mtl-relay-test-v4 before VF_CAP ...
VFPROBE: BO validation returned 0
VFPROBE: PTE candidate, ...
VFPROBE: before MMIO relay handshake ABI 1.0
VFPROBE: before PF map, page=... pte=... magic=2
VFPROBE: PF map acknowledged, count=1
VFPROBE: before PF restore, page=... pte=0x1 magic=3
VFPROBE: PF restore acknowledged, count=1; BO mapping removed
VFPROBE: software node removed, relay_test=1 result=0; stopping probe
VFPROBE: memirq initialization returned -95
GUEST_ALIVE_AFTER_PROBE
```

Normal guest shutdown is appropriate only after confirmed restoration,
software rollback and the alive marker. A handshake-only rejection can also
shut down after the explicit no-PTE-submitted message and ordinary rollback.
Any other sequence requires inspection before teardown. The final `-95` alone
is insufficient: omitting the parameter also produces `-95` without a relay.

Return full serial/GDB/host logs, actual request values and module identities,
not only the checkpoints. Confirm guest shutdown, host health and VFIO binding
only if the success path completed. One run only; do not automatically retry.

## Validation and remaining work

The Xe and compatibility modules build against local Linux 7.3.4 with GCC
16.2.0 and debug information. Hardware is not available on this build host.

`scripts/test-xe-mtl-vf-relay.py` compiles the actual C transport and transaction
functions with scripted MMIO replies. Its 14 cases cover successful encoding,
BUSY followed by success, handshake rejection, wrong ABI, map/restore errors,
wrong magic/count, timeout, cleared scratch registers, GuC RETRY, and preservation
of existing callers' replay behavior. Its wait stub intercepts the diagnostic
hold. These tests establish software decisions only; they cannot establish
firmware ordering, actual DMA/TLB behavior or cancellation across reset.

A successful v4 result supports using the PF bootstrap relay for the first
mapping. It does not validate memory-interrupt delivery, CT setup, submission,
clear batching, suspend/resume or production failure recovery. A general native
VF implementation still needs a proven reset/drain-before-reuse contract and
error propagation throughout map/unmap. This branch intentionally does not
pretend that diagnostic holding solves those requirements.
