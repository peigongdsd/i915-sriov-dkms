/* SPDX-License-Identifier: MIT */
/* Exercise the PF PTE validator with captured writes; no hardware access. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint16_t u16;
#define BIT(n) (1U << (n))
#define BIT_ULL(n) (1ULL << (n))
#define GENMASK_ULL(h, l) ((~0ULL >> (63 - (h))) & (~0ULL << (l)))
#define GENMASK(h, l) ((u32)GENMASK_ULL(h, l))
#define FIELD_GET(m, v) (((v) & (m)) >> __builtin_ctzll(m))
#define FIELD_PREP(m, v) (((u64)(v) << __builtin_ctzll(m)) & (m))
#define FIELD_FIT(m, v) ((u64)(v) <= ((m) >> __builtin_ctzll(m)))
#define lower_32_bits(v) ((u32)(v))
#define upper_32_bits(v) ((u32)((v) >> 32))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define XE_PTE_SHIFT 12
#define XE_PAGE_SIZE (1U << XE_PTE_SHIFT)
#include "abi/guc_relay_actions_abi.h"
#include "regs/xe_gtt_defs.h"
struct xe_ggtt;
struct ops { void (*ggtt_set_pte)(struct xe_ggtt *, u64, u64); };
struct xe_ggtt { const struct ops *pt_ops; int lock; };
struct xe_ggtt_node { struct xe_ggtt *ggtt; u64 start, size; };
static u64 xe_ggtt_node_size(struct xe_ggtt_node *n) { return n->size; }
static u64 xe_ggtt_node_addr(struct xe_ggtt_node *n) { return n->start; }
static u64 xe_encode_vfid_pte(u16 id)
{
	return FIELD_PREP(GGTT_PTE_VFID, id) | XE_PAGE_PRESENT;
}
static void no_lock(int *p) { (void)p; }
#define guard(t) no_lock
static u64 written[2048], addresses[2048];
static unsigned int writes, flushes;
static void record(struct xe_ggtt *g, u64 a, u64 p)
{
	(void)g;
	assert(writes < ARRAY_SIZE(written));
	addresses[writes] = a;
	written[writes++] = p;
}
static void xe_ggtt_flush_writes(struct xe_ggtt *g) { (void)g; ++flushes; }
#include "actual-functions.inc"
static void reset_capture(void) { writes = flushes = 0; }
static void pf_cases(void)
{
	const struct ops ops = { record };
	struct xe_ggtt ggtt = { .pt_ops = &ops };
	struct xe_ggtt_node node = { .ggtt = &ggtt, .start = 0x2000000, .size = 8 * XE_PAGE_SIZE };
	u64 ptes[2] = { 0x100001, 0x200001 };
	u32 desc;

	/* All four expansion modes, ordering, relative addresses and ownership. */
	for (unsigned int mode = 0; mode < 4; mode++) {
		u64 expected[4];
		unsigned int k = 0, selected = (mode & 2) ? 1 : 0;

		desc = FIELD_PREP(VF2PF_UPDATE_GGTT32_MODE, mode) | 2;
		reset_capture();
		assert(xe_ggtt_update_vf_ptes(&node, 5, desc, ptes, 2) == 4);
		for (unsigned int i = 0; i < 2; i++) {
			expected[k++] = ptes[i] | (5 << 2);
			if (i == selected)
				for (unsigned int n = 1; n <= 2; n++)
					expected[k++] = (ptes[i] + ((mode & 1) ? n * XE_PAGE_SIZE : 0)) | (5 << 2);
		}
		assert(writes == 4 && flushes == 1);
		for (unsigned int i = 0; i < 4; i++) {
			assert(written[i] == expected[i]);
			assert(addresses[i] == node.start + i * XE_PAGE_SIZE);
		}
	}
	reset_capture();
	desc = FIELD_PREP(VF2PF_UPDATE_GGTT32_OFFSET, 7);
	assert(xe_ggtt_update_vf_ptes(&node, 1, desc, ptes, 1) == 1);
	reset_capture();
	assert(xe_ggtt_update_vf_ptes(&node, 1, desc | 1, ptes, 1) == -ERANGE);
	assert(xe_ggtt_update_vf_ptes(&node, 0, 0, ptes, 1) == -EINVAL);
	assert(xe_ggtt_update_vf_ptes(&node, 1024, 0, ptes, 1) == -EINVAL);
	assert(xe_ggtt_update_vf_ptes(&node, 1, 0, NULL, 0) == -EINVAL);
	assert(xe_ggtt_update_vf_ptes(&node, 1, 0, ptes, VF2PF_UPDATE_GGTT32_MAX_PTES + 1) == -EINVAL);
	ptes[1] = BIT_ULL(63) | 1;
	assert(xe_ggtt_update_vf_ptes(&node, 1, 0, ptes, 2) == -EINVAL);
	ptes[0] = 0;
	assert(xe_ggtt_update_vf_ptes(&node, 1, 0, ptes, 1) == -EINVAL);
	ptes[0] = GENMASK_ULL(45, 12) | 1;
	desc = FIELD_PREP(VF2PF_UPDATE_GGTT32_MODE, 1) | 1;
	assert(xe_ggtt_update_vf_ptes(&node, 1, desc, ptes, 1) == -ERANGE);
	assert(!writes && !flushes);
	ptes[0] = 0x100001 | FIELD_PREP(GGTT_PTE_VFID, 99) | XELPG_GGTT_PTE_PAT1;
	assert(xe_ggtt_update_vf_ptes(&node, 5, 0, ptes, 1) == 1);
	assert(FIELD_GET(GGTT_PTE_VFID, written[0]) == 5);
	assert(written[0] & XELPG_GGTT_PTE_PAT1);
}
int main(void)
{
	pf_cases();
	puts("PF GGTT range, expansion and ownership tests passed");
	return 0;
}
