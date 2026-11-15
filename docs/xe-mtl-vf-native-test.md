# Meteor Lake native Xe VF, v8.1

Branch: `codex/xe-mtl-vf-native-v8.1`.
Base: v8 `7b67c2f436d8118ef2d3b96686237955cdbd8d6c`.
Use the exact commit supplied with the handoff.

## Run full probe

Load the experimental module with:

```
mtl_vf_native=1 mtl_vf_bootstrap_test=0 mtl_vf_relay_test=0
```

This mode attempts the entire ordinary Xe VF probe, including primary and media
GTs, default-context jobs, DRM registration and normal PM initialization. There
is no deliberate `-95`, guest-only PCI check, pre-submission stop, temporary-BO
exercise or diagnostic whole-GGTT cleanup. Existing bootstrap and relay options
remain separate, mutually exclusive experiments for reproducing older results.

The implementation is shared by an assigned Linux guest VF and a Linux host VF.
The next hardware run is in the guest. Native host binding is a later test, not a
separate implementation. Keep the host PF configuration and native VF autoprobe
as currently arranged; building this branch does not authorize activating a new
host driver or binding its VF on the host.

## What changes

The candidate reuses the tested PF-mediated GGTT mapper, coalescing consecutive
DMA pages and duplicating scratch entries in batches of up to 1,024 pages. The
PF owns GGTT invalidation. Ordinary BO restore uses the same mapper; the generic
PTE writer also routes through the PF, without issuing the CPU-write workaround
on the VF. PAT encoding, Xe's allocator, memirq, CT, default contexts, scheduler,
queue destruction, reset and power-management policy remain the normal paths.

V8.1 restores the GuC interface before negotiating the PF MMIO relay interface
when the native relay cache is invalid. Both normal VF reset and client soft
reset invalidate that cache. The existing version helper requires the previous
GuC interface version; subsequent MMIO updates reuse the connection. Native
GGTT updates select the enabled CT transport or early MMIO transport without the
old experiment's artificial CT-phase requirements. This does not add retries to
a submitted GGTT update whose completion is unknown.

Ordinary TTM destruction clears the acknowledged mapping before releasing its
DMA backing. Normal GGTT finalization clears scratch references in holes and
retired nodes before freeing scratch, preserving mappings of still-live BOs.
This replaces the experiment's reset-and-clear-everything sequence in native
mode. It is not a new queue teardown implementation.

The separate Wa_22016122933 backport uses Xe's existing UC allocation flag for
media-IP 13.00 GuC-shared buffers. It is the same candidate included in the host
comparison. MTL already has memory-based VF interrupts; this coherency issue and
restricted VF GGTT access do not mean that MTL lacks that interrupt feature.

## Guest handoff

1. Start after separately coordinated recovery of the held v8 VM. Rebuilding
   does not change that VM or resolve its held unload. Preserve the running
   generation-207 host profile, PF pin and boot entries. Reuse Linux 7.3.3 and the
   exact build tree; build both modules with `KCFLAGS=-g` and retain the original
   debug copies. Record commit, SHA-256, vermagic and srcversion.
2. Use the established host-local serial and host-kernel captures. Keep Windows
   off and pass the VF through VFIO. Record host boot ID and loaded PF identity.
   No new 15-minute control stages are required by this implementation test.
3. Load Xe with the parameters above. Let full probe run. Success means a
   successful module load, the final native-probe marker, and a DRM render node
   associated with the guest VF. `-95` is a failure in this mode. Capture the
   native GT return codes, per-engine initialization wait/fence status, and
   memirq counts. Positive waits should accompany fence status 1; a signalled
   error fence is not successful engine execution.
4. If probe succeeds, use the available IGT tests rather than a new private
   submission implementation. Check their local `--list-subtests` output and
   run the basic Xe queries and `xe_exec_store --run-subtest basic-store` against
   the VF. Record individual engine results and skips. That IGT subtest submits
   a store and checks the written value; probe success alone does not prove it.
   If IGT is missing, report that separately from the probe result and prepare
   it using the local package configuration. Do not silently substitute a NOP.
5. With successful workload completion, close test clients, unload the guest Xe
   module normally, reload it once, and repeat the basic store. Record explicit
   unload and reload return codes. Capture each GT's normal GuC soft/VF reset
   results, `MMIO GGTT GuC interface restored`, PF relay readiness and mapping
   clears. A restore marker alone is not completed unload. The live identity
   must be `mtl-native-v8.1`. Then shut down the guest normally and confirm
   QEMU exit, VFIO-group release and host health. Do not use the old automatic
   SysRq-after-expected-rejection script: this mode leaves a live DRM driver.
6. On an error or crash, preserve the full captures and report the last operation,
   task/queue status and whether Xe's normal recovery ran. Do not repeat the
   failing probe automatically. The existing mapper still retains backing on
   an unacknowledged PF update: that is an ownership uncertainty, not a probe
   checkpoint. Capture that state before arranging recovery.

IGT source for the suggested workload:
https://chromium.googlesource.com/external/gitlab.freedesktop.org/drm/igt-gpu-tools/+/refs/heads/upstream/master/tests/intel/xe_exec_store.c
Use the tested package's identity and actual subtest list in the report.

## Evidence boundary and remaining work

V8 passed full native probe, primary/media GT initialization, ten engine
initialization jobs, four IGT queries and `xe_exec_store basic-store` with checked
GPU output on Linux 7.3.3. Normal unload then held during late BO destruction:
GuC rejected the PF MMIO handshake with INVALID_STATE before the clear request
was sent. Reload, second store and shutdown were not reached. See
`xe-mtl-vf-native-v8-results.md` for the evidence and source analysis.

V8.1 corrects this missing interface restoration; hardware confirmation of
unload and reload remains required. Successful basic-store is evidence of GPU
execution, not a display/compositor workload or every engine's full coverage.
The provided host captures flagged no new GPU error during v8; that does not
establish the final outcome of the earlier generation-207 comparison.

This branch is a full-probe experiment, not a production-support declaration.
The ordinary scheduler and recovery paths are deliberately exercised, not
replaced by diagnostic queue accounting or timeout suppression. Simultaneous
reset and PF update, suspend/resume, memory pressure, long workloads, repeated
unbind/rebind and native host VF use still need evidence. The mapper's inherited
indefinite response-uncertainty hold remains unsuitable for a final upstream
series; completing error propagation and ownership recovery remains work.

The final review series should separate the already-posted media coherency
workaround, required PF/platform enablement, the VF GGTT transport/lifetime
changes, and validation. Keep test branches reproducible; do not present the
accumulated diagnostic history as the upstream proposal.
