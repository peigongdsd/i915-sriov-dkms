/* SPDX-License-Identifier: MIT */
/* Actual PF service helpers, scripted state and completion; no concurrency. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U >> (31 - (h))) & (~0U << (l)))
#define FIELD_GET(m, v) (((v) & (m)) >> __builtin_ctz(m))
#include "abi/guc_relay_actions_abi.h"

struct xe_ggtt_node { int unused; };
struct xe_gt_sriov_pf_ggtt_token { int unused; };
struct xe_tlb_inval { unsigned int id; };
struct vf_config { struct { struct xe_ggtt_node *ggtt_region; } config; };
struct xe_tile;
struct xe_gt {
	struct xe_tile *tile;
	struct { struct { struct vf_config vfs[2]; } pf; } sriov;
	struct xe_tlb_inval tlb_inval;
};
struct xe_tile { struct xe_gt *primary_gt, *media_gt; };
static struct xe_ggtt_node node;
static struct xe_gt primary, media;
static struct xe_tile tile;
static struct xe_gt_sriov_pf_ggtt_token token;
static unsigned int updates, invalidations[2], current_calls, stale_at;
static unsigned int encoded, captured_count;
static u64 captured[VF2PF_UPDATE_GGTT32_MAX_PTES];
static u32 captured_desc, captured_vfid;
static int update_result, invalidate_result[2], provisioning_lock;
static bool negotiated;

static int *lock_acquire(int *lock)
{
	assert(!*lock);
	*lock = 1;
	return lock;
}

static void lock_release(int **lock)
{
	if (*lock) {
		assert(**lock);
		**lock = 0;
		*lock = NULL;
	}
}

#define scoped_guard(t, p) \
	for (int *held __attribute__((cleanup(lock_release))) = lock_acquire(p); \
	     held; lock_release(&held))
#define xe_gt_sriov_pf_master_mutex(g) (&provisioning_lock)
#define gt_to_xe(g) (g)
#define guard(t) mock_pm
static void mock_pm(struct xe_gt *gt) { (void)gt; }

static bool xe_gt_sriov_pf_service_ggtt_current(struct xe_gt *gt, u32 vfid,
					const struct xe_gt_sriov_pf_ggtt_token *t)
{
	(void)gt;
	assert(vfid == 1 && t == &token);
	return ++current_calls != stale_at;
}

static int xe_ggtt_update_vf_ptes(struct xe_ggtt_node *n, u32 vfid, u32 desc,
				 const u64 *ptes, unsigned int count)
{
	assert(n == &node && provisioning_lock);
	assert(count <= VF2PF_UPDATE_GGTT32_MAX_PTES);
	updates++;
	captured_count = count;
	captured_desc = desc;
	captured_vfid = vfid;
	memcpy(captured, ptes, count * sizeof(*ptes));
	return update_result;
}

static int xe_tlb_inval_ggtt_sync(struct xe_tlb_inval *tlb)
{
	assert(!provisioning_lock && tlb->id < 2);
	invalidations[tlb->id]++;
	return invalidate_result[tlb->id];
}

static bool xe_sriov_pf_service_is_negotiated(struct xe_gt *gt, u32 vfid,
					    u32 major, u32 minor)
{
	(void)gt;
	assert(vfid == 1 && major == 1 && minor == 0);
	return negotiated;
}

static int guc_hxg_msg_encode_success(u32 *response, u32 count)
{
	encoded++;
	*response = count;
	return 1;
}

#include "actual-functions.inc"

static void reset_case(void)
{
	assert(!provisioning_lock);
	memset(&primary, 0, sizeof(primary));
	memset(&media, 0, sizeof(media));
	tile = (struct xe_tile){ &primary, &media };
	primary.tile = media.tile = &tile;
	media.tlb_inval.id = 1;
	primary.sriov.pf.vfs[1].config.ggtt_region = &node;
	updates = current_calls = stale_at = encoded = captured_count = 0;
	invalidations[0] = invalidations[1] = 0;
	invalidate_result[0] = invalidate_result[1] = 0;
	update_result = 1;
	negotiated = true;
}

static void completion_cases(void)
{
	const u64 pte = 0x20000000100001ULL;
	const int errors[] = { 0, -ECANCELED, -ETIME, -EIO };

	/* Both GTs are attempted even when the first invalidation fails. */
	for (unsigned int a = 0; a < 4; a++) {
		for (unsigned int b = 0; b < 4; b++) {
			reset_case();
			invalidate_result[0] = errors[a];
			invalidate_result[1] = errors[b];
			assert(pf_update_ggtt(&media, 1, &token, 0, &pte, 1) ==
			       (errors[a] ?: errors[b] ?: 1));
			assert(updates == 1 && invalidations[0] == 1 && invalidations[1] == 1);
		}
	}
	reset_case();
	stale_at = 1;
	assert(pf_update_ggtt(&primary, 1, &token, 0, &pte, 1) == -ECANCELED);
	assert(!updates && !invalidations[0] && !invalidations[1]);
	reset_case();
	stale_at = 2;
	assert(pf_update_ggtt(&primary, 1, &token, 0, &pte, 1) == -ECANCELED);
	assert(updates == 1 && invalidations[0] == 1 && invalidations[1] == 1);
	reset_case();
	primary.sriov.pf.vfs[1].config.ggtt_region = NULL;
	assert(pf_update_ggtt(&primary, 1, &token, 0, &pte, 1) == -ENOENT);
	assert(!updates && !invalidations[0]);
	reset_case();
	update_result = -ERANGE;
	assert(pf_update_ggtt(&primary, 1, &token, 0, &pte, 1) == -ERANGE);
	assert(updates == 1 && !invalidations[0] && !invalidations[1]);
	reset_case();
	tile.media_gt = NULL;
	assert(pf_update_ggtt(&primary, 1, &token, 0, &pte, 1) == 1);
	assert(invalidations[0] == 1 && !invalidations[1]);
}

