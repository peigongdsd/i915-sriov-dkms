# Independent ADL-P timestamp-workaround review

Reviewed source base `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9` and the unmodified accepted patch `38631a7bce195b88814b93bf2b6d3e48c827fef2`, stored at `patches/adlp/0001-drm-xe-do-not-emit-timestamp-workaround-twice.patch`. Read-only review; no source changes made by reviewer.

**No blocking source-review finding.** This narrowly removes duplicate/wrong-location emission of `Wa_16010904313`. It is a justified baseline correction, not an established fix for the specific reported ADL-P VF failure.

## Applicability

- `xe_pci.c:263` selects Xe_LP (graphics 1200) for ADL-P and already enables SR-IOV. `xe_wa_oob.rules:2` enables this workaround on graphics 1200–1210.
- `xe_lrc.c:1133` currently emits the same triple `MI_LOAD_REGISTER_MEM` timestamp sequence when invoked for render, compute, copy, video decode, or video enhancement. Both `xe_lrc_setup_wa_bb_with_scratch()` and the render/compute callback list of `setup_indirect_ctx()` include it.
- `gt_engine_needs_indirect_ctx()` at `xe_lrc.c:87` guarantees the indirect allocation for render/compute engines whenever this WA is active. Therefore removing it from the post-restore WA batch does not remove its required execution: the indirect context retains it.
- `xe_gt_record_default_lrcs()` at `xe_gt.c:385` creates a kernel exec queue, runs `emit_wa_job()`, switches to a NOP queue, then copies default LRC state. `xe_lrc_ctx_init()` sets up both workaround locations for these initial queues. The correction is therefore relevant before a VF has successfully captured its first default render LRC.
- This timestamp workaround has no VF exclusion; the neighboring utilization helper has a separate intentional VF exclusion. The accepted change applies to both PF/native and VF render/compute contexts and preserves the existing copy/video placement. It is not a new VF protocol or i915 migration.

## Patch consistency

All six setup callback signatures and the common function-pointer type gain the `indirect` argument consistently. The normal WA-batch state is aggregate-initialized, so its omitted boolean is reliably false; `setup_indirect_ctx()` explicitly sets true. Render/compute emit only indirectly; copy/decode/enhancement only in the ordinary WA batch; the WA enable predicate still gates everything. Other callback bodies are unchanged.

`git apply --check` against the untouched ce1e base passed. The patch is the accepted Intel-reviewed change, not a hand-reimplemented equivalent. No behavioral hardware test was performed in this review.

## Validation boundary

A build of the affected Xe translation unit checks the callback-signature refactor. Hardware acceptance must still show the ADL-P VF completing the first default-LRC capture, executing basic render/copy/video submissions, and surviving repeat guest start/stop. If the same `emit_wa_job`/NOP capture error remains, collect the earliest GuC submission and engine-fault data rather than adding another speculative workaround. An existing ring-write visibility barrier should be kept independently; this patch does not replace it.
