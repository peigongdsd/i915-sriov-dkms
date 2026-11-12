/* SPDX-License-Identifier: MIT */
/*
 * Copyright © 2023-2024 Intel Corporation
 */

#ifndef _XE_GT_SRIOV_PF_SERVICE_TYPES_H_
#define _XE_GT_SRIOV_PF_SERVICE_TYPES_H_

#include <linux/atomic.h>
#include <linux/types.h>
#include <linux/workqueue.h>

struct xe_gt;
struct xe_reg;

/* A request must not survive VF reprovisioning, FLR or either GT's CT reset. */
struct xe_gt_sriov_pf_ggtt_token {
	u32 generation;
	u32 primary_epoch;
	u32 media_epoch;
};

struct xe_gt_sriov_pf_mmio_ggtt {
	struct work_struct work;
	struct xe_gt *gt;
	struct xe_gt_sriov_pf_ggtt_token token;
	u64 pte;
	u32 desc;
	u32 vfid;
	u32 magic;
	/* Protected by the receiving GT's CT lock. */
	bool pending;
};

/**
 * struct xe_gt_sriov_pf_service_version - VF/PF ABI Version.
 * @major: the major version of the VF/PF ABI
 * @minor: the minor version of the VF/PF ABI
 *
 * See `GuC Relay Communication`_.
 */
struct xe_gt_sriov_pf_service_version {
	u16 major;
	u16 minor;
};

/**
 * struct xe_gt_sriov_pf_service_runtime_regs - Runtime data shared with VFs.
 * @regs: pointer to static array with register offsets.
 * @values: pointer to array with captured register values.
 * @size: size of the regs and value arrays.
 */
struct xe_gt_sriov_pf_service_runtime_regs {
	const struct xe_reg *regs;
	u32 *values;
	u32 size;
};

/**
 * struct xe_gt_sriov_pf_service - Data used by the PF service.
 * @version: information about VF/PF ABI versions for current platform.
 * @version.base: lowest VF/PF ABI version that could be negotiated with VF.
 * @version.latest: latest VF/PF ABI version supported by the PF driver.
 * @runtime: runtime data shared with VFs.
 * @ggtt_epoch: invalidates requests across GuC CT restarts.
 * @ggtt_stopped: blocks new updates during PF service teardown.
 */
struct xe_gt_sriov_pf_service {
	struct {
		struct xe_gt_sriov_pf_service_version base;
		struct xe_gt_sriov_pf_service_version latest;
	} version;
	struct xe_gt_sriov_pf_service_runtime_regs runtime;
	atomic_t ggtt_epoch;
	bool ggtt_stopped;
};

#endif
