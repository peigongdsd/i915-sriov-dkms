# Meteor Lake native VF v8.2: receive dispatch and Vulkan

This branch continues the full native driver at v8.1, c0ca6cb9915f1dc6bc45c405aad49786abc49ef4.
It does not stop probe at a diagnostic checkpoint. The live identity is
`mtl-native-v8.2`. Use `mtl_vf_native=1`, with the bootstrap and relay test
parameters disabled, as in the successful v8.1 guest and host runs.

## Evidence and scope

In the captured host VF vkcube failure, CT fence 748 and PF relay 646 timed
out. The VF GT0 receive buffer subsequently contained both a GuC success
acknowledgment and the matching PF success response for four pages. Its
head/tail remained 985/991 in snapshots more than sixteen minutes apart.
The snapshots do not timestamp the original arrival, prove PTE contents,
or establish an interrupt or runtime-PM root cause. The blocked allocation
was a bind-queue LRC during VM creation; rendering had not been established.

The receive worker already has a timeout flush in this source. A flush
alone does not queue idle work. The native MTL single-attempt CT and PF
relay waiters now each get at most one explicit receive-worker queue/flush
before their original fence/RID is retired. The existing worker, PM rules,
parsers, response validation and waiter locks remain responsible for
completion. No PTE request is replayed, no periodic polling is added, and
no firmware timeout is increased. Like the pre-existing flush, waiting for
a running worker is not an independently bounded wall-clock operation.
Ordinary replay-capable CT calls and non-native devices retain their
existing timeout behavior.

Trace events record the receive boundaries. Disabled tracing performs no
additional descriptor or interrupt-page reads. Samples are observational,
not an atomic snapshot across CPU and firmware. Memory-interrupt status
bytes are not cleared by tracing. In the usual non-debug configuration the
normal handler can leave status bytes set, so a status byte alone does not
prove a fresh interrupt.

Unresolved native GGTT failures now set a per-device-visible failure state
before releasing the shared GGTT mutex. New native and compat ioctls fail
with EIO; allocations already waiting for that mutex fail before inserting
a new node. Later GGTT updates cannot submit another request. The affected
operation and backing remain retained. This is diagnostic containment,
not production error recovery: it does not make the original operation,
all already-running callers, file close, device removal or module unload
return normally. A completed PF update still cannot be undone safely merely
by forgetting its waiter. Do not use successful compilation as evidence
that uncertain mapping cleanup is solved.

## One hardware run

This is authorized testing of the open-source Xe driver on the user's own
ThinkBookX and assigned VF. Use the established local NixOS/test workspace.
Preserve existing evidence, normal configuration, pin and generation 207
fallback. Windows must remain off. Keep native VF autoprobe disabled.

1. Build Xe and compatibility modules from the exact handed-off commit
   against the host's exact kernel build tree (previous tests used 7.3.3),
   with debug information. Record source commit, SHA-256, vermagic and
   srcversion. Local development builds against 7.3.4 are not substitutes
   for that target build.
2. Prepare a separate host test specialization/entry using the established
   v8.1 workflow; retain the working fallback and default. Do not hot-unload
   the display PF. Coordinate a boot if the matching module is not already
   loaded. A staged build/entry is not an activated or booted system.
3. Verify the booted identity and parameters, PF binding, zero VFs, Windows
   state and baseline journal. Start host-local journal and trace capture
   before creating/binding VF1. Check for the old udev VFIO rebind rule and
   isolate this explicit native Xe bind from it. Resolve PCI-to-DRM mapping
   afresh; do not assume card or render node numbers.
4. Select the `mono` clock in a dedicated trace instance. Enable these Xe
   events, stream trace_pipe to disk, record their formats, and collect
   per-CPU loss counters at start and finish:

   - xe_memirq_rx
   - xe_guc_ct_rx
   - xe_guc_relay_rx
   - xe_guc_ctb_h2g
   - xe_guc_ctb_g2h

5. Create one VF and explicitly bind it to Xe using driver_override as in
   v8.1. Record both GT initialization results. Run the previously passing
   IGT query checks and checked system-memory basic-store once.
