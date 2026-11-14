/* SPDX-License-Identifier: MIT */
#ifndef _XE_GT_SRIOV_VF_GGTT_H_
#define _XE_GT_SRIOV_VF_GGTT_H_

#include <linux/types.h>

struct xe_gt;

/**
 * struct xe_gt_sriov_vf_ggtt_result - Progress of one range update.
 * @completed: leading pages with acknowledged update and PF invalidation.
 * @uncertain: following pages submitted without a valid completion reply.
 *
 * Pages after these two ranges were not submitted by this call. A failed
 * call may have modified both ranges. This describes only the current call,
 * not earlier mappings or whether consumers can still use those mappings.
 */
struct xe_gt_sriov_vf_ggtt_result {
	u32 completed;
	u32 uncertain;
};

int xe_gt_sriov_vf_ggtt_update(struct xe_gt *gt, u32 page, u64 pte, u32 count,
			     bool replicate, struct xe_gt_sriov_vf_ggtt_result *result);

#endif
