/* SPDX-License-Identifier: MIT */
/*
 * Copyright © 2023-2024 Intel Corporation
 */

#ifndef _XE_GT_SRIOV_PF_CONFIG_TYPES_H_
#define _XE_GT_SRIOV_PF_CONFIG_TYPES_H_

#include "xe_ggtt_types.h"
#include "xe_guc_klv_thresholds_set_types.h"

struct xe_bo;

/**
 * struct xe_gt_sriov_config - GT level per-VF configuration data.
 *
 * Used by the PF driver to maintain per-VF provisioning data.
 */
struct xe_gt_sriov_config {
	/** @ggtt_region: GGTT region assigned to the VF. */
	struct xe_ggtt_node *ggtt_region;
	/** @ggtt_shadow: Shadow GGTT PTEs for this VF (PF only). */
	u64 *ggtt_shadow;
	/** @ggtt_shadow_num_ptes: Number of PTEs in @ggtt_shadow. */
	u32 ggtt_shadow_num_ptes;
	/** @ggtt_shadow_updates: Count of shadow updates for this VF. */
	u64 ggtt_shadow_updates;
	/** @ggtt_last_update_seqno: Last PF GGTT update sequence for this VF. */
	u64 ggtt_last_update_seqno;
	/** @ggtt_last_update_ns: Timestamp of last PF GGTT update for this VF. */
	u64 ggtt_last_update_ns;
	/** @ggtt_last_update_start: GGTT start of last PF update for this VF. */
	u64 ggtt_last_update_start;
	/** @ggtt_last_update_end: GGTT end of last PF update for this VF. */
	u64 ggtt_last_update_end;
	/** @ggtt_last_update_source: Last PF GGTT update source for this VF. */
	u8 ggtt_last_update_source;
	/** @ggtt_last_update_mode: Last PF GGTT update mode for this VF. */
	u8 ggtt_last_update_mode;
	/** @ggtt_last_update_count: Last PF GGTT update count for this VF. */
	u16 ggtt_last_update_count;
	/** @ggtt_last_update_copies: Last PF GGTT update copy count for this VF. */
	u16 ggtt_last_update_copies;
	/** @lmem_obj: LMEM allocation for use by the VF. */
	struct xe_bo *lmem_obj;
	/** @num_ctxs: number of GuC contexts IDs.  */
	u16 num_ctxs;
	/** @begin_ctx: start index of GuC context ID range. */
	u16 begin_ctx;
	/** @num_dbs: number of GuC doorbells IDs. */
	u16 num_dbs;
	/** @begin_db: start index of GuC doorbell ID range. */
	u16 begin_db;
	/** @exec_quantum: execution-quantum in milliseconds. */
	u32 exec_quantum;
	/** @preempt_timeout: preemption timeout in microseconds. */
	u32 preempt_timeout;
	/** @sched_priority: scheduling priority. */
	u32 sched_priority;
	/** @thresholds: GuC thresholds for adverse events notifications. */
	u32 thresholds[XE_GUC_KLV_NUM_THRESHOLDS];
};

/**
 * struct xe_gt_sriov_spare_config - GT-level PF spare configuration data.
 *
 * Used by the PF driver to maintain it's own reserved (spare) provisioning
 * data that is not applicable to be tracked in struct xe_gt_sriov_config.
 */
struct xe_gt_sriov_spare_config {
	/** @ggtt_size: GGTT size. */
	u64 ggtt_size;
	/** @lmem_size: LMEM size. */
	u64 lmem_size;
	/** @num_ctxs: number of GuC submission contexts. */
	u16 num_ctxs;
	/** @num_dbs: number of GuC doorbells. */
	u16 num_dbs;
};

#endif
