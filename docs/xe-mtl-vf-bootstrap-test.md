# MTL VF functional bootstrap experiment, v5

Branch: `codex/xe-mtl-vf-bootstrap-v5`, based on tested v4 `70dd8d6`.
Live identity: `diagnostic=mtl-bootstrap-v5`.
Guest module parameter: **`mtl_vf_bootstrap_test=1`**.
Leave the older `mtl_vf_relay_test` parameter off. Both parameters default off.

This experiment retains real mappings for the ordinary Xe bootstrap path.
It targets memirq setup, CT communication, and cleanup before DMA backing is
released. It stops before engine submission, DRM registration or a workload.
The host PF remains `02acd04` on generation 204. This is a diagnostic branch,
not an upstream-ready native VF implementation or general reset recovery.

## Evidence entering this test

The supplied v4 serial/GDB/host logs were inspected. At `70dd8d6`, the guest
received matching count-1 acknowledgements for PF map and restore, released
its software node with `result=0`, returned the intentional -95, emitted the
alive marker and powered down. The PTE was `0x200000087f1001`, relative page
zero, absolute GGTT address `0x7ec00000`. No uncertain-completion marker was
present. The captures were host-local. Those acknowledgements did not test
CT, interrupt delivery, a workload or independent PTE readback.

## Implemented path

The test preserves Xe BO allocation, validation, SG/DMA selection, PAT
encoding, GGTT allocation, memirq initialization, IRQ installation, CT
allocation/registration, and the normal VF/PF CT handshake/runtime queries.

The new bootstrap GGTT mapper consumes the existing DMA cursor. Adjacent DMA
pages are sent as one existing REPLICATE request, up to 1024 pages per request;
a discontinuity starts another run. Clear uses the existing duplicate mode
and the PRESENT/ownership-only PTE, also up to 1024 pages per request. The PF
adds the requesting VFID. It performs its strict invalidation before replying.
There is no additional VF posting read or invalidation, no direct VF GGTT BAR
access and no protocol extension. Each request is acknowledged before the
next; no request is automatically replayed after a lost reply or RETRY.

These are early MMIO updates. The mapper intentionally refuses updates while
the primary CT is active. Native CT is exercised using its existing handshake
and runtime-query requests, not a new GGTT-over-CT implementation.

The actual stop is in `vf_guc_min_load_for_hwconfig()`, after the primary GT's
ordinary CT handshake and runtime query. `xe_memirq_init()` must now return 0.
The test does not continue into GGTT scratch initialization, default contexts
or submission. Media-GT CT and media-engine operation remain untested.

The marker reports `memirq_dispatches=N`, incremented when the memory interrupt
handler dispatches to that GuC. CT can use polling in some configurations, so
CT success with zero dispatches does not establish interrupt delivery. Record
both the count and guest interrupt/MSI state rather than calling that a full
interrupt success. The counter is diagnostic and not intended for production.

## Mapping lifetime and error handling

An acknowledged map stays installed while the BO is used. The ordinary BO
allocation path returns success only after all its batches are acknowledged.
A partial map, bad count/magic, failed handshake or missing response holds the
current operation, retaining its state. It never falls back to a VF BAR write.

On a normal bootstrap stop or an earlier ordinary probe error, the PCI probe
performs cleanup while device-managed resources are still live:

1. Stop the guest CT workers and require a successful single-attempt GuC
   VF-state reset on both GTs, stopping consumers of the mapped buffers.
2. Clear all still-owned mappings through the PF and require completion.
3. Let normal devres/TTM cleanup remove nodes and release BOs.

The reset here is used only when no GGTT update is outstanding. It is not
claimed to cancel a late PF update. Any uncertain update already held the
operation and cannot reach this cleanup. A failed consumer reset also holds;
no clear or resource release follows it.

For BOs released earlier by an allocation/error path, the existing TTM
`delete_mem_notify` hook clears their mapping before backing is destroyed.
The later node destructor performs software removal only. In the
[inspected upstream TTM path](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/ttm/ttm_bo.c),
`delete_mem_notify` precedes `ttm_bo_tt_destroy`; the BO destructor is later.
The local build and simulator do not independently exercise that integration
on the target Linux 7.3.3 kernel; preserve any TTM/allocator warning in the logs.

Unexpected async reset or migration recovery is recorded and suppressed in
this test. It makes the result inconclusive; the operation/cleanup then holds
rather than starting an unvalidated recovery. Unexpected direct GGTT access
also holds. None of these diagnostic holds is a production recovery policy.

## Preparation and one-run instructions