6. Run one VF-selected Wayland vkcube using the desktop user's working
   Vulkan environment. Establish selection from PCI identity and the
   application's DRM descriptors, not an assumed gpu_number. Capture the
   exact command, environment, Mesa/ICD identity and stdout/stderr. The
   earlier vulkaninfo VK_KHR_display failure was separate from the CT hold;
   it is not a prerequisite for this rendering test. Do not launch Chrome
   or an unrelated application as a second VF stress test.
7. If the cube renders normally, close it normally, perform one VF-only
   unbind/rebind, repeat the checked store and cube, and record teardown.
   Keep the PF bound throughout. If any operation blocks, a containment
   message appears, or new host GPU errors occur, stop advancing the test.
   Preserve the device and relevant process state and collect evidence;
   do not automatically reset, unbind, kill QEMU, or reboot as a timeout
   cleanup action. Recovery is a separate decision after collection.

For a timeout/hold, collect both GTs' complete CT buffers for PF and VF,
interrupt counters, power state, application stacks, receive-worker stacks
and the journal while the already-running trace continues. Record the
capture times and whether any read changes runtime power state. Take two
bounded snapshots rather than repeating workloads. Original partial logs
must survive capture-tool failures.

## Interpretation

`xe_guc_ct_rx` identifies PCI device and GT. Its phase is `irq-queue`,
`irq-disabled`, `worker-enter`, `receive`, `pm-skip`, `receive-done`,
`worker-exit`, `response`, `ct-timeout`, `relay-timeout`, `timeout-queue`
or `timeout-drained`. `result` is the queue_work result for queue phases,
the PM-reference result for receive, the dequeue return for receive-done,
and HXG response type for response. `fence` holds the CT fence, or the RID
when the originating timeout is relay-timeout; correlate the phase first.
`pending` is a work-pending sample, not proof that a worker is running.
Disabled CT or I/O-mapped descriptor fields are zero placeholders.
Worker-entry and PM-skip tracing must not read powered-down VRAM.

`xe_memirq_rx` records top-level IRQ enable, memirq enable, BO presence,
and primary/media GuC source/status bytes at IRQ entry, dispatch and
native timeout. Descriptor/page samples do not change interrupt policy.
When top-level IRQs are disabled, source/status reads are skipped and
those fields are zero placeholders.

`xe_guc_relay_rx` records send-once RID and reply matching, remote origin,
reply code, length and first message dword. `reply-unmatched` also covers
an oversized matched response: it is not evidence of a wrong RID alone.
Existing CT trace events supply normal send/dequeue traffic.

- Successful rendering without a kick establishes the workload passed,
  but does not explain the old failure.
- A timeout with queued data, followed by one worker pass and matched
  success, supports missed/stalled receive dispatch. Record how often this
  happened. A cube that advances only through timeout kicks is degraded,
  not a performance or root-cause fix.
- A worker entering and emitting pm-skip distinguishes a PM eligibility
  problem from no worker dispatch; do not change PM policy based only on
  a later debugfs power sample.
- Empty data at timeout followed by a later arrival remains a different
  timing case. A worker pass must not manufacture completion.
- EIO for new work after containment does not establish that the held
  mapping is cleared or that unload is safe.

Return one complete bundle with module/source identities, boot and device
mapping, workload results, trace and loss counters, journal, relevant live
snapshots and the final machine state. State separately: normal success,
recovered-but-degraded progress, or retained failure. Do not retry the
experiment automatically.

## Local checks

Run scripts/test-xe-mtl-vf-ct.py, scripts/test-xe-mtl-vf-bootstrap.py and
scripts/test-xe-mtl-vf-relay.py. These compile actual helper code against
modeled firmware/locks and cover one-shot recovery, registered waiter
lifetime, wrong RID, BUSY/deadline behavior, failure containment and the
existing GGTT lifecycle cases. They do not emulate kernel workqueue
concurrency, real interrupts, DMA or reset ownership. Build the complete
Xe and compatibility modules and run checkpatch on the commit series.
