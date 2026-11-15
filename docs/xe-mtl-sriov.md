# Meteor Lake SR-IOV: consolidated implementation

This branch is the **production candidate**, not a production-ready release.
It consolidates the native VF implementation tested at `d50cc0c76e2af696f796c93684f5558f454f2543`
without the accumulated probe experiments. The clean tree must be tested in its
own right. Do not substitute it for a deployed, tested revision merely because
it has a shorter history.

The goal is native Xe on a Linux guest and on a host VF using the same path,
with Xe's normal allocation, interrupts, CT, engine submission, reset and power
management. Most of these facilities already existed. The essential addition
is the MTL VF GGTT access backend and its backing-memory lifetime integration.

## Platform facts and scope

* The tested machine is a ThinkBookX, Core Ultra 9 185H, PCI `8086:7d55`, PF
  `0000:00:02.0`, VF1 `0000:00:02.1`, Linux 7.3.3. Its graphics/media IPs are
  **1271 / 1300**. Common Xe platform discovery owns this identification; this
  series does not add a second numeric IP allowlist.
* Xe already selects **memory-based VF interrupts on MTL**. Restricted GGTT
  writes must not be described as absence of modern interrupt support.
* A calculated GGTT offset inside the VF BAR does not establish permission to
  write it. Native MTL VF updates use the PF relay. The original direct-BAR
  hang was a source hypothesis, not a captured failing instruction.
* The MTL PF uses firmware-permitted direct GSM access. Firmware denial or a
  missing GSM base is an error; there is no silent BAR fallback in that case.
* The primary and media GT share a tile GGTT. The PF must invalidate both
  applicable GTs before acknowledging a successful update.
* `Wa_22016122933` selects uncached CPU mappings for GuC-shared allocations on
  the affected standalone media GT. It does not disable CPU caching for every
  BO or describe the separate GT0 receive issue.
* The MTL descriptor also covers ARL-related identification in this source.
  The inherited commit title mentions ARL; this is **not ARL hardware evidence**.
  Do not infer support for other platforms from the ThinkBookX results.

## What each component does

| Component | Main code | Reason and boundary |
| --- | --- | --- |
| Legacy VF runtime information | `xe_gt_sriov_pf_service.c` | Supply the MTL register subset needed by existing VF implementations. |
| PF GSM access and allocation | `xe_ggtt.c`, `xe_gt_sriov_pf_config.c` | Write the firmware-approved GSM mapping and keep VF ownership and assigned GGTT bounds. |
| PF GGTT service | `xe_gt_sriov_pf_service.c`, `xe_guc_relay.c` | Decode the existing MMIO/CT ABI, validate PTEs/ranges, write with PF ownership, and acknowledge only after strict invalidation completion. |
| GSC/PXP provisioning and render whitelist | `xe_pci_sriov.c`, `xe_reg_whitelist.c` | Retain the platform enablement used by the earlier assigned Windows VF tests. Independent of native Linux interrupt implementation. |
| Media coherency workaround | `xe_guc_bo_wa_flags()`, `xe_wa_oob.rules` | Reuse allocation flags to apply uncached CPU access only to affected GuC-shared BOs. |
| Single-attempt transport | `xe_guc_mmio_send_recv_once()`, `xe_guc_ct_send_block_once()`, `xe_guc_relay_send_to_pf_once()` | A timeout is not cancellation. Do not replay a possibly applied mapping. Ordinary retry-capable callers retain their policy. |
| Native VF GGTT backend | `xe_gt_sriov_vf_update_ggtt()`, `vf_ggtt_map_bo()`, `vf_ggtt_fill()` | Coalesce contiguous DMA pages, preserve PAT bits, duplicate scratch PTEs, and use MMIO or CT according to the ordinary CT lifecycle. |
| Backing lifetime | `xe_ggtt_vf_unmap_bo()`, `xe_ggtt_vf_bo_mapped()`, TTM hooks in `xe_bo.c` | Clear mappings before backing destruction; keep mapped memory out of reclaim; retain scratch until holes and retired nodes no longer name it. |
| Late interface restoration | `xe_guc_softreset()`, VF GuC version handshake | Normal reset invalidates the cached PF relay handshake. Late MMIO cleanup restores the existing GuC interface before negotiating the PF relay. |
| Receive evidence and assistance | `xe_trace_guc.h`, `xe_guc_ct_recheck_rx()` | Optional trace events and one normal receive-worker pass at a single-attempt deadline. No request replay or periodic polling. This is not a proven root-cause fix. |
| Failure containment | `xe_ggtt_vf_fail()`, DRM ioctl checks | Reject new operations and release the shared mutex while retaining uncertain backing. The indefinite retained operation is a release blocker, not completed recovery. |

