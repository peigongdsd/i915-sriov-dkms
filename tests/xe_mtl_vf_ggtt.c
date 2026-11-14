/* SPDX-License-Identifier: MIT */
/* Scripted MMIO and PF writes for actual transport and range-update code. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1U << (n))
#define BIT_ULL(n) (1ULL << (n))
#define GENMASK_ULL(h, l) ((~0ULL >> (63 - (h))) & (~0ULL << (l)))
#define GENMASK(h, l) ((u32)GENMASK_ULL(h, l))
#define FIELD_GET(m, v) (((v) & (m)) >> __builtin_ctzll(m))
#define FIELD_PREP(m, v) (((u64)(v) << __builtin_ctzll(m)) & (m))
#define FIELD_MAX(m) FIELD_GET(m, m)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define BUILD_BUG_ON(c) _Static_assert(!(c), #c)
#define min_t(t, a, b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define lower_32_bits(v) ((u32)(v))
#define upper_32_bits(v) ((u32)((v) >> 32))
#define unlikely(x) (x)
#define xe_assert(x, c) do { (void)(x); assert(c); } while (0)
#define xe_gt_dbg mock_log
#define xe_gt_err mock_log
#define ALLOW_ERROR_INJECTION(...)
#define XE_PTE_SHIFT 12
#define XE_PAGE_SIZE (1U << XE_PTE_SHIFT)
#define VF_SW_FLAG_COUNT 4
#define MED_VF_SW_FLAG_COUNT 4
#include "abi/guc_actions_sriov_abi.h"
#include "abi/guc_communication_mmio_abi.h"
#include "abi/guc_errors_abi.h"
#include "abi/guc_relay_actions_abi.h"
#include "regs/xe_gtt_defs.h"
#include "xe_gt_sriov_vf_ggtt.h"
#include "actual-state.inc"

struct xe_reg { u32 addr; };
#define VF_SW_FLAG(i) ((struct xe_reg){ (i) * 4 })
#define MED_VF_SW_FLAG(i) VF_SW_FLAG(i)
struct xe_mmio { int unused; };
struct xe_guc { struct xe_gt *gt; int vf_mmio_lock; bool ct; };
struct xe_tile { struct xe_gt *primary_gt; u64 size; };
struct xe_gt {
	struct xe_tile *tile;
	struct xe_mmio mmio;
	struct { struct xe_guc guc; } uc;
	struct { struct { struct xe_gt_sriov_vf_ggtt ggtt; } vf; } sriov;
};
enum { XE_METEORLAKE, OTHER_PLATFORM };
static struct xe_device { struct { int platform; } info; bool vf; } device;
static struct xe_gt gt;
static struct xe_tile tile;
static void mock_log(struct xe_gt *unused, const char *format, ...)
{
	(void)unused;
	(void)format;
}
#define guc_to_gt(g) ((g)->gt)
#define guc_to_xe(g) (&device)
#define gt_to_xe(g) (&device)
#define IS_SRIOV_VF(x) ((x)->vf)
#define xe_gt_is_media_type(g) ((g) != (g)->tile->primary_gt)
#define xe_tile_sriov_vf_ggtt(t) ((t)->size)
#define xe_guc_ct_enabled(c) (*(c))
#define lockdep_assert_held(p) assert(*(p))

static int *acquire(int *lock)
{
	assert(!*lock);
	*lock = 1;
	return lock;
}

static void release(int **lock)
{
	assert(**lock);
	**lock = 0;
}

#define guard(t) int *held __attribute__((cleanup(release))) = acquire
static void xe_sleep_relaxed_ms(unsigned int ms) { (void)ms; }
static void xe_sleep_exponential_ms(unsigned int *ms, unsigned int max)
{
	(void)ms;
	(void)max;
}

enum fault {
	NONE, LOST_ZERO, LOST_NONZERO, RETRY, BUSY_TIMEOUT, BUSY_SUCCESS,
	WRONG_MAGIC, SHORT_COUNT, INVAL_FAILURE, MIGRATED, DELAYED, BAD_VERSION,
};
static enum fault fault, active_fault;
static bool raw, raw_first_only, handshake_fault, pending;
static unsigned int notifications, updates, handshakes, waits, fault_update;
static u32 scratch[4], response[4], delayed_request[4];
static u64 ptes[4096];

static void apply_update(const u32 *req)
{
	u32 page = FIELD_GET(VF2PF_UPDATE_GGTT32_OFFSET, req[1]);
	u32 count = FIELD_GET(VF2PF_UPDATE_GGTT32_COPIES, req[1]) + 1;
	u32 mode = FIELD_GET(VF2PF_UPDATE_GGTT32_MODE, req[1]);
	u64 pte = ((u64)req[3] << 32) | req[2];
	u64 stride = mode & VF2PF_UPDATE_GGTT32_REPLICATE ? XE_PAGE_SIZE : 0;

	assert(page + count <= ARRAY_SIZE(ptes));
	for (u32 i = 0; i < count; i++)
		ptes[page + i] = pte + i * stride;
}

static void xe_mmio_write32(struct xe_mmio *mmio, struct xe_reg reg, u32 value)
{
	(void)mmio;
	assert(gt.uc.guc.vf_mmio_lock && reg.addr / 4 < ARRAY_SIZE(scratch));
	scratch[reg.addr / 4] = value;
}

static u32 xe_mmio_read32(struct xe_mmio *mmio, struct xe_reg reg)
{
	(void)mmio;
	assert(gt.uc.guc.vf_mmio_lock && reg.addr / 4 < ARRAY_SIZE(response));
	return response[reg.addr / 4];
}

static void xe_guc_notify(struct xe_guc *guc)
{
	u32 magic = FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, scratch[0]);
	u32 opcode = FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_REQUEST_MSG_0_OPCODE, scratch[0]);
	u32 count = 1;

	assert(guc->vf_mmio_lock);
	notifications++;
	waits = 0;
	active_fault = NONE;
	memset(response, 0, sizeof(response));
	if (raw) {
		if (!raw_first_only || notifications == 1)
			active_fault = fault;
		magic = 0;
	} else if (opcode == IOV_OPCODE_VF2PF_MMIO_HANDSHAKE) {
		handshakes++;
		if (handshake_fault)
			active_fault = fault;
		count = 0;
		response[1] = active_fault == BAD_VERSION ? 0x20000 : 0x10000;
	} else {
		assert(opcode == IOV_OPCODE_VF2PF_MMIO_UPDATE_GGTT);
		updates++;
		count = FIELD_GET(VF2PF_UPDATE_GGTT32_COPIES, scratch[1]) + 1;
		if (updates == fault_update)
			active_fault = fault;
		if (active_fault == DELAYED) {
			memcpy(delayed_request, scratch, sizeof(scratch));
			pending = true;
		} else if (active_fault == NONE || active_fault == BUSY_SUCCESS ||
			   active_fault == INVAL_FAILURE || active_fault == SHORT_COUNT ||
			   active_fault == WRONG_MAGIC) {
			apply_update(scratch);
		}
	}
	if (active_fault == WRONG_MAGIC)
		magic = (magic + 1) & 0xf;
	if (active_fault == SHORT_COUNT)
		count--;
	response[0] = FIELD_PREP(GUC_HXG_MSG_0_ORIGIN, GUC_HXG_ORIGIN_GUC) |
		      FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_RESPONSE_SUCCESS) |
		      FIELD_PREP(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, magic) | count;
	if (active_fault == RETRY)
		response[0] = BIT(31) | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_NO_RESPONSE_RETRY);
	if (active_fault == INVAL_FAILURE || active_fault == MIGRATED)
		response[0] = BIT(31) | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_RESPONSE_FAILURE) |
			FIELD_PREP(GUC_HXG_FAILURE_MSG_0_ERROR,
				   active_fault == MIGRATED ? XE_GUC_RESPONSE_VF_MIGRATED : 1);
}

static int xe_mmio_wait32(struct xe_mmio *mmio, struct xe_reg reg, u32 mask,
			 u32 value, unsigned int timeout, u32 *out, bool atomic)
{
	(void)mmio;
	(void)reg;
	(void)mask;
	(void)value;
	(void)timeout;
	(void)atomic;
	waits++;
	if (active_fault == LOST_ZERO || active_fault == DELAYED) {
		*out = 0;
		return -ETIMEDOUT;
	}
	if (active_fault == LOST_NONZERO) {
		*out = scratch[0];
		return -ETIMEDOUT;
	}
	if (active_fault == BUSY_TIMEOUT || (active_fault == BUSY_SUCCESS && waits == 1)) {
		*out = BIT(31) | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_NO_RESPONSE_BUSY);
		return waits == 1 ? 0 : -ETIMEDOUT;
	}
	*out = response[0];
	return 0;
}

#include "actual-functions.inc"

static void fresh_device(void)
{
	assert(!gt.uc.guc.vf_mmio_lock);
	memset(&gt, 0, sizeof(gt));
	gt.uc.guc.gt = &gt;
	gt.tile = &tile;
	tile.primary_gt = &gt;
	tile.size = sizeof(ptes) / sizeof(ptes[0]) * XE_PAGE_SIZE;
	device.vf = true;
	device.info.platform = XE_METEORLAKE;
	fault = active_fault = NONE;
	raw = raw_first_only = handshake_fault = pending = false;
	notifications = updates = handshakes = waits = fault_update = 0;
	memset(ptes, 0, sizeof(ptes));
}

static void range_cases(void)
{
	struct xe_gt_sriov_vf_ggtt_result result;
	u64 pte = XELPG_GGTT_PTE_PAT1 | 0x100001;

	fresh_device();
	assert(!xe_gt_sriov_vf_ggtt_update(&gt, 3, pte, 2049, true, &result));
	assert(result.completed == 2049 && !result.uncertain);
	assert(notifications == 4 && handshakes == 1 && updates == 3);
	for (u32 i = 0; i < 2049; i++)
		assert(ptes[3 + i] == pte + i * XE_PAGE_SIZE);
	assert(!xe_gt_sriov_vf_ggtt_update(&gt, 3, XE_PAGE_PRESENT, 2049, false, &result));
	assert(notifications == 7 && handshakes == 1 && updates == 6);
	for (u32 i = 0; i < 2049; i++)
		assert(ptes[3 + i] == XE_PAGE_PRESENT);
	/* Caller-split fragmented DMA/attribute runs; no new negotiation. */
	assert(!xe_gt_sriov_vf_ggtt_update(&gt, 3, 0xabc001, 2, true, &result));
	assert(!xe_gt_sriov_vf_ggtt_update(&gt, 5, XELPG_GGTT_PTE_PAT0 | 0x300001,
					 2, true, &result));
	assert(ptes[4] == 0xabd001 && ptes[5] == (XELPG_GGTT_PTE_PAT0 | 0x300001));
	assert(handshakes == 1);
	for (u32 i = 0; i < 32; i++)
		assert(!xe_gt_sriov_vf_ggtt_update(&gt, i, pte, 1, false, &result));
	assert(!gt.uc.guc.vf_mmio_lock && !gt.sriov.vf.ggtt.error);
	puts("PASS bounded map/clear runs, fragmented caller runs, PAT and magic wrap");
}