Preserve generation 204, host PF `02acd04`, Nix pins and boot entries. Verify
Windows has released VF1 and host ownership remains `vfio-pci`; isolate binding
rules. Use the established fresh assignment/FLR setup and confirm completion
before loading Xe. Do not change the assignment or reset the VF during probe.

Reuse the existing exact Linux 7.3.3 guest kernel and prepared build tree.
Build matching Xe/compat modules from the supplied v5 commit with `KCFLAGS=-g`;
retain the unstripped module, record SHA-256/vermagic/srcversion, and require
the live v5 identity. No new guest kernel or host activation is required.

Use guest `loglevel=7`. Explicitly load Xe with `mtl_vf_bootstrap_test=1` and
without `mtl_vf_relay_test=1`. A host-local VF is rejected before mapping.
Without the new parameter, this branch retains the earlier software-only stop.

Establish independent off-host serial/host-log capture before probing. Prepare
artifacts and report if that capture is unavailable. Remove automatic module
load/VM timeout cleanup, guest watchdog restart and panic-on-hung-task behavior.
A diagnostic hold must leave the VM running and its VF assigned. Do not kill
QEMU, shut down the guest, unbind/reset the VF, start Windows, force-remove Xe,
or bypass the hold in GDB. Report the marker and logs for a separate recovery
plan. External destruction is not covered by the containment mechanism.

Use passive serial capture as the primary evidence. GDB may break before the
first mapping or before the normal CT sequence. Do not single-step while a
relay/CT response is pending. Load symbols at this run's module addresses;
use source path substitution if needed. These symbols are present in the local
debug build; confirm them again in the target build:

- `xe_gt_sriov_vf_bootstrap_update`
- `xe_guc_enable_communication`
- `xe_ggtt_vf_bootstrap_finish`
- `xe_gt_sriov_vf_test_hold`

Expected successful checkpoints include:

```text
VFPROBE: diagnostic=mtl-bootstrap-v5 before VF_CAP ...
VFPROBE: bootstrap MMIO relay ready
VFPROBE: map acknowledged relative=... pages=... requests=...
VFPROBE: memirq initialization returned 0
... further pool/CT/hwconfig mappings ...
VFPROBE: before hwconfig and CT bootstrap
VFPROBE: before GuC memirq registration
VFPROBE: before CT registration and enable
VFPROBE: CT enabled; before native PF handshake
VFPROBE: native CT handshake and runtime query passed; memirq_dispatches=N
... intentional initialization errors ending in -95 ...
VFPROBE: before bootstrap consumer reset
VFPROBE: bootstrap consumer reset acknowledged
... reset acknowledgement for the other GT ...
VFPROBE: unmap acknowledged relative=... pages=...
VFPROBE: all bootstrap GGTT mappings removed before devres cleanup; ct_passed=1
... Xe probe failure -95 ...
GUEST_ALIVE_AFTER_PROBE
```

The final -95 alone is insufficient. Require CT success, successful cleanup,
no hold/reset-suppressed/migration-suppressed marker, and an alive marker.
Report zero memirq dispatches as interrupt delivery unproven. Record the last
checkpoint on any earlier failure. An ordinary failure may cleanly unwind
with `ct_passed=0`; do not label that a successful bootstrap test.

After the complete success sequence, shut down normally, verify QEMU shutdown
before release, and verify host health/VFIO ownership. Return full serial,
GDB and host logs plus module identities. Do not automatically retry or restart
Windows. One run is sufficient to decide the next implementation change.

## Local validation and limits

The Xe/compatibility modules build with GCC 16.2.0 and debug information against
local Linux 7.3.4. Checkpatch and whitespace checks pass. No module was loaded
on this build host. The target must rebuild for its exact Linux 7.3.3 kernel.

The existing 14 protocol cases still pass. The additional 14 cases in
`scripts/test-xe-mtl-vf-bootstrap.py` compile the actual batching, relay, clear
and quiescence helpers against scripted DMA addresses and replies. They cover
1/1024/1025-page runs, fragmented DMA, partial-map response loss, clear response
loss, handshake failure, bad counts, active-CT/reset guards, size limits,
consumer-reset acknowledgement and consumer-reset failure. These tests do not
validate hardware DMA, interrupts, firmware reset semantics or TTM/devres
integration. Those are boundaries for the guest evidence.

A successful result advances functional bootstrap. Full CT-based GGTT updates,
scratch initialization, both GTs, engine execution, production error propagation,
reset/drain-before-reuse, suspend/resume and general unbind remain future work.
