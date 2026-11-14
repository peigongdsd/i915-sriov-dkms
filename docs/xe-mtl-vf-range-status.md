# MTL native Xe VF: guest-first range backend

## Target and current scope

The first bring-up target is a **fully working native Xe VF inside the Linux
guest**: complete probe, command submission, and correct teardown/recovery.
Native Xe binding to the VF on the host comes afterward. Preserve the working
host PF/VFIO configuration while developing the guest driver.

This extension starts at the clean PF review series
`707c15cae5381b94118d03e7c277f2a76c991ce4`. It implements the early remote
range-update core and explicit failure progress. It is **not yet connected
to the GGTT allocator or BO destruction**. Both native VF admission gates
remain intact; there is no new module option to bypass them. Building this
branch therefore does not produce a guest with full native graphics.

The successful diagnostic remains frozen at
`292dec2bfa0d121df72012cb43f14c437edf5146`. Its indefinite holds, reset
suppression, logging and deliberate probe stop are not copied into this
backend. Its tested wire encoding and single-attempt behavior are reused.

## Implemented contracts

`xe_guc_mmio_send_recv_once_locked()` reuses the ordinary GuC transport
parser and waits for a BUSY response to finish without resending. It does
not replay on a lost response or firmware RETRY. The ordinary API retains
its mutex ownership and existing bounded retry behavior. Callers of the
new primitive hold the existing `vf_mmio_lock` across their transaction.
No second transport mutex or workqueue is introduced.

`xe_gt_sriov_vf_ggtt_update()` accepts one VF-relative range with either
consecutive DMA pages or a repeated PTE. It:

- Restricts the helper to the primary GT of an MTL VF before CT is enabled.
- Checks the full range against the VF allocation and wire offset width,
  then checks PTE permission/attribute bits and 46-bit DMA overflow before
  sending. VFID is not accepted from the VF; the PF supplies ownership.
- Negotiates the existing PF MMIO relay ABI once per stream. The GuC
  interface must already have been negotiated by ordinary VF bootstrap.
- Splits at the existing 1024-page replication limit, retaining PAT bits.
  Callers must split scatter-gather discontinuities and attribute changes
  into separate runs; automatic BO/resource-cursor integration is pending.
- Returns the acknowledged leading page count and the following submitted
  batch whose completion is uncertain. Pages beyond both were not sent by
  this call. A failed clear has exactly the same conservative semantics.
- Latches the first protocol/transport failure. Further calls through this
  state send no update, handshake or attempted rollback. There is no API
  to clear that error and pretend the old request was cancelled.

For example, if the second request in a 2049-page run times out, the result
is `completed=1024, uncertain=1024`; the last page was not submitted. The
acknowledged prefix is still mapped, and the uncertain batch may arrive
later. Neither range can be treated as automatically rolled back. A later
rejected call reports no work of its own; it does not erase earlier results
or discharge earlier ownership obligations.

This state is protected by the existing GuC MMIO mutex. The calling layer
must still own the BO/node, preserve its DMA mapping and device resources,
and exclude reset, reprovisioning and CT transitions. The helper cannot
establish those caller-side conditions by checking `ct_enabled`. Unrelated
GuC MMIO callers are not stopped by the latched GGTT error; an owning
recovery layer must stop protocol transitions too, since late replies may
still overwrite scratch registers.

The cached negotiation belongs to one uninterrupted pre-CT bootstrap
phase. Reuse after a reset or CT transition is not supported, even after
successful updates. The future lifecycle layer must invalidate and renew
negotiation correctly; there is no post-reset reuse API in this extension.

## Why the allocator is not connected yet

`xe_ttm_tt_unpopulate()` unmaps the scatter-gather DMA backing and frees
the TTM pages. Ordinary GGTT removal is reached from the later
`xe_ttm_bo_destroy()`. Replacing that final node clear with a remote request
would put the clear after the lifetime boundary it must protect.
The [pinned upstream TTM source](https://github.com/torvalds/linux/blob/7e1392a42ea288d70a266f6553fe06f57f8647ea/drivers/gpu/drm/ttm/ttm_bo.c#L249)
confirms the ordering: `ttm_bo_release()` cleans up the TT/resource before
calling the driver destructor, including its delayed-delete path. This
source comparison is not a new trace of the guest's exact kernel.

The mapping lifetime must therefore be integrated before unpopulation and
through failed probe, eviction and final release. An errno alone cannot
express permission to free memory after a partially applied request. The
new result describes the affected ranges; it does not retain the BO,
cancel PF work, fence TTM release or keep DRM-managed resources alive.

The inspected `VF2GUC_VF_RESET` ABI describes resetting GuC's VF state.
It does not specify draining every relayed PF request or cancelling an
already queued PF worker. The v5.1 consumer-reset/renegotiate/clear sequence
started with all maps acknowledged, and therefore cannot supply the
missing uncertain-request guarantee.

Before connecting this backend, choose and establish one completion or
quiescence contract covering firmware-held requests, PF workers, PTE
writes and both GT invalidations. Do not implement recovery by zeroing the
sticky error, sleeping, replaying, leaking references or skipping DMA
unmapping. A negative PF response can follow a completed write but failed
invalidation; it is not necessarily a pre-submission rejection.

## Offline validation

`CC=<compiler> python3 tests/run_xe_mtl_vf_ggtt.py` compiles the actual MMIO
transport and the whole new backend with ASan/UBSan against scripted MMIO
and PF writes. The state definition and ABI constants come from driver
headers. Coverage includes:

- Multi-request contiguous maps and repeated-PTE clears, PAT retention,
  caller-split discontinuities, and correlation-value wrap.
- Invalid PTEs, VFID bits, zero/oversized ranges, DMA overflow, wrong GT or
  platform, and active CT, with no premature transmission.
- Nine failure types at each of the first, middle and last request:
  cleared/nonzero scratch timeout, RETRY, BUSY timeout, wrong correlation,
  wrong completion count, PF failure after writes, migration rejection,
  and a delayed PF write after timeout.
- Exact acknowledged/uncertain ranges, no later rollback or replay,
  failed negotiation without a PTE request, BUSY success without replay,
  and preservation of ordinary GuC retry bounds.

The delayed-write case deliberately applies the old PTE update after the
helper has returned failure. The test checks that the backend did not
send a new operation that assumes cancellation. It does not prove that
kernel memory is retained: allocator and TTM integration are absent.

The original four PF suites also pass. Xe and compatibility modules build
against local Linux 7.3.4 with `KCFLAGS=-g`; the hardware diagnostic used
7.3.3. These are software checks only. No guest or host driver was loaded,
and the new branch has no hardware result.

## Remaining implementation order

1. Establish remote completion/drain semantics and integrate ownership
   before TTM DMA unpopulation, including failed probe and reset.
2. Connect range batching to Xe's resource cursor, normal mapping and
   scratch clears, with error propagation through all callers.
3. Implement the normal-operation transport and its transition from early
   MMIO; native CT communication succeeding in v5.1 did not test CT GGTT
   updates. Reuse existing Xe transport and fences where their semantics fit.
4. Complete guest probe and validate submission and lifecycle operations.
   Only after guest correctness is established should host-native VF
   binding become a test target.

No new hardware experiment is requested for this preparatory extension.
