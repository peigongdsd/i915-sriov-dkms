// SPDX-License-Identifier: MIT
/*
 * Copyright © 2026 Intel Corporation
 */

#include "xe_gt_sriov_pf_debug.h"

#include <linux/atomic.h>
#include <linux/bitfield.h>
#include <linux/bits.h>
#include <linux/ktime.h>
#include <linux/string.h>

#include <drm/drm_print.h>

#include "abi/guc_klvs_abi.h"
#include "abi/guc_relay_actions_abi.h"
#include "abi/iov_actions_mmio_abi.h"
#include "regs/xe_gtt_defs.h"
#include "xe_bo.h"
#include "xe_device.h"
#include "xe_gt.h"
#include "xe_gt_printk.h"
#include "xe_gt_sriov_pf_debug_types.h"
#include "xe_gt_sriov_pf_helpers.h"
#include "xe_guc_klv_helpers.h"

#define XE_GGTT_PTE_ADDR_MASK	GENMASK_ULL(51, 12)
#define XE_GGTT_PTE_FLAG_MASK	(~XE_GGTT_PTE_ADDR_MASK)

static const char *ggtt_update_source_to_string(u32 source)
{
	switch (source) {
	case XE_GT_SRIOV_GGTT_UPDATE_RELAY:
		return "relay";
	case XE_GT_SRIOV_GGTT_UPDATE_MMIO:
		return "mmio";
	default:
		return "unknown";
	}
}

static const char *ggtt_update_mode_to_string(u32 mode)
{
	switch (mode) {
	case 0:
		return "duplicate";
	case 1:
		return "replicate";
	case 2:
		return "duplicate-last";
	case 3:
		return "replicate-last";
	default:
		return "unknown";
	}
}

static bool ggtt_update_mode_is_duplicate(u32 mode)
{
	return mode == 0 || mode == 2;
}

static bool ggtt_update_mode_is_last(u32 mode)
{
	return mode == 2 || mode == 3;
}

static u64 ggtt_prepare_final_pte(u64 pte, u16 vfid)
{
	return u64_replace_bits(pte, vfid, GGTT_PTE_VFID) | XE_PAGE_PRESENT;
}

static u32 ggtt_pat_index(u64 pte)
{
	return ((pte & XELPG_GGTT_PTE_PAT0) ? BIT(0) : 0) |
	       ((pte & XELPG_GGTT_PTE_PAT1) ? BIT(1) : 0);
}

static bool debug_filter_match(struct xe_gt_sriov_pf_ggtt_debug *dbg, u32 start, u32 count)
{
	u32 filter_start = READ_ONCE(dbg->filter_start);
	u32 filter_count = READ_ONCE(dbg->filter_count);
	u32 filter_end, end;

	if (!filter_count)
		return true;

	filter_end = filter_start + filter_count;
	end = start + count;

	return start < filter_end && end > filter_start;
}

static void ggtt_record_history(struct xe_gt_sriov_pf_ggtt_debug *debug,
				u32 source, u32 pte_offset, u32 mode,
				u16 num_copies, u16 count, u32 n_ptes, int ret,
				u32 pat_mask, u64 raw_first, u64 raw_last,
				u64 final_first, u64 final_last, u64 old_first,
				u64 raw_flags_mask, u64 final_flags_mask)
{
	u64 seq = atomic64_inc_return(&debug->history_seq);
	struct xe_gt_sriov_pf_ggtt_record *record =
		&debug->history[(seq - 1) % XE_GT_SRIOV_PF_DEBUG_GGTT_HISTORY];

	WRITE_ONCE(record->ktime_ns, ktime_get_mono_fast_ns());
	WRITE_ONCE(record->raw_first, raw_first);
	WRITE_ONCE(record->raw_last, raw_last);
	WRITE_ONCE(record->final_first, final_first);
	WRITE_ONCE(record->final_last, final_last);
	WRITE_ONCE(record->old_first, old_first);
	WRITE_ONCE(record->raw_flags_mask, raw_flags_mask);
	WRITE_ONCE(record->final_flags_mask, final_flags_mask);
	WRITE_ONCE(record->source, source);
	WRITE_ONCE(record->mode, mode);
	WRITE_ONCE(record->num_copies, num_copies);
	WRITE_ONCE(record->count, count);
	WRITE_ONCE(record->n_ptes, n_ptes);
	WRITE_ONCE(record->offset, pte_offset);
	WRITE_ONCE(record->end, pte_offset + n_ptes);
	WRITE_ONCE(record->ret, ret);
	WRITE_ONCE(record->pat_mask, pat_mask);

	/* Publish seq last so readers can skip partially updated records. */
	WRITE_ONCE(record->seq, seq);
}

