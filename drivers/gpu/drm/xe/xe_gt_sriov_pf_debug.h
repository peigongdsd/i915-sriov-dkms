/* SPDX-License-Identifier: MIT */
/*
 * Copyright © 2026 Intel Corporation
 */

#ifndef _XE_GT_SRIOV_PF_DEBUG_H_
#define _XE_GT_SRIOV_PF_DEBUG_H_

#include <linux/types.h>

struct drm_printer;
struct xe_gt;

#if IS_ENABLED(CONFIG_PCI_IOV)
void xe_gt_sriov_pf_debug_init(struct xe_gt *gt);

void xe_gt_sriov_pf_debug_record_config_push(struct xe_gt *gt, unsigned int vfid,
					     const u32 *klvs, u32 num_dwords,
					     int num_klvs, int err);
void xe_gt_sriov_pf_debug_record_service(struct xe_gt *gt, unsigned int vfid,
					 u32 action, u32 msg_len, u32 resp_size, int ret);
void xe_gt_sriov_pf_debug_record_mmio(struct xe_gt *gt, unsigned int vfid,
				      u32 opcode, int ret);
void xe_gt_sriov_pf_debug_record_ggtt_update(struct xe_gt *gt, unsigned int vfid,
					     u32 source, u32 pte_offset, u8 mode,
					     u16 num_copies, const u64 *old_ptes,
					     const u64 *new_ptes, u16 count, int ret);

int xe_gt_sriov_pf_debug_print_config(struct xe_gt *gt, unsigned int vfid,
				      struct drm_printer *p);
int xe_gt_sriov_pf_debug_print_service(struct xe_gt *gt, unsigned int vfid,
				       struct drm_printer *p);
int xe_gt_sriov_pf_debug_print_ggtt(struct xe_gt *gt, unsigned int vfid,
				    struct drm_printer *p);
void xe_gt_sriov_pf_debug_reset_ggtt(struct xe_gt *gt, unsigned int vfid);
#endif

#endif