static int request(u32 *msg, u32 len, u32 size, const struct xe_gt_sriov_pf_ggtt_token *t)
{
	u32 response = 0;
	int ret = pf_process_update_ggtt_msg(&primary, 1, msg, len, &response, size, t);

	assert(!provisioning_lock);
	if (ret > 0)
		assert(encoded == 1 && response == (u32)update_result);
	else
		assert(!encoded);
	return ret;
}

static void protocol_cases(void)
{
	u32 msg[GUC_RELAY_MSG_MAX_LEN + 2] = { 0 };

	for (u32 len = 0; len <= GUC_RELAY_MSG_MAX_LEN + 2; len++) {
		reset_case();
		if (len < 4 || len > GUC_RELAY_MSG_MAX_LEN || (len & 1)) {
			assert(request(msg, len, 1, &token) == -EPROTO);
			assert(!updates);
		} else {
			assert(request(msg, len, 1, &token) == 1);
			assert(captured_count == (len - 2) / 2);
		}
	}
	reset_case();
	assert(request(msg, 4, 1, NULL) == -EOPNOTSUPP);
	assert(!updates);
	reset_case();
	msg[0] = GUC_HXG_REQUEST_MSG_0_DATA0;
	assert(request(msg, 4, 1, &token) == -EPROTO);
	assert(!updates);
	msg[0] = 0;
	reset_case();
	assert(request(msg, 4, 0, &token) == -ENOBUFS);
	assert(!updates);
	reset_case();
	negotiated = false;
	assert(request(msg, 4, 1, &token) == -EACCES);
	assert(!updates);
	reset_case();
	msg[1] = 0x12345001;
	msg[2] = 0x12345001;
	msg[3] = 0x200000;
	msg[4] = 0x98765001;
	msg[5] = 0x100000;
	update_result = 3;
	assert(request(msg, 6, 1, &token) == 1);
	assert(captured_count == 2 && captured_vfid == 1 && captured_desc == msg[1]);
	assert(captured[0] == 0x20000012345001ULL && captured[1] == 0x10000098765001ULL);
	reset_case();
	invalidate_result[1] = -ETIME;
	assert(request(msg, 6, 1, &token) == -ETIME);
	assert(updates == 1); /* Error is not a rollback or cancellation guarantee. */
	reset_case();
	stale_at = 3;
	assert(request(msg, 6, 1, &token) == -ECANCELED);
	assert(updates == 1);
}

int main(void)
{
	completion_cases();
	protocol_cases();
	puts("PF service protocol, two-GT completion and failure-policy tests passed");
	return 0;
}