static void ggtt_decode_entry(const u64 *ptes, u16 count, u32 mode,
			      u16 num_copies, u32 n, u64 *entry)
{
	bool duplicate = ggtt_update_mode_is_duplicate(mode);
	bool last = ggtt_update_mode_is_last(mode);
	u16 copies = num_copies + 1;
	u16 remaining = count - 1;
	u16 idx;

	if (!last) {
		if (n < copies) {
			*entry = duplicate ? ptes[0] : ptes[0] + (u64)n * XE_PAGE_SIZE;
			return;
		}

		idx = n - copies + 1;
	} else {
		if (n < remaining) {
			*entry = ptes[n];
			return;
		}

		idx = remaining;
		n -= remaining;
		*entry = duplicate ? ptes[idx] : ptes[idx] + (u64)n * XE_PAGE_SIZE;
		return;
	}

	*entry = ptes[idx];
}

void xe_gt_sriov_pf_debug_init(struct xe_gt *gt)
{
	unsigned int n, total_vfs = xe_gt_sriov_pf_get_totalvfs(gt);

	for (n = 0; n <= total_vfs; n++) {
		struct xe_gt_sriov_pf_debug_data *debug = &gt->sriov.pf.vfs[n].debug;

		spin_lock_init(&debug->config.lock);
		atomic_set(&debug->ggtt.log_budget, 0);
		atomic_set(&debug->ggtt.raw_budget, 0);
		atomic64_set(&debug->ggtt.history_seq, 0);
		atomic_set(&debug->config.log_budget, 0);
		atomic_set(&debug->service.log_budget, 0);
		debug->ggtt.snapshot_count = 32;
	}
}

void xe_gt_sriov_pf_debug_record_config_push(struct xe_gt *gt, unsigned int vfid,
					     const u32 *klvs, u32 num_dwords,
					     int num_klvs, int err)
{
	struct xe_gt_sriov_pf_config_debug *debug;
	unsigned long flags;
	u32 stored;

	if (unlikely(!gt))
		return;
	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return;

	debug = &gt->sriov.pf.vfs[vfid].debug.config;
	atomic64_inc(&debug->pushes);
	if (err)
		atomic64_inc(&debug->errors);

	stored = min_t(u32, num_dwords, XE_GT_SRIOV_PF_DEBUG_MAX_KLV_DWORDS);

	spin_lock_irqsave(&debug->lock, flags);
	debug->last_seq++;
	debug->last_num_dwords = num_dwords;
	debug->last_stored_dwords = stored;
	debug->last_num_klvs = num_klvs < 0 ? 0 : num_klvs;
	debug->last_err = err < 0 ? -err : 0;
	debug->last_truncated = stored != num_dwords;
	if (stored)
		memcpy(debug->last_klvs, klvs, stored * sizeof(*klvs));
	spin_unlock_irqrestore(&debug->lock, flags);

	if ((err && (READ_ONCE(debug->flags) & XE_GT_SRIOV_PF_DEBUG_LOG_ERRORS) &&
	     atomic_add_unless(&debug->log_budget, -1, 0)) ||
	    ((READ_ONCE(debug->flags) & XE_GT_SRIOV_PF_DEBUG_LOG_UPDATES) &&
	     atomic_add_unless(&debug->log_budget, -1, 0))) {
		xe_gt_info(gt, "SR-IOV VF%u config push klvs=%d dwords=%u err=%d%s\n",
			   vfid, num_klvs, num_dwords, err,
			   stored != num_dwords ? " truncated" : "");
	}
}