## Normal mapping and teardown

The existing allocator reserves a node in the VF's assigned GGTT window. The
backend sends a relative page offset and Xe-encoded PTE to the PF. Adjacent DMA
pages are represented by the ABI's replicate mode, at most 1,024 pages per
request. Discontinuous segments become separate requests. Scratch uses duplicate
mode: its DMA address must not advance across the range.

Before CT exists, the primary GT negotiates the GuC interface and PF MMIO relay.
With CT enabled, updates use the existing PF relay over CT. Once the normal
teardown disables CT, cleanup uses MMIO again, renegotiating after soft reset.
A failed active-CT request is never retried through MMIO.

PF completion includes both applicable GT invalidations and the final epoch
check. An epoch check detects stale work; it does not cancel work already sent.
Successful clears precede backing release. Scratch finalization clears holes
and already-retired nodes without overwriting still-live BO mappings.

## Choices made to keep the change small

* Reuse Xe's SG cursor, GGTT mutex, `drm_mm`, PAT selection, BO lifetime, GuC
  transport, memirq handler, scheduler and PM ownership. No alternate scheduler,
  interrupt implementation, persistent runtime-PM pin or application API.
* Reuse the existing PF GGTT message format rather than inventing a private ABI.
* Keep all old diagnostic branches reproducible. Do not compile their temporary
  BOs, deliberate `-95` stops, diagnostic resets or bootstrap phase flags here.
* Keep `mtl_vf_native=1` as an explicit opt-in until failure handling is complete.
  The removed `mtl_vf_bootstrap_test` and `mtl_vf_relay_test` parameters must not
  be passed to this branch. With native mode off, MTL VF probing returns
  `-EOPNOTSUPP` before GGTT initialization.
* Detailed allocation/map/reset logs use dynamic debug. The probe identity is
  `mtl-native-clean-v1`. The experimental always-on interrupt counter is gone.
  Trace descriptor/page reads are conditional on enabled trace events.
* Retain the bounded receive recheck as a separate, reviewable change because
  v8.2 teardown actually needed it. No claim of zero overhead or measured power
  improvement is made: PF relay operations and invalidations have a real cost.

## Source and series provenance

The base is `strongtz/i915-sriov-dkms` commit `bea7187` (resolve the full ID with
`git rev-parse bea7187`). The first seven changes preserve the authors and
messages of `peigongdsd/i915-sriov-dkms` through `e9130af`: runtime registers,
GSM, PF relay, color-cache keying, platform capability, PF invalidation and
GSC/PXP provisioning. They are followed by the media coherency workaround,
single-attempt transports, one consolidated native VF change, receive
instrumentation/assistance, strict PF checks, tests and this documentation.

The native code derives from `d50cc0c`, including the v8.1 interface restoration.
The PF admission/completion corrections derive from the earlier `02acd04`
review branch; the native experiment history had not inherited them. The
numeric IP gate from intermediate experiments is deliberately absent.

Earlier comparisons with `peigongdsd/master` and `xbomber/xe-sriov-mtl-arl`
informed the platform work. This branch preserves the actual source lineage
rather than claiming those moving branches are identical or that this series
is already upstream. Existing commit authorship is retained. Upstream submission
still needs maintainer review and valid contributor sign-offs.

See [validation and evidence](xe-mtl-sriov-validation.md) and
[release blockers](xe-mtl-sriov-readiness.md). A clean commit history is not a
substitute for the remaining recovery work.