static void admission_cases(void)
{
	struct xe_gt_sriov_vf_ggtt_result result;
	const u64 invalid[] = { 0, 0x100002, BIT_ULL(46) | 1, BIT_ULL(63) | 1,
				1 | FIELD_PREP(GGTT_PTE_VFID, 1), XE_PAGE_PRESENT | XE_GGTT_PTE_DM };

	fresh_device();
	for (unsigned int i = 0; i < ARRAY_SIZE(invalid); i++) {
		assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, invalid[i], 1, true, &result) == -EINVAL);
		assert(!result.completed && !result.uncertain && !notifications);
	}
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 0, false, &result) == -EINVAL);
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 4095, 1, 2, false, &result) == -ERANGE);
	assert(xe_gt_sriov_vf_ggtt_update(&gt, UINT32_MAX, 1, 1, false, &result) == -ERANGE);
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, GENMASK_ULL(45, 12) | 1,
					 2, true, &result) == -ERANGE);
	tile.size = 1ULL << 40;
	assert(xe_gt_sriov_vf_ggtt_update(&gt, FIELD_MAX(VF2PF_UPDATE_GGTT32_OFFSET),
					 1, 2, false, &result) == -ERANGE);
	tile.size = 0;
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &result) == -ERANGE);
	assert(!notifications && !gt.sriov.vf.ggtt.error);
	fresh_device();
	gt.uc.guc.ct = true;
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &result) == -EBUSY);
	gt.uc.guc.ct = false;
	tile.primary_gt = NULL;
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &result) == -EINVAL);
	tile.primary_gt = &gt;
	device.vf = false;
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &result) == -EOPNOTSUPP);
	device.vf = true;
	device.info.platform = OTHER_PLATFORM;
	assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &result) == -EOPNOTSUPP);
	device.info.platform = XE_METEORLAKE;
	assert(!notifications && !gt.sriov.vf.ggtt.error);
	assert(!xe_gt_sriov_vf_ggtt_update(&gt, 4095, 1, 1, false, &result));
	puts("PASS complete-run validation and phase/platform guards before any submission");
}