void xe_gt_sriov_pf_debug_record_service(struct xe_gt *gt, unsigned int vfid,
					 u32 action, u32 msg_len, u32 resp_size, int ret)
{
	struct xe_gt_sriov_pf_service_debug *debug;
	u32 flags;

	if (unlikely(!gt))
		return;
	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return;

	debug = &gt->sriov.pf.vfs[vfid].debug.service;
	flags = READ_ONCE(debug->flags);

	atomic64_inc(&debug->requests);
	if (ret < 0)
		atomic64_inc(&debug->errors);

	switch (action) {
	case GUC_RELAY_ACTION_VF2PF_HANDSHAKE:
		atomic64_inc(&debug->handshake);
		break;
	case GUC_RELAY_ACTION_VF2PF_QUERY_RUNTIME:
		atomic64_inc(&debug->runtime);
		break;
	case GUC_RELAY_ACTION_VF2PF_UPDATE_GGTT32:
		atomic64_inc(&debug->ggtt);
		break;
	default:
		atomic64_inc(&debug->unknown);
		break;
	}

	WRITE_ONCE(debug->last_action, action);
	WRITE_ONCE(debug->last_ret, ret < 0 ? -ret : ret);
	WRITE_ONCE(debug->last_msg_len, msg_len);
	WRITE_ONCE(debug->last_resp_size, resp_size);

	if (ret < 0 && (flags & XE_GT_SRIOV_PF_DEBUG_LOG_ERRORS) &&
	    atomic_add_unless(&debug->log_budget, -1, 0))
		xe_gt_info(gt, "SR-IOV VF%u service action=%#x msg_len=%u resp=%u err=%d\n",
			   vfid, action, msg_len, resp_size, ret);
}

void xe_gt_sriov_pf_debug_record_mmio(struct xe_gt *gt, unsigned int vfid,
				      u32 opcode, int ret)
{
	struct xe_gt_sriov_pf_service_debug *debug;
	u32 flags;

	if (unlikely(!gt))
		return;
	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return;

	debug = &gt->sriov.pf.vfs[vfid].debug.service;
	flags = READ_ONCE(debug->flags);

	atomic64_inc(&debug->mmio_requests);
	if (ret < 0)
		atomic64_inc(&debug->mmio_errors);

	switch (opcode) {
	case IOV_OPCODE_VF2PF_MMIO_HANDSHAKE:
		atomic64_inc(&debug->mmio_handshake);
		break;
	case IOV_OPCODE_VF2PF_MMIO_GET_RUNTIME:
		atomic64_inc(&debug->mmio_runtime);
		break;
	case IOV_OPCODE_VF2PF_MMIO_UPDATE_GGTT:
		atomic64_inc(&debug->mmio_ggtt);
		break;
	default:
		atomic64_inc(&debug->mmio_unknown);
		break;
	}

	WRITE_ONCE(debug->last_opcode, opcode);
	WRITE_ONCE(debug->last_ret, ret < 0 ? -ret : ret);

	if (ret < 0 && (flags & XE_GT_SRIOV_PF_DEBUG_LOG_ERRORS) &&
	    atomic_add_unless(&debug->log_budget, -1, 0))
		xe_gt_info(gt, "SR-IOV VF%u MMIO relay opcode=%#x err=%d\n",
			   vfid, opcode, ret);
}

