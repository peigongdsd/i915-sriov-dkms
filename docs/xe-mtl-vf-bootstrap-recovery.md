# Recovery assessment for the held v5 guest

This is a source-reviewed recovery procedure for the reported v5 hold at
`43d5e5d`, with host PF `02acd0415e056e859159e4825c3119124eee9785` on generation
204. It has not been executed or validated on hardware. The v5.1 guest patch
cannot change the module already running in the held VM.

## Scope and retained state

The supplied report records all seven map requests acknowledged, both GuC VF
consumer resets acknowledged, then explicit GuC INVALID_STATE on a PF relay
handshake. The inspected guest path holds before submitting its first clear.
Its six BO mappings remain owned; QEMU retains the guest memory and assignment.
There was no outstanding GGTT request identified in this reported sequence.

This assessment does not cover a lost map/clear reply, a concurrent new guest
probe, a different last checkpoint, or a host/PF failure. Preserve the VM and
return the new evidence if the live state differs. A running QEMU process alone
does not prove the required driver state.

## Existing PF recovery path

The tested host source exposes the device-wide PF debugfs endpoint:

`<verified PF DRM debugfs directory>/sriov/vf1/reset`

A true Boolean write invokes `xe_sriov_pf_control_reset_vf()`. It triggers the
VF FLR state machine on all GTs and then waits on all GTs. This is a
PF-coordinated VF reset, not a guest debugfs control or the PCI sysfs `reset`
file. The source-reviewed chain is:

1. `xe_sriov_pf_debugfs.c`: `reset_vf_write()` calls the PF reset helper.
2. `xe_sriov_pf_control.c`: trigger and wait loops cover all GTs.
3. `xe_gt_sriov_pf_control.c`: wait for GuC FLR done, synchronize GTs, sanitize
   resources, reset PF service/MMIO state, and finish the GuC FLR sequence.
4. `xe_gt_sriov_pf_config.c`: sanitizing the main GT's VF resources calls
   `xe_ggtt_assign()` on the VF region, replacing guest PTEs with ownership
   entries. The GGTT assignment holds the existing GGTT mutex.

These four control/configuration files match the host revision in the local
repository. The host GGTT invalidation path was inspected separately. A
successful reset return establishes the PF lifecycle's completion according
to that code. It is not independent PTE readback: the MTL assignment path writes
the MMIO invalidation register without the relay test's strict completion poll,
and some invalidation failures are reported as warnings rather than propagated
as reset errors. Preserve all host warnings and treat them as a failed recovery
check. Do not use this procedure as proof of general timeout cancellation.

## Live preparation

Keep the existing VM and assignment intact while doing these read-only checks:

- Save the full serial and host kernel logs and the exact tested module identities.
- Recheck QMP status, current QEMU PID, ownership of VFIO group 19, VF1's driver,
  host generation and loaded PF identity. The PID in the old report may be stale.
- Confirm the serial tail is still the same held handshake, with no later map,
  clear, reset or retry. Keep Windows and any competing VF user stopped.
- Resolve the DRM debugfs directory to PF `0000:00:02.0`; do not assume a numeric
  DRM index. Check that its device-wide `sriov/vf1/reset` endpoint exists.
  Inspect names/metadata only when discovering debugfs files: some other files
  perform operations on read. Do not recursively read the debugfs tree.
- Keep host-local capture active through recovery and record operation results.

If the endpoint or PF identity cannot be verified, report that gap. Do not
substitute a global GPU reset, remove the PF driver, or change VF provisioning.

## Controlled recovery on the hardware host

After the live preparation confirms this exact case, the hardware operator can
perform one PF-coordinated VF reset while QEMU and its memory remain retained:

1. Write `1` once to the verified PF `sriov/vf1/reset` endpoint and retain the
   write result and complete host log. Let the driver's bounded waits complete.
   Do not attach automatic QEMU teardown to a timeout or command failure.
2. If the write fails, stays pending, or logs FLR, forcewake, GGTT-invalidation
   or other new GPU errors, leave QEMU assigned and report. Do not retry.
3. If the operation completes successfully and the host remains healthy with
   no such errors, record this as PF-assisted recovery of the old diagnostic.
   The old guest is still held; it will not return from its probe automatically.
4. Only after that completion, end this disposable VM through its existing QMP
   control channel, wait for process exit and release of group 19, and capture
   any additional VFIO/PF teardown messages. Keep VF1 bound to vfio-pci.
5. Verify host health and exclusive ownership before a fresh v5.1 assignment.
   Preserve the old captures; do not report the recovered v5 run as successful
   guest cleanup. Do not restart Windows or launch the next test automatically.

This procedure is prepared for review and execution by the hardware operator;
no live reset, VM termination, host installation or reboot was performed while
preparing the v5.1 patch. If live recovery cannot satisfy the checks, arrange a
separate host recovery with the owner instead of improvising while allocations
are still retained.