static void failure_cases(void)
{
	const enum fault faults[] = { LOST_ZERO, LOST_NONZERO, RETRY, BUSY_TIMEOUT,
		WRONG_MAGIC, SHORT_COUNT, INVAL_FAILURE, MIGRATED, DELAYED };
	struct xe_gt_sriov_vf_ggtt_result result, later;

	for (unsigned int i = 0; i < ARRAY_SIZE(faults); i++) {
		for (unsigned int failed = 1; failed <= 3; failed++) {
			int ret;
			unsigned int sent;

			fresh_device();
			fault = faults[i];
			fault_update = failed;
			ret = xe_gt_sriov_vf_ggtt_update(&gt, 0, 0x100001, 2049, true, &result);
			assert(ret < 0 && result.completed == (failed - 1) * 1024);
			assert(result.uncertain == (failed == 3 ? 1 : 1024));
			assert(updates == failed && !gt.uc.guc.vf_mmio_lock);
			if (failed < 3)
				assert(!ptes[2048]);
			if (result.completed)
				assert(ptes[0] == 0x100001);
			sent = notifications;
			/* A caller cannot use another update as an attempted rollback. */
			assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 2049, false, &later) == ret);
			assert(!later.completed && !later.uncertain && notifications == sent);
			if (pending) {
				assert(!ptes[result.completed]);
				apply_update(delayed_request); /* The timed-out PF write arrives late. */
				assert(ptes[result.completed] == 0x100001 + (u64)result.completed * XE_PAGE_SIZE);
				assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 2049, false, &later) == ret);
				assert(notifications == sent);
			}
		}
	}
	puts("PASS 27 first/middle/last batch failures: exact progress, no replay/rollback");
	for (unsigned int i = 0; i < 2; i++) {
		int ret;

		fresh_device();
		handshake_fault = true;
		fault = i ? BAD_VERSION : LOST_ZERO;
		ret = xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &result);
		assert(ret < 0 && !updates && !result.completed && !result.uncertain);
		assert(xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &later) == ret);
		assert(notifications == 1);
	}
	puts("PASS failed negotiation latches stream error without submitting a PTE");
}