void xe_gt_sriov_pf_debug_record_ggtt_update(struct xe_gt *gt, unsigned int vfid,
					     u32 source, u32 pte_offset, u8 mode,
					     u16 num_copies, const u64 *old_ptes,
					     const u64 *new_ptes, u16 count, int ret)
{
	struct xe_gt_sriov_pf_ggtt_debug *debug;
	u64 raw_first = 0, raw_last = 0, final_first = 0, final_last = 0, old_first = 0;
	u64 raw_flags_mask = 0, final_flags_mask = 0;
	u32 n_ptes, pat_mask = 0;
	bool contiguous = true;
	u32 flags;
	u16 i;

	if (unlikely(!gt))
		return;
	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return;

	debug = &gt->sriov.pf.vfs[vfid].debug.ggtt;
	flags = READ_ONCE(debug->flags);
	n_ptes = ret > 0 ? min_t(u32, ret, count + num_copies) : 0;

	atomic64_inc(&debug->updates);
	if (ret < 0)
		atomic64_inc(&debug->errors);
	if (source < XE_GT_SRIOV_GGTT_UPDATE_SOURCE_COUNT)
		atomic64_inc(&debug->source[source]);
	if (mode < XE_GT_SRIOV_GGTT_UPDATE_MODE_COUNT)
		atomic64_inc(&debug->mode[mode]);
	if (n_ptes)
		atomic64_add(n_ptes, &debug->ptes);

	if (ret > 0 && new_ptes) {
		u64 prev_addr = 0;

		for (i = 0; i < n_ptes; i++) {
			u64 raw, final, old = old_ptes ? old_ptes[i] : 0;
			u64 raw_addr, raw_flags, old_addr, old_flags;
			u32 pat;

			ggtt_decode_entry(new_ptes, count, mode, num_copies, i, &raw);
			final = ggtt_prepare_final_pte(raw, vfid);

			if (!i) {
				raw_first = raw;
				final_first = final;
				old_first = old;
			}
			raw_last = raw;
			final_last = final;

			raw_addr = raw & XE_GGTT_PTE_ADDR_MASK;
			raw_flags = raw & XE_GGTT_PTE_FLAG_MASK;
			old_addr = old & XE_GGTT_PTE_ADDR_MASK;
			old_flags = old & XE_GGTT_PTE_FLAG_MASK;
			raw_flags_mask |= raw_flags;
			final_flags_mask |= final & XE_GGTT_PTE_FLAG_MASK;

			if (raw & XE_PAGE_PRESENT)
				atomic64_inc(&debug->raw_present);
			else
				atomic64_inc(&debug->raw_clear);
			if (final & XE_PAGE_PRESENT)
				atomic64_inc(&debug->final_present);
			if (raw & XE_GGTT_PTE_DM)
				atomic64_inc(&debug->dm);
			if (!raw)
				atomic64_inc(&debug->clears);

			pat = ggtt_pat_index(raw);
			pat_mask |= BIT(pat);
			if (pat < XE_GT_SRIOV_GGTT_PAT_COUNT)
				atomic64_inc(&debug->pat[pat]);

			if (old_ptes) {
				if (old_addr != raw_addr && old_flags != raw_flags)
					atomic64_inc(&debug->addr_and_flags);
				else if (old_addr != raw_addr)
					atomic64_inc(&debug->addr_only);
				else if (old_flags != raw_flags)
					atomic64_inc(&debug->flags_only);
				else
					atomic64_inc(&debug->no_change);
			}

			if (i && raw_addr != prev_addr + XE_PAGE_SIZE)
				contiguous = false;
			prev_addr = raw_addr;
		}

		if (contiguous)
			atomic64_inc(&debug->contiguous);
		else
			atomic64_inc(&debug->non_contiguous);
	}

	WRITE_ONCE(debug->last_source, source);
	WRITE_ONCE(debug->last_mode, mode);
	WRITE_ONCE(debug->last_num_copies, num_copies);
	WRITE_ONCE(debug->last_count, count);
	WRITE_ONCE(debug->last_n_ptes, n_ptes);
	WRITE_ONCE(debug->last_offset, pte_offset);
	WRITE_ONCE(debug->last_end, pte_offset + n_ptes);
	WRITE_ONCE(debug->last_ret, ret < 0 ? -ret : ret);
	WRITE_ONCE(debug->last_pat_mask, pat_mask);
	WRITE_ONCE(debug->last_raw_first, raw_first);
	WRITE_ONCE(debug->last_raw_last, raw_last);
	WRITE_ONCE(debug->last_final_first, final_first);
	WRITE_ONCE(debug->last_final_last, final_last);
	WRITE_ONCE(debug->last_old_first, old_first);
	WRITE_ONCE(debug->last_raw_flags_mask, raw_flags_mask);
	WRITE_ONCE(debug->last_final_flags_mask, final_flags_mask);

	ggtt_record_history(debug, source, pte_offset, mode, num_copies, count, n_ptes, ret,
			    pat_mask, raw_first, raw_last, final_first, final_last,
			    old_first, raw_flags_mask, final_flags_mask);

	if (!debug_filter_match(debug, pte_offset, max_t(u32, n_ptes, 1)))
		return;

	if (ret < 0 && (flags & XE_GT_SRIOV_PF_DEBUG_LOG_ERRORS) &&
	    atomic_add_unless(&debug->log_budget, -1, 0))
		xe_gt_info(gt, "SR-IOV VF%u GGTT %s off=%u mode=%s copies=%u count=%u err=%d\n",
			   vfid, ggtt_update_source_to_string(source), pte_offset,
			   ggtt_update_mode_to_string(mode), num_copies, count, ret);

	if ((flags & XE_GT_SRIOV_PF_DEBUG_LOG_UPDATES) &&
	    atomic_add_unless(&debug->log_budget, -1, 0))
		xe_gt_info(gt,
			   "SR-IOV VF%u GGTT %s off=%u..%u mode=%s copies=%u count=%u ptes=%u pat_mask=%#x flags=%#llx final_flags=%#llx ret=%d\n",
			   vfid, ggtt_update_source_to_string(source), pte_offset,
			   pte_offset + n_ptes, ggtt_update_mode_to_string(mode),
			   num_copies, count, n_ptes, pat_mask, raw_flags_mask,
			   final_flags_mask, ret);

	if ((flags & XE_GT_SRIOV_PF_DEBUG_LOG_RAW) &&
	    atomic_add_unless(&debug->raw_budget, -1, 0))
		xe_gt_info(gt,
			   "SR-IOV VF%u GGTT raw old=%#llx new=%#llx..%#llx final=%#llx..%#llx\n",
			   vfid, old_first, raw_first, raw_last, final_first, final_last);
}

