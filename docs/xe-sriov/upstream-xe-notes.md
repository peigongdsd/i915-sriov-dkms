# Upstream Xe SR-IOV: ADL-P source audit

Audited 2026-10-02. Upstream Linux checkout: `sources/linux`, commit `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`, committed 2026-10-01T12:47:16-07:00. All Linux paths and line numbers below refer to this immutable snapshot. No runtime changes or hardware tests were performed.

## Status and what Intel actually enabled

`drivers/gpu/drm/xe/xe_pci.c:263` defines ADL-P with `.has_sriov=true`, `.require_force_probe=true`, 39-bit DMA, 48-bit GPU VA, one GT per tile, LLC and cached page tables. ADL-S/N and TGL have the same important properties. Raptor Lake U is an ADL-P subplatform. Therefore current upstream is not missing the basic ADL enablement flag.

Intel commit [2e761039985271a69bf6eada8f236701f8594638](https://github.com/torvalds/linux/commit/2e761039985271a69bf6eada8f236701f8594638), authored 2025-07-22, promoted ADL/ATSM from the CI topic branch and `CONFIG_DRM_XE_DEBUG` gating. Its rationale was that CI had already exercised these platforms, and that `require_force_probe` remained an explicit guard. This supersedes the June 2025 support-status question saying ADL SR-IOV was CI-only.

Intel commit [6983ea9cd720fdd409b4944caf9605731323bb8d](https://github.com/torvalds/linux/commit/6983ea9cd720fdd409b4944caf9605731323bb8d) adds TGL similarly; Intel specifically says TGL was used during feature development but lacked official SR-IOV CI coverage.

That is development availability, not production support. Intel's Matt Roper reiterated in [2026-09-30 review](https://lkml.rescloud.iu.edu/2609.3/17001.html) that Xe1/ADL force-probe support targets driver developers and might lack hardware workarounds. His statement should not be conflated with the separately true `.has_sriov=true` status.

MTL descriptor `xe_pci.c:384` has no `.has_sriov` and is also force-probe. This is a distinct enablement problem. ADL's 39-bit DMA versus MTL's 46-bit DMA does not establish a DMA bug; supported upstream ADL/TGL descriptors deliberately use 39 bits.

## PF/VF initialization and actual mechanisms

1. `xe_sriov.c:62` recognizes VF through `VF_CAP_REG` and PF through PCI/runtime readiness, conditional on platform capability. A hardware-advertised capability with `has_sriov=false` is explicitly suppressed.
2. ADL-P PF selects `i915/adlp_guc_70.bin` with recommendation 70.44.1 (`xe_uc_fw.c:117`). Filename major selection and recommended version are distinct; inspect the loaded firmware, not package age. VF does not upload its own independent GuC.
3. VF minimum GuC interface is 1.1 for TGL through PVC (`xe_gt_sriov_vf.c:170`); newer families require at least 1.2 for GMD_ID discovery. PF/VF relay ABI currently negotiates 1.0 (`abi/guc_relay_actions_abi.h:20`, `xe_gt_sriov_vf.c:826`). Firmware release number, GuC submission ABI, and PF/VF relay ABI are separate version spaces.
4. The PF supplies fuse/runtime register data; TGL/ADL use the gfx1200 runtime table (`xe_gt_sriov_pf_service.c:20`, `:118`). VF MMIO reads not marked VF-accessible go through its cached virtual view (`xe_mmio.c:231`). Topology is therefore not simply unrestricted guest MMIO probing.
5. ADL already receives the required PF `VIRTUAL_CTRL_REG.GUEST_GTT_UPDATE_EN` write (`xe_gt_sriov_pf.c:140`). PF assigns GGTT space using PTE VFID bits and the PRESENT bit (`xe_ggtt.c:943`). VF uses only its provisioned GGTT interval (`xe_ggtt.c:411`), then direct GSM MMIO PTE updates (`xe_ggtt.c:238`). There is an explicit posted-write read and TLB invalidation (`xe_ggtt.c:577`).
6. System memory buffers use DMA API mappings (`xe_bo.c:403`); the device applies the configured DMA mask (`xe_device.c:702`). A trace must distinguish CPU physical addresses, DMA/IOMMU IOVAs, GGTT addresses, and PPGTT GPU VAs. Increasing 39 to 46 is not a justified repair.
7. ADL-P VF IRQ is supported without memory-based interrupts: `vf_irq_reset` has the gfx<1210 register interrupt path (`xe_irq.c:627`). The warning that migration requires memory-based IRQ says migration is disabled; it does not say basic SR-IOV execution is unsupported.

## Earliest GPU execution is the right localization point

`xe_gt_record_default_lrcs()` (`xe_gt.c:385`) creates a kernel queue with `vm=NULL` (`:409`), submits the workaround/state initialization batch (`:417`), then submits a NOP on another queue (`:424`) to force the first context image to be saved. This becomes the template for future contexts.

The batch is from the kernel BB pool and GGTT mapped. `get_ppgtt_flag()` (`xe_ring_ops.c:272`) returns zero for `vm=NULL`. Accordingly, an `emit_wa_job -ETIME` during VF probe is not evidence of a failed userspace VM_BIND or Mesa PPGTT mapping: the basic GGTT/context/GuC/interrupt path already failed before that.

One actual source difference worth an isolated experiment: i915 initializes PPGTT registers even for a GGTT context by using its GGTT alias VM (`sources/i915-sriov-dkms/drivers/gpu/drm/i915/gt/intel_lrc.c:912`, `:972`); Xe only sets PPGTT root when a VM exists (`xe_lrc.c:1526`). That does **not** prove the NULL root is wrong: these jobs are GGTT, restore inhibit and GuC handle other context state. If implicated by fault address/register captures, use an Xe scratch/kernel VM and existing page-table helpers rather than importing i915 VM lifetime code.

The [ADL-S UHD770 first-person issue #454](https://github.com/strongtz/i915-sriov-dkms/issues/454) reports VF `emit_wa_job -ETIME`, PF-attributed IOMMU write fault and engine CAT error while i915 works. It corroborates the stage of failure on a related Xe_LP platform, not the cause on ADL-P. Its assertion that only 46-bit/newer hardware is enabled is contradicted by upstream source. “Next page table ptr is invalid” here is a DMAR/IOMMU report, not by itself a GPU PPGTT root diagnosis. PF requester identity during the VF's first job makes address ownership/VFID/context switching worth tracing, but hardware requester routing can also differ by transaction type.

## Two current context changes to account for

### Clean NULL context reset: already upstream

[61e7649a1a253609769063a30018e68b970324d6](https://github.com/torvalds/linux/commit/61e7649a1a253609769063a30018e68b970324d6), Intel, March 2026, explains that another VF's modified context might remain when capturing the default image. It adds a deliberately impossible watchdog condition so GuC resets the engine before capture.

Current `xe_gt.c:377` passes `force_reset=true` for VF initial WA jobs. `xe_ring_ops.c:306` emits the watchdog and GGTT semaphore. Therefore, on recent kernels the earliest submission includes an intentional reset; seeing an engine-reset event there is not by itself the defect. Failure to complete/recover, CAT errors, or repeated reset storms are defects. A narrow diagnostic split is to trace this sequence separately from subsequent workaround instructions and fence signalling. Do not simply delete it as a fix: that reintroduces contaminated default contexts.

### ADL indirect-context offset: pending and disputed

[c9dfd66cb91ef32f76e51f75e315c07907df2b85](https://github.com/torvalds/linux/commit/c9dfd66cb91ef32f76e51f75e315c07907df2b85), Intel, September 2025, removed explicit default-offset programming while extending indirect contexts to more engines, on the premise the hardware default was already appropriate.

Current `xe_lrc.c:1452` still leaves INDIRECT_CTX_OFFSET at its inherited value. The September 30, 2026 proposal to restore programming reports ADL Vulkan/ANGLE hangs. [Intel's review](https://lkml.rescloud.iu.edu/2609.3/17001.html) disputes the stated mechanism and requests default-LRC dumps. Roper explains expected reset value 0xd, capture by restore-inhibit then context switch, and inheritance into real contexts. Inspect dword 0x17 in the register-state portion/default-LRC dump, respecting the dump's offsets; compare before and after save. This is a concrete fresh context-state lead, not an accepted SR-IOV fix. Also the proposed `GRAPHICS_VER < 20` condition is broader than the ADL-only title, so do not copy it indiscriminately.

## CCS distinctions and avoiding unnecessary legacy ports

Compute Command Streamer (CCS engine) and Compression Control Surface (CCS metadata) are different things.

Upstream `graphics_xelp` (`xe_pci.c:57`) includes RCS0 and BCS0, not CCS0. Media engines are added separately. Its CCS hardware-enable rule starts at gfx1255 (`xe_hw_engine.c:454`), leaving ADL compute-engine support disabled.

Current strongtz snapshot adds experimental Xe_LP CCS0 only under `xe.xelp_enable_ccs=true` and then reduces GPU VA to 47 bits (`sources/strongtz-current/drivers/gpu/drm/xe/xe_pci.c:884`, `:971`). This opt-in is not an upstream module parameter. It is potentially relevant to a Windows driver expecting CCS engine resources, not automatically a cure for a Linux upstream VF probe failure.

i915 explicitly adds GEN12_RCU_MODE to its GuC ADS register-save list when CCS is present (`sources/i915-sriov-dkms/drivers/gpu/drm/i915/gt/uc/intel_guc_ads.c:395`). Xe's RTP-generated `hwe->reg_sr` entries are already serialized into ADS (`xe_guc_ads.c:851`). If adding a CCS enable rule via that modern mechanism, an additional i915-style manual ADS entry may be redundant; inspect the actual resulting list/reset domain instead of porting by symbol-name absence.

i915 fork's GUC_WA_RCS_CCS_SWITCHOUT bit is restricted to gfx12.70–12.74 and the fork's enable switch (`.../intel_guc.c:321`). It is absent in upstream Xe, but it is not an ADL-P workaround. Xe retains POLLCS for pre-XeHP (`xe_guc.c:202`).

i915 GGTT binder/relay condition is media13.0 plus unavailable direct stolen access (`sources/i915-sriov-dkms/drivers/gpu/drm/i915/gt/intel_gtt.c:24`), so the MTL workaround is not an ADL-P architectural gap. ADL i915 also uses direct GGTT writes. Keep MTL's binder investigation separate.

## Recommended experiments, ranked by diagnostic value

1. Pin exact host/guest driver commits and firmware; classify whether failure is during VF probe, first user submission, Windows device initialization, or later rendering. “Recent” cannot distinguish NULL-context reset changes or DKMS CCS policy.
2. One VF, host driver binding first if reproducible there: instrument initial LRC/BB/ring/HWSP DMA addresses, GGTT offsets, PF-owned PTEs and VFID, GuC context ID and actual engine. Match the *first* DMAR address to these objects. Trace expected watchdog reset, context save, subsequent WA execution and completed sequence number separately. This separates mapping/ownership, context-state and interrupt failures.
3. Compare captured default LRC register values with i915 and the expected reset defaults, especially INDIRECT_CTX_OFFSET and PDP root, but do not assume either is causal. On a failed probe capture before cleanup, since a completed default-LRC file may never exist.
4. Test independent queue variants (GGTT NOP; same with scratch Xe VM; actual WA batch; reset sequence) to identify the first failing transition. Retain current Xe abstractions. These are diagnostic patch ideas, not validated fixes.
5. If failure is Windows-only after a Linux VF succeeds, evaluate the separate CCS0 exposure/enable/reset contract with 47-bit VA using the current DKMS work as a controlled comparison. Do not mix that with compression modifiers.
6. For Linux rendering after probe succeeds, investigate Mesa capability and AuxCCS support then. Kernel AuxCCS handling recently changed in March 2026: [quiesce traffic](https://github.com/torvalds/linux/commit/458b1e64e7c0594cca8515fae8996bc52619d2f6), [wait for invalidation](https://github.com/torvalds/linux/commit/cd1a516234ebb049007ce20c6b6e76936b29bade). These cannot fix a kernel module failing its initial golden-LRC job before Mesa starts.

No source review alone settles the user's ADL-P failure. The highest-value result is a narrower experiment set and rejection of unsupported broad explanations (39-bit DMA intrinsically broken; MTL binder required on ADL; Mesa causing pre-probe kernel failures).

## Authoritative Xe development tree and issue tracker follow-up

The project URL provided by the user is reachable directly via HTTPS/REST (GitLab project ID 13578), even where the web-search tool returns an internal error. The default `main` branch is a README pointer; the actual development branch is `drm-xe-next`. Verified current heads:

- `drm-xe-next`: `cf4171a20d13918e07ed01a1e01a6b546825c601`, 2026-10-01, GuC suspend-pending race fix.
- `drm-xe-fixes`: `72207463f7a4a6818a88f4ef57802b42da534301`, 2026-09-28, keep VF LMEM BAR small when no VFs enabled (dGPU resource allocation).
- `topic/xe-for-CI`: `b275cb3f07a7ab3ef3bd419db86bd42fa95dcedb`, 2026-07-09.

Source `xe-next-pci.c` fetched through the official API confirms the same relevant platform split on the latest next branch: ADL-P has SR-IOV and force-probe; MTL descriptor still lacks SR-IOV; ARL IDs select that MTL descriptor. These were not inferred solely from Torvalds' tree. The newest 100 path-scoped commits were saved to `xe-next-latest-commits.json`. Full-history inspection below identifies a substantive XeLP timestamp-workaround fix and MTL/ARL media coherency fix in this development branch; the generic GuC/ULLS replay changes do not independently establish an ADL SR-IOV repair.

Saved issue searches include ADL, SR-IOV, sriov, emit_wa_job, Windows, Hyper-V, and IOMMU. Title search is needed because otherwise many unrelated platform logs contain SR-IOV text. A search result or same error signature is not sufficient to assign causality.

Read [work item 8354](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/8354) including discussion: this is a VF stress-test `emit_wa_job -ETIME` issue on WCL, later PTL/NVL, **not ADL-P**. It was automatically closed on 2026-09-09 after being unseen for 21 days; no identified fix is given. Item 3075 reports the same timeout during dGPU wedged testing in 2024; also not ADL-P. Item 6420 is an N100 display/boot blank-screen report, not VF passthrough. They should not be repurposed as confirmation of the user's failure.

GitLab REST `/issues/IID/notes` currently returns 401 unauthenticated, but the public web UI endpoint `/drm/xe/kernel/-/issues/IID/discussions.json` supplies the public discussion. File `xe-item-8354-discussions.json` preserves this read. No account authentication or tracker writes were performed.

Further full-discussion findings:

- [6489](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/6489): November 2025, i5-12500H ADL-P heavy-3D stutters under Xe but not i915. Intel's Jani Nikula says i915 is the supported driver and Xe/ADL-P was a development vehicle. This is a support-policy statement, not proof SR-IOV cannot work.
- [7584](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7584): Mesa CI ADL-P/RPL-U Vulkan hangs, initially reported as 6.17 to 6.19 regression. Crucially, on 2026-04-09 the reporter first implicated `c9dfd66cb91e`, then withdrew confidence after reproducing on its parent. July 1 reports persistence in 7.1.1. Thus the bisect does not prove the indirect-context-offset patch is the cause. These are bare-metal rendering failures, not VF-probe failures. The mentioned partial fix is [7596459f3c93d8d45a1bf12d4d7526b50c15baa2](https://github.com/torvalds/linux/commit/7596459f3c93d8d45a1bf12d4d7526b50c15baa2), correcting idledly unit conversion; it was already present in that still-failing 7.1.1 report.
- [7352](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7352) and [7733](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7733) really do show ADL-P RVP SR-IOV CI failures, but in the `xe-vfio-pci` FLR/reset path (NULL dereference), not initial render execution. These distinguish VFIO migration/reset plumbing from the guest renderer, and show that upstream ADL-P CI use is real despite the end-user support limitation.

## Additional confirmed fixes found through complete commit-history traversal

The following are established changes, useful for testing what a report means by “recent.” They are already present in the pinned October 2026 upstream source; none proves the cause of a failure there.

- [051be4913397](https://github.com/torvalds/linux/commit/051be49133971076717846e2a04c746ab3476282), January 2026, fixes XeLP Wa_18022495364 programming the wrong register: CS_DEBUG_MODE1 becomes CS_DEBUG_MODE2. [0df99689eb79](https://github.com/torvalds/linux/commit/0df99689eb790bcad3ad82b38fa4ce1cbf3cffa3), April 2026, fixes the same workaround's missing engine-relative MMIO bit in MI_LOAD_REGISTER_IMM. Current `xe_lrc.c:1241` contains both corrections. These concrete errors warrant screening older reports before proposing further speculative default-context changes.
- [f2f90989ccff](https://github.com/torvalds/linux/commit/f2f90989ccff2d010472d47e4e62f7afe8ce67ff), March 2025, explicitly fixes VF workaround initialization by performing register read/modify/write on the engine with MI_MATH instead of CPU reads that fail for a VF. Thus current Xe already has a modern VF-safe workaround execution mechanism; importing i915 CPU-MMIO assumptions would regress that property.
- [e904c56ba6e0](https://github.com/torvalds/linux/commit/e904c56ba6e0d4eff5f48a70356fd5d764c2a966), February 2026, replaces VF GGTT balloon objects with direct GGTT start/size initialization. Its message says the previous scheme worked but was complicated. Missing old ballooning objects is therefore an intentional modernization, not absent virtualization support.
- [1b81ed612e12](https://github.com/torvalds/linux/commit/1b81ed612e12ea9df8c5cb6f0ddd4419fd0b8ac8), April 2026, explicitly closes ADL-P work item 7352. `xe-vfio-pci` had initialized fields needed for reset only when migration was supported, causing a NULL dereference on ADL-P's non-migratable VF. It decouples VF initialization from migration initialization. This is a confirmed ADL-P SR-IOV defect and fix, with a precisely different failure signature from an `emit_wa_job` GPU timeout.
- [d1643db3b037](https://github.com/torvalds/linux/commit/d1643db3b037b57f2af7f85c3821d6fe69c492f6), August 2026, ensures the VF calls `xe_guc_submit_enable()` and applies render/compute scheduling policy before recording default LRCs. The actual policy KLV is conditional on `CCS_INSTANCES` (`xe_guc_submit.c:356`), so this is relevant to CCS-enabled platforms/experiments, not a strong default-upstream ADL-P explanation where CCS0 is absent. [26caeae9fb48](https://github.com/torvalds/linux/commit/26caeae9fb482ec443753b4e3307e5122b60b850) explains modern GuC dual-queue/yield policy. For MTL, audit this current mechanism before proposing the old RCS_CCS_SWITCHOUT flag as a replacement.

The post-migration LRC re-creation fixes `c692ae39e9fd` and `f3fb5f1ebbf3` concern contexts raced by VM migration; they should not be promoted to explanations for the first cold-boot ADL-P VF probe without evidence of migration/recovery.

## Accepted development fixes not yet in the pinned mainline

These are stronger starting patches than an unconfirmed reconstruction of older i915 context code. Exact upstream patches are preserved in `upstream-patches/`; both pass `git apply --check` on pristine `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`, without adaptation or dependencies on each other.

1. [38631a7bce195b88814b93bf2b6d3e48c827fef2](https://gitlab.freedesktop.org/drm/xe/kernel/-/commit/38631a7bce195b88814b93bf2b6d3e48c827fef2), authored September 25, accepted October 1, 2026: **Do not emit Wa_16010904313 twice**. The original XeLP workaround was incorrectly rebased and emitted both in the indirect context and in the post-restore workaround batch. The documented requirement is RCS/CCS in the indirect context only, and BCS/VCS/VECS in the post-restore batch only. The fix passes a location boolean through existing BO-setup callbacks. It directly repairs an ADL-family context-restore defect using the current Xe abstractions. It is a justified first backport; it is not yet proven to repair the user's particular VF failure, especially if the failure precedes indirect-context execution.
2. [d5b0bf3f37f152583a884c696cf6caa152aa7ed5](https://gitlab.freedesktop.org/drm/xe/kernel/-/commit/d5b0bf3f37f152583a884c696cf6caa152aa7ed5), accepted September 24, 2026: **Implement Wa_22016122933**. Standalone media GT 13.00 (MTL/ARL) needs CPU-uncached GuC-shared memory. Current Xe missed an i915 workaround; stale cached G2H CTB lines delayed already-completed firmware acknowledgements by about 2.3 seconds. It uses the existing `XE_BO_FLAG_NEEDS_UC` and OOB media-version rule for CTBs, GuC logs, ADS, SLPC and engine activity buffers. The author reports two ARL machines, over 10 million invalidations, and six combined weeks without stalls after the fix. This is a concrete modern fix with independent hardware evidence, not full MTL SR-IOV enablement. The commit explicitly leaves i915's additional media LRC/ring coherency scope for possible follow-up.

Avoid accidentally duplicating fixes with different commit identities between `drm-xe-next` and mainline:

- Development `136360290f31` (order ring writes before WC ring-tail publication) already exists in pinned mainline as `9f83c94469ff0fa37274b873ba24922e02531fa7`; `xe_lrc.c:1860` already calls `xe_device_wmb(xe)`. It is an important version check, not another missing backport.
- Development `77f704158f09` (PAGE_SIZE scatterlist segments on Xen PV, i915-equivalent fix for bounce-buffer coherency) already exists as mainline `141008dec73521ccf64878517460cec8b3297251`; current `xe_bo.h:594` contains the Xen PV check. Its platform scope can help interpret older Qubes reports; it does not establish a general SR-IOV failure.

The separate pending INDIRECT_CTX_OFFSET proposal should remain a controlled diagnostic experiment after these accepted changes. The proposed offset encoding is `0xd << 6` (`0x340`) in bits [15:6], not a literal register value `0xd`; do not spread one render-engine observation to all engine classes or platforms below graphics version 20.

## Full-history acquisition and scope, completed 2026-10-02

`sources/xe-development` is a no-checkout, blob-filtered Git repository with **full commit and tree history**, not a shallow clone. It was seeded with Torvalds' full repository for efficient object transport, then fetched all official `https://gitlab.freedesktop.org/drm/xe/kernel.git` branch refs and tags. `origin` is the authoritative Xe remote; `linux-upstream` records the Torvalds transport source. Source blobs are retrieved lazily when examining patches; filtering file contents does not truncate commit ancestry.

Verification: `git rev-parse --is-shallow-repository` returned false; complete commit traversal succeeded. The snapshot has 16 official Xe branches and 226 advertised tags, 1,490,234 commits reachable from official branch refs including Linux ancestry, and 1,502,905 across all fetched refs including tags and Torvalds. Advertised exact refs are preserved in `xe-full-advertised-refs.txt`, local official branch refs in `xe-full-official-refs.txt`.

`xe-complete-path-history.tsv` indexes all 21,754 non-merge commits touching `drivers/gpu/drm/xe` across these refs, including historical rebases. Scoped searches produced 562 SR-IOV/PF/VF matches, 682 ADL/XeLP/MTL/ARL matches and 47 VF-context/IRQ matches (duplicate/cherry-picked changes are retained). `xe-development-unmerged-history.log` records the 240 commits reachable from next/fixes/CI but not the pinned Torvalds branch by identity; as the ring-barrier example shows, that does not imply 240 unique unapplied patches.

These are full-history acquisition and targeted commit-message/diff traversal, **not a claim that all Linux commits or all 21,754 Xe diffs were manually reviewed**. The source conclusions above were checked at the pinned source and the relevant authoritative development commits. Repository and public tracker were read only; no external messages or changes were made.
