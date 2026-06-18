/* SPDX-License-Identifier: MIT */
/*
 * Copyright © 2026 Intel Corporation
 */

#ifndef _XE_GT_SRIOV_PF_DEBUG_TYPES_H_
#define _XE_GT_SRIOV_PF_DEBUG_TYPES_H_

#include <linux/atomic.h>
#include <linux/bits.h>
#include <linux/spinlock_types.h>
#include <linux/types.h>

#define XE_GT_SRIOV_PF_DEBUG_MAX_KLV_DWORDS	256u
#define XE_GT_SRIOV_PF_DEBUG_SNAPSHOT_MAX_PTES	256u

#define XE_GT_SRIOV_PF_DEBUG_LOG_UPDATES	BIT(0)
#define XE_GT_SRIOV_PF_DEBUG_LOG_RAW		BIT(1)
#define XE_GT_SRIOV_PF_DEBUG_LOG_ERRORS		BIT(2)

#define XE_GT_SRIOV_GGTT_UPDATE_RELAY		0u
#define XE_GT_SRIOV_GGTT_UPDATE_MMIO		1u
#define XE_GT_SRIOV_GGTT_UPDATE_SOURCE_COUNT	2u

#define XE_GT_SRIOV_GGTT_UPDATE_MODE_COUNT	4u
#define XE_GT_SRIOV_GGTT_PAT_COUNT		4u

struct xe_gt_sriov_pf_ggtt_debug {
	u32 flags;
	atomic_t log_budget;
	atomic_t raw_budget;
	u32 filter_start;
	u32 filter_count;
	u32 snapshot_start;
	u32 snapshot_count;

	atomic64_t updates;
	atomic64_t ptes;
	atomic64_t errors;
	atomic64_t source[XE_GT_SRIOV_GGTT_UPDATE_SOURCE_COUNT];
	atomic64_t mode[XE_GT_SRIOV_GGTT_UPDATE_MODE_COUNT];
	atomic64_t pat[XE_GT_SRIOV_GGTT_PAT_COUNT];
	atomic64_t raw_present;
	atomic64_t raw_clear;
	atomic64_t final_present;
	atomic64_t dm;
	atomic64_t addr_only;
	atomic64_t flags_only;
	atomic64_t addr_and_flags;
	atomic64_t no_change;
	atomic64_t clears;
	atomic64_t contiguous;
	atomic64_t non_contiguous;

	u32 last_source;
	u32 last_mode;
	u32 last_num_copies;
	u32 last_count;
	u32 last_n_ptes;
	u32 last_offset;
	u32 last_end;
	u32 last_ret;
	u32 last_pat_mask;
	u64 last_raw_first;
	u64 last_raw_last;
	u64 last_final_first;
	u64 last_final_last;
	u64 last_old_first;
	u64 last_raw_flags_mask;
	u64 last_final_flags_mask;
};

struct xe_gt_sriov_pf_config_debug {
	spinlock_t lock;
	u32 flags;
	atomic_t log_budget;
	atomic64_t pushes;
	atomic64_t errors;
	u32 last_seq;
	u32 last_num_dwords;
	u32 last_stored_dwords;
	u32 last_num_klvs;
	u32 last_err;
	bool last_truncated;
	u32 last_klvs[XE_GT_SRIOV_PF_DEBUG_MAX_KLV_DWORDS];
};

struct xe_gt_sriov_pf_service_debug {
	u32 flags;
	atomic_t log_budget;
	atomic64_t requests;
	atomic64_t errors;
	atomic64_t handshake;
	atomic64_t runtime;
	atomic64_t ggtt;
	atomic64_t unknown;
	atomic64_t mmio_requests;
	atomic64_t mmio_errors;
	atomic64_t mmio_handshake;
	atomic64_t mmio_runtime;
	atomic64_t mmio_ggtt;
	atomic64_t mmio_unknown;
	u32 last_action;
	u32 last_opcode;
	u32 last_ret;
	u32 last_msg_len;
	u32 last_resp_size;
};

struct xe_gt_sriov_pf_debug_data {
	struct xe_gt_sriov_pf_ggtt_debug ggtt;
	struct xe_gt_sriov_pf_config_debug config;
	struct xe_gt_sriov_pf_service_debug service;
};

#endif