int xe_gt_sriov_pf_debug_print_config(struct xe_gt *gt, unsigned int vfid,
				      struct drm_printer *p)
{
	struct xe_gt_sriov_pf_config_debug *debug;
	u32 klvs[XE_GT_SRIOV_PF_DEBUG_MAX_KLV_DWORDS];
	unsigned long flags;
	u32 stored, num_dwords, seq, num_klvs, err;
	bool truncated;

	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return -EINVAL;

	debug = &gt->sriov.pf.vfs[vfid].debug.config;

	spin_lock_irqsave(&debug->lock, flags);
	seq = debug->last_seq;
	num_dwords = debug->last_num_dwords;
	stored = debug->last_stored_dwords;
	num_klvs = debug->last_num_klvs;
	err = debug->last_err;
	truncated = debug->last_truncated;
	if (stored)
		memcpy(klvs, debug->last_klvs, stored * sizeof(*klvs));
	spin_unlock_irqrestore(&debug->lock, flags);

	drm_printf(p, "pushes: %lld\n", atomic64_read(&debug->pushes));
	drm_printf(p, "errors: %lld\n", atomic64_read(&debug->errors));
	drm_printf(p, "flags: %#x\n", READ_ONCE(debug->flags));
	drm_printf(p, "log_budget: %d\n", atomic_read(&debug->log_budget));
	drm_printf(p, "last_seq: %u\n", seq);
	drm_printf(p, "last_err: %u\n", err);
	drm_printf(p, "last_num_klvs: %u\n", num_klvs);
	drm_printf(p, "last_num_dwords: %u\n", num_dwords);
	drm_printf(p, "last_stored_dwords: %u%s\n", stored, truncated ? " truncated" : "");
	if (stored)
		xe_guc_klv_print(klvs, stored, p);

	return 0;
}

int xe_gt_sriov_pf_debug_print_service(struct xe_gt *gt, unsigned int vfid,
				       struct drm_printer *p)
{
	struct xe_gt_sriov_pf_service_debug *debug;

	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return -EINVAL;

	debug = &gt->sriov.pf.vfs[vfid].debug.service;

	drm_printf(p, "flags: %#x\n", READ_ONCE(debug->flags));
	drm_printf(p, "log_budget: %d\n", atomic_read(&debug->log_budget));
	drm_printf(p, "requests: %lld\n", atomic64_read(&debug->requests));
	drm_printf(p, "errors: %lld\n", atomic64_read(&debug->errors));
	drm_printf(p, "handshake: %lld\n", atomic64_read(&debug->handshake));
	drm_printf(p, "runtime: %lld\n", atomic64_read(&debug->runtime));
	drm_printf(p, "ggtt: %lld\n", atomic64_read(&debug->ggtt));
	drm_printf(p, "unknown: %lld\n", atomic64_read(&debug->unknown));
	drm_printf(p, "mmio_requests: %lld\n", atomic64_read(&debug->mmio_requests));
	drm_printf(p, "mmio_errors: %lld\n", atomic64_read(&debug->mmio_errors));
	drm_printf(p, "mmio_handshake: %lld\n", atomic64_read(&debug->mmio_handshake));
	drm_printf(p, "mmio_runtime: %lld\n", atomic64_read(&debug->mmio_runtime));
	drm_printf(p, "mmio_ggtt: %lld\n", atomic64_read(&debug->mmio_ggtt));
	drm_printf(p, "mmio_unknown: %lld\n", atomic64_read(&debug->mmio_unknown));
	drm_printf(p, "last_action: %#x\n", READ_ONCE(debug->last_action));
	drm_printf(p, "last_opcode: %#x\n", READ_ONCE(debug->last_opcode));
	drm_printf(p, "last_ret: %u\n", READ_ONCE(debug->last_ret));
	drm_printf(p, "last_msg_len: %u\n", READ_ONCE(debug->last_msg_len));
	drm_printf(p, "last_resp_size: %u\n", READ_ONCE(debug->last_resp_size));