static void transport_cases(void)
{
	u32 request[4] = { 0 }, reply[4];
	const enum fault faults[] = { LOST_ZERO, LOST_NONZERO, RETRY, BUSY_TIMEOUT, MIGRATED };

	for (unsigned int i = 0; i < ARRAY_SIZE(faults); i++) {
		fresh_device();
		raw = true;
		fault = faults[i];
		gt.uc.guc.vf_mmio_lock = 1;
		assert(xe_guc_mmio_send_recv_once_locked(&gt.uc.guc, request, 4, reply) < 0);
		assert(notifications == 1);
		gt.uc.guc.vf_mmio_lock = 0;
	}
	for (unsigned int i = 0; i < 2; i++) {
		fresh_device();
		raw = raw_first_only = true;
		fault = i ? RETRY : LOST_ZERO;
		assert(xe_guc_mmio_send_recv(&gt.uc.guc, request, 4, reply) == 1);
		assert(notifications == 2 && !gt.uc.guc.vf_mmio_lock);
	}
	fresh_device();
	raw = true;
	fault = RETRY;
	assert(xe_guc_mmio_send_recv(&gt.uc.guc, request, 4, reply) == -ETIMEDOUT);
	assert(notifications == MAX_MMIO_RETRIES + 1 && !gt.uc.guc.vf_mmio_lock);
	fresh_device();
	fault = BUSY_SUCCESS;
	fault_update = 1;
	{
		struct xe_gt_sriov_vf_ggtt_result result;

		assert(!xe_gt_sriov_vf_ggtt_update(&gt, 0, 1, 1, false, &result));
		assert(result.completed == 1 && !result.uncertain && updates == 1 && waits == 2);
	}
	puts("PASS single-attempt transport, BUSY completion and preserved ordinary retry policy");
}

int main(void)
{
	range_cases();
	admission_cases();
	failure_cases();
	transport_cases();
	return 0;
}
