/* SPDX-License-Identifier: MIT */
/*
 * Copyright © 2023-2024 Intel Corporation
 */

#ifndef _XE_GT_SRIOV_PF_SERVICE_H_
#define _XE_GT_SRIOV_PF_SERVICE_H_

#include <linux/errno.h>
#include <linux/types.h>

struct drm_printer;
struct xe_gt;
struct xe_gt_sriov_pf_ggtt_token;

int xe_gt_sriov_pf_service_init(struct xe_gt *gt);
void xe_gt_sriov_pf_service_update(struct xe_gt *gt);

int xe_gt_sriov_pf_service_print_runtime(struct xe_gt *gt, struct drm_printer *p);

#ifdef CONFIG_PCI_IOV
int xe_gt_sriov_pf_service_process_request(struct xe_gt *gt, u32 origin,
					   const u32 *msg, u32 msg_len,
					   u32 *response, u32 resp_size,
					   const struct xe_gt_sriov_pf_ggtt_token *token);
bool xe_gt_sriov_pf_service_has_ggtt_relay(struct xe_gt *gt);
bool xe_gt_sriov_pf_service_ggtt_snapshot(struct xe_gt *gt, u32 vfid,
					  struct xe_gt_sriov_pf_ggtt_token *token);
bool xe_gt_sriov_pf_service_ggtt_current(struct xe_gt *gt, u32 vfid,
					 const struct xe_gt_sriov_pf_ggtt_token *token);
void xe_gt_sriov_pf_service_reset_ggtt(struct xe_gt *gt, u32 vfid);
void xe_gt_sriov_pf_service_stop_ggtt_ct(struct xe_gt *gt);
void xe_gt_sriov_pf_service_fini_ggtt(struct xe_gt *gt);
int xe_gt_sriov_pf_service_process_mmio_relay(struct xe_gt *gt, const u32 *msg, u32 len);
#else
static inline int
xe_gt_sriov_pf_service_process_request(struct xe_gt *gt, u32 origin,
				       const u32 *msg, u32 msg_len,
				       u32 *response, u32 resp_size,
				       const struct xe_gt_sriov_pf_ggtt_token *token)
{
	return -EPROTO;
}
static inline bool xe_gt_sriov_pf_service_has_ggtt_relay(struct xe_gt *gt)
{
	return false;
}
static inline bool
xe_gt_sriov_pf_service_ggtt_snapshot(struct xe_gt *gt, u32 vfid,
				     struct xe_gt_sriov_pf_ggtt_token *token)
{
	return false;
}
static inline bool
xe_gt_sriov_pf_service_ggtt_current(struct xe_gt *gt, u32 vfid,
				    const struct xe_gt_sriov_pf_ggtt_token *token)
{
	return false;
}
static inline void xe_gt_sriov_pf_service_stop_ggtt_ct(struct xe_gt *gt)
{
}
static inline int
xe_gt_sriov_pf_service_process_mmio_relay(struct xe_gt *gt, const u32 *msg, u32 len)
{
	return -EPROTO;
}
#endif

#endif