	return 0;
}

int xe_gt_sriov_pf_debug_print_ggtt(struct xe_gt *gt, unsigned int vfid,
				    struct drm_printer *p)
{
	struct xe_gt_sriov_pf_ggtt_debug *debug;
	u64 history_seq, first_seq, seq;
	bool any_history = false;
	u32 i;

	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return -EINVAL;

	debug = &gt->sriov.pf.vfs[vfid].debug.ggtt;

	drm_printf(p, "flags: %#x\n", READ_ONCE(debug->flags));
	drm_printf(p, "log_budget: %d\n", atomic_read(&debug->log_budget));
	drm_printf(p, "raw_budget: %d\n", atomic_read(&debug->raw_budget));
	drm_printf(p, "filter_start: %u\n", READ_ONCE(debug->filter_start));
	drm_printf(p, "filter_count: %u\n", READ_ONCE(debug->filter_count));
	drm_printf(p, "snapshot_start: %u\n", READ_ONCE(debug->snapshot_start));
	drm_printf(p, "snapshot_count: %u\n", READ_ONCE(debug->snapshot_count));
	drm_printf(p, "updates: %lld\n", atomic64_read(&debug->updates));
	drm_printf(p, "ptes: %lld\n", atomic64_read(&debug->ptes));
	drm_printf(p, "errors: %lld\n", atomic64_read(&debug->errors));
	for (i = 0; i < XE_GT_SRIOV_GGTT_UPDATE_SOURCE_COUNT; i++)
		drm_printf(p, "source_%s: %lld\n", ggtt_update_source_to_string(i),
			   atomic64_read(&debug->source[i]));
	for (i = 0; i < XE_GT_SRIOV_GGTT_UPDATE_MODE_COUNT; i++)
		drm_printf(p, "mode_%s: %lld\n", ggtt_update_mode_to_string(i),
			   atomic64_read(&debug->mode[i]));
	for (i = 0; i < XE_GT_SRIOV_GGTT_PAT_COUNT; i++)
		drm_printf(p, "pat%u: %lld\n", i, atomic64_read(&debug->pat[i]));
	drm_printf(p, "raw_present: %lld\n", atomic64_read(&debug->raw_present));
	drm_printf(p, "raw_clear: %lld\n", atomic64_read(&debug->raw_clear));
	drm_printf(p, "final_present: %lld\n", atomic64_read(&debug->final_present));
	drm_printf(p, "dm: %lld\n", atomic64_read(&debug->dm));
	drm_printf(p, "addr_only: %lld\n", atomic64_read(&debug->addr_only));
	drm_printf(p, "flags_only: %lld\n", atomic64_read(&debug->flags_only));
	drm_printf(p, "addr_and_flags: %lld\n", atomic64_read(&debug->addr_and_flags));
	drm_printf(p, "no_change: %lld\n", atomic64_read(&debug->no_change));
	drm_printf(p, "clears: %lld\n", atomic64_read(&debug->clears));
	drm_printf(p, "contiguous: %lld\n", atomic64_read(&debug->contiguous));
	drm_printf(p, "non_contiguous: %lld\n", atomic64_read(&debug->non_contiguous));
	drm_printf(p, "last_source: %s\n",
		   ggtt_update_source_to_string(READ_ONCE(debug->last_source)));
	drm_printf(p, "last_mode: %s\n",
		   ggtt_update_mode_to_string(READ_ONCE(debug->last_mode)));
	drm_printf(p, "last_num_copies: %u\n", READ_ONCE(debug->last_num_copies));
	drm_printf(p, "last_count: %u\n", READ_ONCE(debug->last_count));
	drm_printf(p, "last_n_ptes: %u\n", READ_ONCE(debug->last_n_ptes));
	drm_printf(p, "last_offset: %u\n", READ_ONCE(debug->last_offset));
	drm_printf(p, "last_end: %u\n", READ_ONCE(debug->last_end));
	drm_printf(p, "last_ret: %u\n", READ_ONCE(debug->last_ret));
	drm_printf(p, "last_pat_mask: %#x\n", READ_ONCE(debug->last_pat_mask));
	drm_printf(p, "last_raw_first: %#llx\n", READ_ONCE(debug->last_raw_first));
	drm_printf(p, "last_raw_last: %#llx\n", READ_ONCE(debug->last_raw_last));
	drm_printf(p, "last_final_first: %#llx\n", READ_ONCE(debug->last_final_first));
	drm_printf(p, "last_final_last: %#llx\n", READ_ONCE(debug->last_final_last));
	drm_printf(p, "last_old_first: %#llx\n", READ_ONCE(debug->last_old_first));
	drm_printf(p, "last_raw_flags_mask: %#llx\n", READ_ONCE(debug->last_raw_flags_mask));
	drm_printf(p, "last_final_flags_mask: %#llx\n",
		   READ_ONCE(debug->last_final_flags_mask));
	history_seq = atomic64_read(&debug->history_seq);
	drm_printf(p, "history_seq: %llu\n", history_seq);

