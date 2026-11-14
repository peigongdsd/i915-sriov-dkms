// SPDX-License-Identifier: MIT

#include <linux/bitfield.h>

#include "abi/guc_actions_sriov_abi.h"
#include "abi/guc_communication_mmio_abi.h"
#include "abi/guc_relay_actions_abi.h"
#include "regs/xe_gtt_defs.h"

#include "xe_bo.h"
#include "xe_device.h"
#include "xe_gt.h"
#include "xe_gt_sriov_vf_ggtt.h"
#include "xe_guc.h"
#include "xe_guc_ct.h"
#include "xe_sriov.h"
#include "xe_tile_sriov_vf.h"

static int vf_ggtt_mmio_relay(struct xe_gt *gt, u8 opcode,
			    u32 data1, u32 data2, u32 data3, u32 *response)
{
	struct xe_gt_sriov_vf_ggtt *state = &gt->sriov.vf.ggtt;
	u8 magic = ++state->magic & FIELD_MAX(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC);
	u32 request[VF2GUC_MMIO_RELAY_SERVICE_REQUEST_MSG_LEN] = {
		FIELD_PREP(GUC_HXG_MSG_0_ORIGIN, GUC_HXG_ORIGIN_HOST) |
		FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_REQUEST) |
		FIELD_PREP(GUC_HXG_REQUEST_MSG_0_ACTION, GUC_ACTION_VF2GUC_MMIO_RELAY_SERVICE) |
		FIELD_PREP(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, magic) |
		FIELD_PREP(VF2GUC_MMIO_RELAY_SERVICE_REQUEST_MSG_0_OPCODE, opcode),
		data1, data2, data3,
	};
	int ret;

	ret = xe_guc_mmio_send_recv_once_locked(&gt->uc.guc, request,
					     ARRAY_SIZE(request), response);
	if (ret < 0)
		return ret;
	if (FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, response[0]) != magic)
		return -EPROTO;

	return FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_RESPONSE_MSG_0_DATA0, response[0]);
}

static int vf_ggtt_validate_range(struct xe_gt *gt, u32 page, u64 pte,
				u32 count, bool replicate)
{
	const u64 addr_mask = GENMASK_ULL(45, 12);
	const u64 allowed = addr_mask | XELPG_GGTT_PTE_PAT0 |
			    XELPG_GGTT_PTE_PAT1 | XE_PAGE_PRESENT;
	u64 limit = xe_tile_sriov_vf_ggtt(gt->tile) >> XE_PTE_SHIFT;

	if (!count || !(pte & XE_PAGE_PRESENT) || pte & ~allowed)
		return -EINVAL;

	limit = min_t(u64, limit, (u64)FIELD_MAX(VF2PF_UPDATE_GGTT32_OFFSET) + 1);
	if (page >= limit || count > limit - page)
		return -ERANGE;
	if (replicate && (u64)(count - 1) * XE_PAGE_SIZE > addr_mask - (pte & addr_mask))
		return -ERANGE;

	return 0;
}

/**
 * xe_gt_sriov_vf_ggtt_update - Submit an early MTL VF GGTT range update.
 * @gt: primary GT of the tile owning the GGTT
 * @page: first page relative to the VF's assigned GGTT allocation
 * @pte: first PTE, using Xe PAT encoding and no VFID bits
 * @count: number of pages
 * @replicate: advance the DMA address for each page, otherwise duplicate @pte
 * @result: current-call progress, initialized on every return
 *
 * The caller owns the node and DMA backing, excludes reset, reprovisioning
 * and CT transitions, holds the existing device memory-access/PM context,
 * and has already negotiated the GuC interface. The state belongs to one
 * uninterrupted pre-CT phase, not reuse after reset or a CT transition.
 * The helper serializes its whole transaction
 * with other GuC MMIO requests and validates the entire run before sending.
 *
 * An invalid or lost reply latches a stream error. No later update, rollback
 * or handshake is sent through this state. Resetting a GuC consumer or
 * zeroing this state is not a PF request-drain guarantee. Callers must keep
 * the affected mappings and backing alive until an external, established
 * completion or quiescence contract permits their release. Unrelated MMIO
 * calls are not blocked by this state; the caller must also stop protocol
 * transitions after a failure, since a late reply can overwrite scratch.
 *
 * This backend is not selected by the GGTT allocator. Native MTL VF probing
 * remains gated until the caller's ownership and recovery contract exists.
 *
 * Return: 0 if every page completed, otherwise a negative error. Even on
 * failure, @result may describe an acknowledged prefix and uncertain batch.
 */
int xe_gt_sriov_vf_ggtt_update(struct xe_gt *gt, u32 page, u64 pte, u32 count,
			     bool replicate, struct xe_gt_sriov_vf_ggtt_result *result)
{
	struct xe_gt_sriov_vf_ggtt *state = &gt->sriov.vf.ggtt;
	struct xe_device *xe = gt_to_xe(gt);
	u32 response[GUC_MAX_MMIO_MSG_LEN] = {};
	int ret;

	*result = (struct xe_gt_sriov_vf_ggtt_result){};
	if (!IS_SRIOV_VF(xe) || xe->info.platform != XE_METEORLAKE)
		return -EOPNOTSUPP;
	if (gt != gt->tile->primary_gt)
		return -EINVAL;

	guard(mutex)(&gt->uc.guc.vf_mmio_lock);
	if (state->error)
		return state->error;
	if (xe_guc_ct_enabled(&gt->uc.guc.ct))
		return -EBUSY;

	ret = vf_ggtt_validate_range(gt, page, pte, count, replicate);
	if (ret)
		return ret;

	if (!state->ready) {
		u32 version = FIELD_PREP(VF2PF_MMIO_HANDSHAKE_REQUEST_MSG_1_MAJOR, 1);

		ret = vf_ggtt_mmio_relay(gt, IOV_OPCODE_VF2PF_MMIO_HANDSHAKE,
					version, 0, 0, response);
		if (ret || response[1] != version) {
			state->error = ret < 0 ? ret : -EPROTO;
			return state->error;
		}
		state->ready = true;
	}

	while (result->completed < count) {
		u32 n = min_t(u32, count - result->completed,
				  FIELD_MAX(VF2PF_UPDATE_GGTT32_COPIES) + 1);
		u64 next = pte + (replicate ? (u64)result->completed * XE_PAGE_SIZE : 0);
		u32 desc = FIELD_PREP(VF2PF_UPDATE_GGTT32_OFFSET, page + result->completed) |
			   FIELD_PREP(VF2PF_UPDATE_GGTT32_COPIES, n - 1) |
			   FIELD_PREP(VF2PF_UPDATE_GGTT32_MODE,
				      replicate ? VF2PF_UPDATE_GGTT32_REPLICATE : 0);

		/* All failures after this point conservatively retain this batch. */
		result->uncertain = n;
		ret = vf_ggtt_mmio_relay(gt, IOV_OPCODE_VF2PF_MMIO_UPDATE_GGTT,
					desc, lower_32_bits(next), upper_32_bits(next), response);
		if (ret != n) {
			state->error = ret < 0 ? ret : -EPROTO;
			return state->error;
		}
		result->completed += n;
		result->uncertain = 0;
	}

	return 0;
}