	drm_puts(p, "\nhistory:\n");
	if (history_seq > XE_GT_SRIOV_PF_DEBUG_GGTT_HISTORY)
		first_seq = history_seq - XE_GT_SRIOV_PF_DEBUG_GGTT_HISTORY + 1;
	else
		first_seq = 1;

	for (seq = first_seq; seq <= history_seq; seq++) {
		struct xe_gt_sriov_pf_ggtt_record *record =
			&debug->history[(seq - 1) % XE_GT_SRIOV_PF_DEBUG_GGTT_HISTORY];

		if (READ_ONCE(record->seq) != seq)
			continue;

		any_history = true;
		drm_printf(p,
			   "[%llu] t=%lluns %s off=%u..%u mode=%s copies=%u count=%u ptes=%u ret=%d pat_mask=%#x flags=%#llx final_flags=%#llx old=%#llx raw=%#llx..%#llx final=%#llx..%#llx\n",
			   seq, READ_ONCE(record->ktime_ns),
			   ggtt_update_source_to_string(READ_ONCE(record->source)),
			   READ_ONCE(record->offset), READ_ONCE(record->end),
			   ggtt_update_mode_to_string(READ_ONCE(record->mode)),
			   READ_ONCE(record->num_copies), READ_ONCE(record->count),
			   READ_ONCE(record->n_ptes), READ_ONCE(record->ret),
			   READ_ONCE(record->pat_mask), READ_ONCE(record->raw_flags_mask),
			   READ_ONCE(record->final_flags_mask), READ_ONCE(record->old_first),
			   READ_ONCE(record->raw_first), READ_ONCE(record->raw_last),
			   READ_ONCE(record->final_first), READ_ONCE(record->final_last));
	}
	if (!any_history)
		drm_puts(p, "(empty)\n");

	return 0;
}

void xe_gt_sriov_pf_debug_reset_ggtt(struct xe_gt *gt, unsigned int vfid)
{
	struct xe_gt_sriov_pf_ggtt_debug *debug;
	u32 flags, filter_start, filter_count, snapshot_start, snapshot_count;

	if (unlikely(vfid > xe_gt_sriov_pf_get_totalvfs(gt)))
		return;

	debug = &gt->sriov.pf.vfs[vfid].debug.ggtt;
	flags = READ_ONCE(debug->flags);
	filter_start = READ_ONCE(debug->filter_start);
	filter_count = READ_ONCE(debug->filter_count);
	snapshot_start = READ_ONCE(debug->snapshot_start);
	snapshot_count = READ_ONCE(debug->snapshot_count);

	memset(debug, 0, sizeof(*debug));
	WRITE_ONCE(debug->flags, flags);
	WRITE_ONCE(debug->filter_start, filter_start);
	WRITE_ONCE(debug->filter_count, filter_count);
	WRITE_ONCE(debug->snapshot_start, snapshot_start);
	WRITE_ONCE(debug->snapshot_count, snapshot_count);
}
