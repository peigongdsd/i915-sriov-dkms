#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile actual diagnostic batching/relay/clear helpers with fake DMA and PF replies.

These tests exercise bounds, encoding and failure decisions, not device DMA,
firmware reset ordering, IRQ delivery or the kernel's TTM/devres integration.
"""
import os
import shlex
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
xe = root / 'drivers/gpu/drm/xe'
vf = (xe / 'xe_gt_sriov_vf.c').read_text()
ggtt = (xe / 'xe_ggtt.c').read_text()
helpers = vf[vf.index('static int vf_test_mmio_relay('):
             vf.index('/*\n * Test the working PF')]
update = vf[vf.index('static void vf_test_ct_ggtt('):
            vf.index('/* No GGTT update is outstanding:')]
quiesce = vf[vf.index('void xe_gt_sriov_vf_bootstrap_quiesce('):
              vf.index('static int guc_action_match_version(')]
negotiation = vf[vf.index('static int guc_action_match_version('):
                 vf.index('/**\n * xe_gt_sriov_vf_bootstrap -')]
mapper = ggtt[ggtt.index('static void vf_bootstrap_map_bo('):
              ggtt.index('/**\n * xe_ggtt_map_bo -')]
unmapper = ggtt[ggtt.index('static void vf_bootstrap_unmap_node('):
                ggtt.index('/* BO reservation held')]
lifetime = ggtt[ggtt.index('/* BO reservation held'):ggtt.index('/* Called while the PCI probe')]
remove = ggtt[ggtt.index('static void ggtt_node_remove(struct'):ggtt.index('static void ggtt_node_remove_work_func(')]
experiment = ggtt[ggtt.index('int xe_ggtt_vf_ct_test('):ggtt.index('static void vf_bootstrap_map_bo(')]
fill = ggtt[ggtt.index('static u64 xe_ggtt_scratch_pte('):ggtt.index('static void primelockdep(')]
initial = ggtt[ggtt.index('static void xe_ggtt_initial_clear('):ggtt.index('/* All updates below')]
finish = ggtt[ggtt.index('void xe_ggtt_vf_bootstrap_finish('):ggtt.index('static void ggtt_node_fini(')]
fini = ggtt[ggtt.index('static void ggtt_fini(void'):ggtt.index('#ifdef CONFIG_LOCKDEP', ggtt.index('static void ggtt_fini(void'))]
bootstrap = vf[vf.index('int xe_gt_sriov_vf_bootstrap('):vf.index('/**\n * xe_gt_sriov_vf_guc_versions')]
uc = (xe / 'xe_uc.c').read_text()
reconnect = uc[uc.index('static int vf_uc_scratch_test('):uc.index('/**\n * xe_uc_init_post_hwconfig')]
abi = (xe / 'abi/guc_actions_sriov_abi.h').read_text()
constants = '\n'.join(line for line in abi.splitlines() if line.startswith('#define ') and
                      any(name in line for name in (
                          'GUC_ACTION_VF2GUC_MMIO_RELAY_SERVICE', 'GUC_ACTION_VF2GUC_VF_RESET',
                          'VF2GUC_MMIO_RELAY_SERVICE_', 'GUC_ACTION_VF2GUC_MATCH_VERSION',
                          'VF2GUC_MATCH_VERSION_', 'GUC_VERSION_',
                          'IOV_OPCODE_VF2PF_MMIO_', 'VF2PF_MMIO_HANDSHAKE_')))
abi = (xe / 'abi/guc_relay_actions_abi.h').read_text()
constants += '\n' + '\n'.join(line for line in abi.splitlines()
                              if line.startswith('#define ') and ('VF2PF_UPDATE_GGTT32_' in line or 'GUC_RELAY_ACTION_VF2PF_UPDATE_GGTT32' in line))
constants += '\n' + '\n'.join(line for line in (xe / 'xe_guc.h').read_text().splitlines()
                              if line.startswith(('#define MAKE_GUC_VER(', '#define MAKE_GUC_VER_STRUCT(')))
prefix = r'''
#include <assert.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <setjmp.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define IS_ALIGNED(v,a) (!((v) & ((a)-1)))
#define xe_tile_assert(t,c) assert(c)
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
#define xe_device_uc_enabled(x) true
#define BIT(n) (1u << (n))
#define BIT_ULL(n) (1ULL << (n))
#define GENMASK_ULL(h,l) ((~0ULL >> (63-(h))) & (~0ULL << (l)))
#define SZ_4K 4096
#define xe_tile_sriov_vf_ggtt(t) (4096ULL * 4096)
#include "regs/xe_gtt_defs.h"
#define GENMASK(h,l) ((uint32_t)((~0ULL >> (63-(h))) & (~0ULL << (l))))
#define FIELD_GET(m,v) (((v) & (m)) >> __builtin_ctz(m))
#define FIELD_PREP(m,v) (((u32)(v) << __builtin_ctz(m)) & (m))
#define FIELD_MAX(m) FIELD_GET(m,m)
#define FIELD_FIT(m,v) ((u64)(v) <= FIELD_MAX(m))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BUILD_BUG_ON(c) _Static_assert(!(c), #c)
#define unlikely(x) (x)
#define xe_gt_assert(g,c) assert(c)
#define xe_gt_sriov_err(...) ((void)0)
#define xe_gt_sriov_info(...) ((void)0)
#define xe_gt_sriov_notice(...) ((void)0)
#define xe_gt_sriov_dbg(...) ((void)0)
#define noinline __attribute__((noinline))
#define __noreturn __attribute__((noreturn))
#define lower_32_bits(x) ((u32)(x))
#define upper_32_bits(x) ((u32)((x) >> 32))
#define READ_ONCE(x) (x)
#define scoped_guard(t,p) for (int scope=1; scope; scope=0)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define HZ 1000
#define atomic_read(p) (*(p))
#define mutex_lock(p) ((void)0)
#define mutex_unlock(p) ((void)0)
#define min_t(t,a,b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define lockdep_assert_held(x) ((void)0)
#define xe_gt_err(...) ((void)0)
static void test_log(const char *format, ...) { }
#define xe_gt_info(g,...) test_log(__VA_ARGS__)
#define xe_tile_info(t,...) test_log(__VA_ARGS__)
#define GUC_MAX_MMIO_MSG_LEN 4
#define XE_PTE_SHIFT 12
#define XE_PAGE_SIZE 4096
struct xe_uc_fw_version { u32 branch, major, minor, patch; };
struct xe_gt_sriov_vf {
    bool test_reset_seen, test_relay_ready, test_ct_ggtt, test_ct_passed; u8 test_magic; int test_irqs;
    struct xe_uc_fw_version guc_version, wanted_guc_version;
};
struct xe_gt;
struct xe_guc_relay { int unused; };
struct xe_guc { bool ct; struct xe_gt *gt; struct xe_guc_relay relay; };
struct xe_tile;
struct xe_device { struct { int platform; } info; struct xe_tile *tile; };
enum { XE_TIGERLAKE, XE_PVC, XE_METEORLAKE };
static struct xe_device device = {.info = {XE_METEORLAKE}};
#define gt_to_xe(g) (&device)
#define guc_to_gt(g) ((g)->gt)
#define IS_SRIOV_VF(x) true
struct xe_uc { struct xe_guc guc; };
struct xe_gt { struct xe_tile *tile; struct { struct xe_gt_sriov_vf vf; } sriov; struct xe_uc uc; };
#define uc_to_gt(u) ((u)->guc.gt)
#define xe_guc_ct_enabled(c) (*(c))
struct xe_tile { struct xe_gt *primary_gt, *media_gt; unsigned id; struct { struct xe_ggtt *ggtt; } mem; };
struct drm_mm_node { u64 start, size; bool allocated; };
struct mock_mm { struct drm_mm_node *node; u64 size; };
struct xe_bo;
struct xe_ggtt;
struct xe_ggtt_pt_ops { u64 (*pte_encode_flags)(struct xe_bo *, u16); void (*ggtt_set_pte)(struct xe_ggtt *, u64, u64); };
struct xe_ggtt { struct xe_tile *tile; bool test_used, test_scratch_mapped; struct xe_bo *scratch; const struct xe_ggtt_pt_ops *pt_ops; u64 start, size; struct mock_mm mm; u32 test_ct_maps, test_ct_clears; int lock, test_ct_removed; unsigned flags; };
struct xe_ggtt_node { struct xe_ggtt *ggtt; struct drm_mm_node base; bool test_mapped, test_ct_owned, test_temporary, invalidate_on_remove; };
struct xe_bo { struct xe_ggtt_node *ggtt_node[1]; u64 size; u64 dma[2048]; };
#define XE_CACHE_WB 0
#define xe_cache_pat_idx(t,c) 2
#define xe_bo_addr(b,o,s) ((b)->dma[0])
#define for_each_gt(g,x,id) for (id=0; id<2; id++) if (((g) = (id ? (x)->tile->media_gt : (x)->tile->primary_gt)))
#define drm_mm_for_each_node(n,m) for (n=(m)->node; n && n->allocated; n=NULL)
#define drm_mm_for_each_hole(n,m,s,e) for (unsigned hi=0; hi<2; hi++) if (((n)=(m)->node, mock_hole(m,hi,&s,&e)))
static bool mock_hole(struct mock_mm *mm, unsigned i, u64 *s, u64 *e)
{
    if (!mm->node || !mm->node->allocated) { *s=0; *e=mm->size; return i==0 && *e; }
    *s = i ? mm->node->start + mm->node->size : 0;
    *e = i ? mm->size : mm->node->start;
    return *e > *s;
}
static u64 encode_scratch(struct xe_bo *bo, u16 pat) { assert(pat==2); return 0x20000000000001ULL; }
static void direct_pte(struct xe_ggtt *g, u64 addr, u64 pte) { assert(0); }
static const struct xe_ggtt_pt_ops pt_ops = {encode_scratch, direct_pte};
#define xe_bo_device(b) (&device)
#define for_each_tile(t,x,id) for (id=0,t=(x)->tile; id<1; id++)
#define tile_to_xe(t) (&device)
#define xe_gt_sriov_vf_bootstrap_test(x) true
#define XE_GGTT_FLAGS_ONLINE 1
#define XE_BO_FLAG_SYSTEM 1
#define XE_BO_FLAG_GGTT 2
#define XE_BO_FLAG_GGTT_INVALIDATE 4
#define XE_BO_FLAG_NEEDS_CPU_ACCESS 8
#define XE_BO_FLAG_NEEDS_UC 16
#define ttm_bo_type_kernel 0
struct xe_res_cursor { struct xe_bo *bo; u64 remaining; unsigned index; };
#define xe_bo_size(b) ((b)->size)
#define xe_bo_sg(b) (b)
static void xe_res_first_sg(struct xe_bo *bo, u64 offset, u64 size, struct xe_res_cursor *cur)
{ assert(!offset); *cur = (struct xe_res_cursor){bo, size, 0}; }
static u64 xe_res_dma(struct xe_res_cursor *cur) { return cur->bo->dma[cur->index]; }
static void xe_res_next(struct xe_res_cursor *cur, u64 bytes)
{ assert(bytes == XE_PAGE_SIZE); cur->remaining -= bytes; cur->index++; }
static jmp_buf held;
#define DECLARE_COMPLETION_ONSTACK(n) int n = 0
static void wait_for_completion(int *p) { (void)p; longjmp(held, 1); }
#include "abi/guc_messages_abi.h"
'''
mock = r'''
static u64 pt[4096];
static unsigned updates, handshakes, duplicate_batches, replicate_batches, fail_update;
static bool fail_handshake, fail_reset, bad_count;
static unsigned fail_reset_at;
static bool guc_negotiated, pf_negotiated, fail_version, changed_version;
static unsigned resets, disables, version_requests, version_queries, invalid_state;
static void xe_guc_ct_disable(bool *ct) { *ct = false; disables++; }
static unsigned counts[4096];
static int xe_guc_mmio_send_recv_once(struct xe_guc *guc, const u32 *req, u32 len, u32 *resp)
{
    (void)guc;
    if (FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, req[0]) == GUC_ACTION_VF2GUC_VF_RESET) {
        assert(len == 1 && !resp); resets++;
        guc_negotiated = pf_negotiated = false;
        return fail_reset && (!fail_reset_at || resets==fail_reset_at) ? -ETIMEDOUT : 0;
    }
    assert(len == 4);
    assert(FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, req[0]) == GUC_ACTION_VF2GUC_MMIO_RELAY_SERVICE);
    if (!guc_negotiated) { invalid_state++; return -ENXIO; }
    memset(resp, 0, 4*sizeof(u32));
    resp[0] = 0xf0000000u | (req[0] & VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC);
    unsigned opcode = FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_REQUEST_MSG_0_OPCODE, req[0]);
    if (opcode == IOV_OPCODE_VF2PF_MMIO_HANDSHAKE) {
        handshakes++;
        assert(req[1] == 0x10000 && !req[2] && !req[3]);
        if (fail_handshake) return -ETIMEDOUT;
        pf_negotiated = true;
        resp[1] = 0x10000;
        return resp[0] & 0xfffffff;
    }
    assert(opcode == IOV_OPCODE_VF2PF_MMIO_UPDATE_GGTT);
    assert(pf_negotiated);
    unsigned page = FIELD_GET(VF2PF_UPDATE_GGTT32_OFFSET, req[1]);
    unsigned n = FIELD_GET(VF2PF_UPDATE_GGTT32_COPIES, req[1]) + 1;
    unsigned mode = FIELD_GET(VF2PF_UPDATE_GGTT32_MODE, req[1]);
    u64 pte = (u64)req[2] | ((u64)req[3] << 32);
    assert(mode == 0 || mode == VF2PF_UPDATE_GGTT32_REPLICATE);
    assert(page+n <= ARRAY_SIZE(pt) && n <= 1024);
    counts[updates++] = n;
    if (mode) replicate_batches++; else duplicate_batches++;
    /* Apply the request even when the response is subsequently lost. */
    for (unsigned i=0; i<n; i++) pt[page+i] = pte + (mode ? (u64)i*4096 : 0);
    if (updates == fail_update) return -ETIMEDOUT;
    resp[0] |= bad_count ? n-1 : n;
    return resp[0] & 0xfffffff;
}
static unsigned ct_requests, ct_fault, ct_fault_at;
static int xe_guc_relay_send_to_pf_once(struct xe_guc_relay *relay, const u32 *req,
                                      u32 len, u32 *resp, u32 size)
{
    assert(len == 4 && size == 1);
    assert(FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, req[0]) == GUC_RELAY_ACTION_VF2PF_UPDATE_GGTT32);
    unsigned page = FIELD_GET(VF2PF_UPDATE_GGTT32_OFFSET, req[1]);
    unsigned n = FIELD_GET(VF2PF_UPDATE_GGTT32_COPIES, req[1]) + 1;
    unsigned mode = FIELD_GET(VF2PF_UPDATE_GGTT32_MODE, req[1]);
    u64 pte = req[2] | ((u64)req[3] << 32);
    assert(page + n <= ARRAY_SIZE(pt));
    ct_requests++;
    for (unsigned i=0; i<n; i++) pt[page+i] = pte + (mode ? (u64)i*4096 : 0);
    *resp = FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_RESPONSE_SUCCESS) | n;
    /* Faults happen after the PF has applied the mapping. */
    switch (!ct_fault_at || ct_requests == ct_fault_at ? ct_fault : 0) {
    case 1: return -ETIME;
    case 2: return -EAGAIN;
    case 3: *resp ^= 1; break;
    case 4: *resp |= FIELD_PREP(GUC_HXG_MSG_0_ORIGIN, GUC_HXG_ORIGIN_GUC); break;
    case 5: *resp = FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_RESPONSE_FAILURE); break;
    case 6: return 0;
    case 7: return 2;
    case 8: device.tile->primary_gt->sriov.vf.test_reset_seen = true; break;
    }
    return 1;
}
/* Exercise the real version encoder/validator; only firmware replies are fake. */
static int xe_guc_mmio_send_recv(struct xe_guc *guc, const u32 *req, u32 len, u32 *resp)
{
    assert(!guc->ct && resets >= 1 && disables == resets);
    assert(len == VF2GUC_MATCH_VERSION_REQUEST_MSG_LEN);
    assert(FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, req[0]) == GUC_ACTION_VF2GUC_MATCH_VERSION);
    assert(!FIELD_GET(VF2GUC_MATCH_VERSION_REQUEST_MSG_1_MBZ, req[1]));
    unsigned major = FIELD_GET(VF2GUC_MATCH_VERSION_REQUEST_MSG_1_MAJOR, req[1]);
    if (major == GUC_VERSION_MAJOR_ANY) {
        version_queries++;
    } else {
        version_requests++;
        assert(major == 1 && FIELD_GET(VF2GUC_MATCH_VERSION_REQUEST_MSG_1_MINOR, req[1]) == 2);
        if (fail_version) return -ENXIO;
        guc_negotiated = true;
    }
    memset(resp, 0, GUC_MAX_MMIO_MSG_LEN * sizeof(u32));
    resp[0] = 0xf0000000u;
    resp[1] = FIELD_PREP(VF2GUC_MATCH_VERSION_RESPONSE_MSG_1_MAJOR, 1) |
              FIELD_PREP(VF2GUC_MATCH_VERSION_RESPONSE_MSG_1_MINOR, changed_version ? 3 : 2);
    return 0;
}
static int vf_handshake_with_guc(struct xe_gt *gt);
static int vf_reset_guc_state(struct xe_gt *gt) { assert(0); return -EIO; }
static void complete(int *p) { *p = 1; }
static void reinit_completion(int *p) { *p = 0; }
static void drm_mm_remove_node(struct drm_mm_node *n) { n->allocated=false; }
static void ggtt_node_fini(struct xe_ggtt_node *n) { assert(!n->test_mapped); }
static void xe_ggtt_invalidate(struct xe_ggtt *g) { }
#define xe_ggtt_node_addr(n) ((n)->base.start)
#define xe_ggtt_node_size(n) ((n)->base.size)

'''
main_globals = r'''
static struct xe_gt gt;
static struct xe_tile tile;
static struct xe_ggtt ggtt;
static struct xe_ggtt_node node;
static struct xe_bo bo;
static const u64 flags = 0x20000000000001ULL;
static void setup(unsigned pages, bool fragmented)
{
    memset(&gt, 0, sizeof(gt));
    gt.uc.guc.gt = &gt;
    gt.sriov.vf.guc_version = (struct xe_uc_fw_version){0, 1, 2, 0};
    tile = (struct xe_tile){.primary_gt = &gt, .mem = {&ggtt}};
    gt.tile = &tile; device.tile = &tile;
    ggtt = (struct xe_ggtt){.tile = &tile, .size=4096ULL*4096, .start=0x7ec00000, .pt_ops=&pt_ops, .mm={&node.base,4096ULL*4096}};
    node = (struct xe_ggtt_node){.ggtt = &ggtt, .base = {7*4096, (u64)pages*4096, true}};
    bo.ggtt_node[0] = &node; bo.size = (u64)pages*4096;
    for (unsigned i=0; i<pages; i++) bo.dma[i] = 0x1000000ULL + (u64)i*4096 + (fragmented && i>=2 ? 8192 : 0);
    memset(pt, 0, sizeof(pt));
    updates = handshakes = duplicate_batches = replicate_batches = fail_update = 0;
    ct_requests = ct_fault = ct_fault_at = fail_reset_at = 0;
    fail_handshake = fail_reset = bad_count = false;
    resets = disables = version_requests = version_queries = invalid_state = 0;
    guc_negotiated = true;
    pf_negotiated = fail_version = changed_version = false;
}
'''
lifecycle_mocks = r'''
static unsigned allocations, releases, backing_frees, reclaim_blocked;
static unsigned reconnect_fault, enable_calls, connect_calls, query_calls;
static bool deferred_release, pending_release, missing_removal, create_fails, query_fails;
static struct xe_bo *xe_bo_create_pin_map_novm(struct xe_device *x, struct xe_tile *t,
                                             size_t size, int type, u32 flags_in, bool intr)
{
    allocations++;
    if (create_fails) return (void *)(intptr_t)-ENOMEM;
    assert(gt.uc.guc.ct && gt.sriov.vf.test_ct_ggtt);
    node.base.size = bo.size = size; node.base.start = 7*4096; node.base.allocated=true;
    bo.ggtt_node[0] = &node;
    for (unsigned i=0; i<size/4096; i++) bo.dma[i] = 0x1000000ULL + (u64)i*4096;
    vf_bootstrap_map_bo(&ggtt,&bo, flags_in & XE_BO_FLAG_NEEDS_UC ? 1 : flags);
    return &bo;
}
static void finish_release(void)
{
    pending_release = false;
    /* Reclaim must stay blocked in the unpin-to-delete window. */
    assert(xe_ggtt_vf_bootstrap_bo_mapped(&bo)); reclaim_blocked++;
    xe_ggtt_vf_bootstrap_unmap_bo(&bo);
    assert(!node.test_mapped && !xe_ggtt_vf_bootstrap_bo_mapped(&bo));
    backing_frees++;
    if (!missing_removal) ggtt_node_remove(&node);
}
static void xe_bo_unpin_map_no_vm(struct xe_bo *b)
{
    releases++;
    if (deferred_release) pending_release = true;
    else finish_release();
}
static long wait_for_completion_timeout(int *p, unsigned long timeout)
{
    if (pending_release) finish_release();
    return *p;
}
static int xe_guc_enable_communication(struct xe_guc *g)
{ enable_calls++; if (reconnect_fault==1) return -EIO; g->ct=true; return 0; }
static int xe_gt_sriov_vf_connect(struct xe_gt *g)
{ connect_calls++; return reconnect_fault==2 ? -EIO : 0; }
static int xe_gt_sriov_vf_query_runtime(struct xe_gt *g)
{ query_calls++; return query_fails || reconnect_fault==3 ? -EIO : 0; }
static void lifetime_setup(void)
{
    setup(1,false);
    gt.uc.guc.ct = gt.sriov.vf.test_ct_passed = true;
    allocations = releases = backing_frees = reclaim_blocked = 0;
    reconnect_fault = enable_calls = connect_calls = query_calls = 0;
    deferred_release = pending_release = missing_removal = create_fails = query_fails = false;
}
'''
main = r'''
int main(void)
{
    for (unsigned n=1; n<=1025; n += n==1 ? 1023 : 1) {
        setup(n, false);
        vf_bootstrap_map_bo(&ggtt, &bo, flags);
        assert(node.test_mapped && ggtt.test_used && handshakes == 1);
        assert(updates == (n+1023)/1024 && duplicate_batches == 0);
        for (unsigned i=0; i<n; i++) assert(pt[7+i] == (flags | bo.dma[i]));
        vf_bootstrap_unmap_node(&node);
        assert(!node.test_mapped && duplicate_batches == (n+1023)/1024);
        for (unsigned i=0; i<n; i++) assert(pt[7+i] == 1);
        unsigned before=updates;
        vf_bootstrap_unmap_node(&node);
        assert(updates == before);
        printf("PASS %u contiguous pages: bounded map batches, ownership clear, no duplicate unmap\n", n);
    }
    setup(4, true);
    vf_bootstrap_map_bo(&ggtt, &bo, flags);
    assert(updates == 2 && counts[0] == 2 && counts[1] == 2);
    for (unsigned i=0; i<4; i++) assert(pt[7+i] == (flags | bo.dma[i]));
    puts("PASS fragmented DMA: split at discontinuity");
    setup(1025, false); fail_update = 2;
    if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
    assert(updates == 2 && !node.test_mapped && !duplicate_batches);
    puts("PASS lost second map reply: hold, no rollback request");
    setup(1025, false); vf_bootstrap_map_bo(&ggtt, &bo, flags); fail_update = 3;
    if (!setjmp(held)) { vf_bootstrap_unmap_node(&node); assert(0); }
    assert(node.test_mapped && updates == 3);
    puts("PASS lost clear reply: mapping remains owned, no second clear");
    setup(1, false); fail_handshake = true;
    if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
    assert(!updates && !node.test_mapped);
    puts("PASS failed handshake: no update submitted");
    setup(1, false); gt.uc.guc.ct = true;
    if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
    assert(!updates && !handshakes);
    puts("PASS active CT guard: no bootstrap MMIO update");
    setup(1, false); gt.sriov.vf.test_reset_seen = true;
    if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
    assert(!updates && !handshakes);
    puts("PASS reset guard: no update after reset request");
    setup(1, false);
    if (!setjmp(held)) { xe_gt_sriov_vf_bootstrap_update(&gt, 0, flags, 1025, true); assert(0); }
    assert(!updates);
    puts("PASS oversized batch rejected before submission");
    setup(4, false); bad_count = true;
    if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
    assert(updates == 1 && !node.test_mapped && !duplicate_batches);
    puts("PASS wrong batch count: hold after submitted mapping");
    setup(1, false); gt.uc.guc.ct = true; gt.sriov.vf.test_relay_ready = true;
    xe_gt_sriov_vf_bootstrap_quiesce(&gt);
    assert(!gt.uc.guc.ct && resets == 1 && disables == 1 && !gt.sriov.vf.test_relay_ready);
    puts("PASS quiescence: stop CT then acknowledged single-attempt reset");
    setup(1, false); fail_reset = true; gt.sriov.vf.test_relay_ready = true;
    if (!setjmp(held)) { xe_gt_sriov_vf_bootstrap_quiesce(&gt); assert(0); }
    assert(resets == 1 && disables == 1 && gt.sriov.vf.test_relay_ready && !updates);
    puts("PASS lost consumer-reset reply: hold without clearing mappings");
    setup(1, false); gt.sriov.vf.test_reset_seen = true;
    if (!setjmp(held)) { xe_gt_sriov_vf_bootstrap_quiesce(&gt); assert(0); }
    assert(!resets && !disables);
    puts("PASS unexpected reset event: no recovery or cleanup attempted");
    setup(1025, false);
    vf_bootstrap_map_bo(&ggtt, &bo, flags);
    gt.uc.guc.ct = true;
    xe_gt_sriov_vf_bootstrap_quiesce(&gt);
    assert(version_requests == 1 && !version_queries && guc_negotiated && !pf_negotiated);
    vf_bootstrap_unmap_node(&node);
    assert(!gt.uc.guc.ct && !node.test_mapped && handshakes == 2 && updates == 4);
    assert(!invalid_state);
    for (unsigned i=0; i<1025; i++) assert(pt[7+i] == 1);
    puts("PASS map-reset-renegotiate-clear: version restored before PF handshake, CT stays disabled");
    setup(1, false);
    vf_bootstrap_map_bo(&ggtt, &bo, flags);
    /* Model v5's missing negotiation after successful reset. */
    guc_negotiated = pf_negotiated = gt.sriov.vf.test_relay_ready = false;
    if (!setjmp(held)) { vf_bootstrap_unmap_node(&node); assert(0); }
    assert(invalid_state == 1 && node.test_mapped && updates == 1 && !duplicate_batches);
    puts("PASS old sequence: INVALID_STATE before clear; mapping retained");
    setup(1, false);
    vf_bootstrap_map_bo(&ggtt, &bo, flags);
    fail_version = true;
    if (!setjmp(held)) { xe_gt_sriov_vf_bootstrap_quiesce(&gt); assert(0); }
    assert(node.test_mapped && updates == 1 && !duplicate_batches && !guc_negotiated);
    assert(version_requests == 1 && version_queries == 1 && handshakes == 1);
    puts("PASS failed post-reset version match: diagnostic version query only, no clear");
    setup(1, false);
    vf_bootstrap_map_bo(&ggtt, &bo, flags);
    changed_version = true;
    if (!setjmp(held)) { xe_gt_sriov_vf_bootstrap_quiesce(&gt); assert(0); }
    assert(node.test_mapped && updates == 1 && !duplicate_batches && handshakes == 1);
    assert(version_requests == 1);
    puts("PASS changed post-reset interface: existing Xe version check holds before clear");
    setup(1025, false);
    gt.uc.guc.ct = gt.sriov.vf.test_ct_passed = gt.sriov.vf.test_ct_ggtt = true;
    vf_bootstrap_map_bo(&ggtt, &bo, flags);
    assert(ct_requests == 2 && !updates && !handshakes && node.test_ct_owned);
    for (unsigned i=0; i<1025; i++) assert(pt[7+i] == (flags | bo.dma[i]));
    vf_bootstrap_unmap_node(&node);
    assert(ct_requests == 4 && !node.test_mapped && ggtt.test_ct_maps == 1025 && ggtt.test_ct_clears == 1025);
    for (unsigned i=0; i<1025; i++) assert(pt[7+i] == 1);
    puts("PASS CT 1025-page map/clear: correct PAT/DMA, split batches, no MMIO");
    setup(4, true);
    gt.uc.guc.ct = gt.sriov.vf.test_ct_passed = gt.sriov.vf.test_ct_ggtt = true;
    vf_bootstrap_map_bo(&ggtt, &bo, flags);
    assert(ct_requests == 2);
    for (unsigned i=0; i<4; i++) assert(pt[7+i] == (flags | bo.dma[i]));
    puts("PASS CT fragmented DMA preserves cursor addresses");
    for (volatile unsigned fault=1; fault<=8; fault++) {
        setup(1, false);
        gt.uc.guc.ct = gt.sriov.vf.test_ct_passed = gt.sriov.vf.test_ct_ggtt = true;
        ct_fault = fault;
        if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
        assert(ct_requests == 1 && !updates && !handshakes && !ggtt.test_ct_clears);
        printf("PASS CT map fault %u: hold without clear, fallback or replay\n", fault);
        setup(1, false);
        gt.uc.guc.ct = gt.sriov.vf.test_ct_passed = gt.sriov.vf.test_ct_ggtt = true;
        vf_bootstrap_map_bo(&ggtt, &bo, flags);
        ct_fault = fault;
        if (!setjmp(held)) { vf_bootstrap_unmap_node(&node); assert(0); }
        assert(ct_requests == 2 && node.test_mapped && !ggtt.test_ct_clears && !updates);
        printf("PASS CT clear fault %u: retain node/backing, no fallback\n", fault);
    }
    setup(1025, false);
    gt.uc.guc.ct = gt.sriov.vf.test_ct_passed = gt.sriov.vf.test_ct_ggtt = true;
    ct_fault = 1; ct_fault_at = 2;
    if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
    assert(ct_requests == 2 && !node.test_mapped && !ggtt.test_ct_clears && !updates);
    puts("PASS CT lost second map reply: partial mapping retained without rollback");
    setup(1, false); gt.sriov.vf.test_ct_ggtt = true;
    if (!setjmp(held)) { vf_bootstrap_map_bo(&ggtt, &bo, flags); assert(0); }
    assert(!updates && !handshakes && !ct_requests);
    puts("PASS lost CT: no MMIO fallback");
    setup(1, false);
    if (!setjmp(held)) { xe_gt_sriov_vf_bootstrap_update(&gt, 4095, flags, 2, true); assert(0); }
    assert(!updates && !ct_requests);
    puts("PASS allocation-end overrun rejected before relay");
    setup(1, false);
    if (!setjmp(held)) { xe_gt_sriov_vf_bootstrap_update(&gt, 0, flags | BIT(2), 1, true); assert(0); }
    assert(!updates && !ct_requests);
    puts("PASS PTE ownership bits rejected before relay");
    for (volatile unsigned deferred=0; deferred<2; deferred++) {
        lifetime_setup(); deferred_release = deferred;
        assert(!xe_ggtt_vf_ct_test(&gt));
        assert(allocations == 2 && releases == 2 && backing_frees == 2 && reclaim_blocked == 2);
        assert(ggtt.test_ct_maps == 1026 && ggtt.test_ct_clears == 1026 && gt.sriov.vf.test_ct_ggtt);
        assert(!updates && !resets && ct_requests == 6);
        puts(deferred ? "PASS deferred TTM release: wait for clear and node removal before next allocation" :
                        "PASS ordinary BO lifecycle: two allocations, clear before backing release, reclaim blocked while mapped");
    }
    lifetime_setup(); ct_fault = 1; ct_fault_at = 3;
    if (!setjmp(held)) { xe_ggtt_vf_ct_test(&gt); assert(0); }
    assert(allocations == 1 && releases == 1 && !backing_frees && node.test_mapped && !resets);
    puts("PASS CT lost clear reply in ordinary release: backing not freed, next BO not allocated");
    lifetime_setup(); missing_removal = true;
    if (!setjmp(held)) { xe_ggtt_vf_ct_test(&gt); assert(0); }
    assert(allocations == 1 && backing_frees == 1 && gt.sriov.vf.test_ct_ggtt);
    puts("PASS missing node removal: hold before next allocation or CT transition");
    lifetime_setup(); create_fails = true;
    if (!setjmp(held)) { xe_ggtt_vf_ct_test(&gt); assert(0); }
    assert(!releases && !backing_frees && !ct_requests && gt.sriov.vf.test_ct_ggtt);
    puts("PASS allocation failure: hold without quiescing possibly deferred cleanup");
    lifetime_setup(); query_fails = true;
    if (!setjmp(held)) { xe_ggtt_vf_ct_test(&gt); assert(0); }
    assert(allocations == 2 && backing_frees == 2 && gt.sriov.vf.test_ct_ggtt && !resets);
    puts("PASS final CT query failure: no success marker or consumer reset");

    static struct xe_bo scratch = {.size=4096, .dma={0x71000000}};
    const u64 scratch_pte = 0x20000071000001ULL;
    setup(1, false); ggtt.scratch=&scratch;
    gt.uc.guc.ct=gt.sriov.vf.test_ct_passed=gt.sriov.vf.test_ct_ggtt=true;
    vf_bootstrap_map_bo(&ggtt,&bo,flags);
    xe_ggtt_initial_clear(&ggtt);
    assert(ggtt.test_scratch_mapped && ct_requests == 6 && !updates);
    for (unsigned i=0; i<4096; i++) assert(pt[i] == (i==7 ? flags|bo.dma[0] : scratch_pte));
    puts("PASS scratch holes: preserve allocated node, duplicate DMA/PAT across all holes");
    assert(xe_ggtt_vf_bootstrap_bo_mapped(&scratch));
    if (!setjmp(held)) { xe_ggtt_vf_bootstrap_unmap_bo(&scratch); assert(0); }
    assert(ggtt.test_scratch_mapped && ggtt.scratch==&scratch);
    puts("PASS scratch reclaim and early backing release blocked without a GGTT node");
    if (!setjmp(held)) { ggtt_fini(&ggtt); assert(0); }
    assert(ggtt.scratch==&scratch);
    puts("PASS early devres fini retains scratch pointer while translations exist");
    vf_bootstrap_unmap_node(&node);
    assert(!node.test_mapped && pt[7]==scratch_pte && ggtt.test_scratch_mapped);
    ggtt_node_remove(&node);
    assert(!ggtt.test_ct_removed);
    puts("PASS ordinary CT node returns to scratch without completing temporary-node wait");
    assert(!xe_gt_sriov_vf_bootstrap(&gt));
    assert(!gt.uc.guc.ct && !gt.sriov.vf.test_ct_ggtt && !gt.sriov.vf.test_relay_ready);
    assert(resets==1 && version_requests==1);
    for (unsigned i=0; i<4096; i++) assert(pt[i]==scratch_pte);
    puts("PASS expected bootstrap reset: single attempt, fresh interface, scratch retained");
    gt.uc.guc.ct=gt.sriov.vf.test_ct_ggtt=true;
    vf_bootstrap_map_bo(&ggtt,&bo,flags);
    assert(node.test_mapped && pt[7]==(flags|bo.dma[0]));
    node.base.allocated=true;
    xe_ggtt_vf_bootstrap_finish(&device);
    assert(!node.test_mapped && !ggtt.test_scratch_mapped && !gt.uc.guc.ct);
    assert(resets==2 && version_requests==2 && updates==4);
    for (unsigned i=0; i<4096; i++) assert(pt[i]==1);
    assert(!xe_ggtt_vf_bootstrap_bo_mapped(&scratch));
    xe_ggtt_vf_bootstrap_unmap_bo(&scratch);
    ggtt_fini(&ggtt); assert(!ggtt.scratch);
    puts("PASS complete managed-range clear covers holes and nodes before scratch release");
    setup(1,false); ggtt.scratch=&scratch;
    gt.uc.guc.ct=gt.sriov.vf.test_ct_passed=gt.sriov.vf.test_ct_ggtt=true;
    ct_fault=1; ct_fault_at=2;
    if (!setjmp(held)) { xe_ggtt_initial_clear(&ggtt); assert(0); }
    assert(ct_requests==2 && ggtt.test_scratch_mapped && ggtt.test_used && !resets);
    puts("PASS partial scratch fill: uncertain reply retains backing without reset or rollback");
    setup(1,false); ggtt.scratch=&scratch; ggtt.test_scratch_mapped=ggtt.test_used=true;
    node.test_mapped=true; fail_update=2;
    if (!setjmp(held)) { xe_ggtt_vf_bootstrap_finish(&device); assert(0); }
    assert(updates==2 && node.test_mapped && ggtt.test_scratch_mapped && ggtt.scratch==&scratch);
    puts("PASS partial final clear: no node retirement or scratch release after lost reply");
    setup(1,false); ggtt.scratch=&scratch; ggtt.test_scratch_mapped=ggtt.test_used=true;
    node.test_mapped=true; fail_reset=true;
    if (!setjmp(held)) { xe_ggtt_vf_bootstrap_finish(&device); assert(0); }
    assert(!updates && node.test_mapped && ggtt.test_scratch_mapped);
    puts("PASS failed final reset: no full-range clear or backing release");
    for (volatile unsigned fault=0; fault<4; fault++) {
        setup(1,false);
        volatile u64 start=ggtt.start, size=4096;
        if (fault==0) start--;
        if (fault==1) size++;
        if (fault==2) start+=ggtt.size;
        if (fault==3) size=~0ULL-4095;
        if (!setjmp(held)) { vf_bootstrap_fill(&ggtt,start,size,scratch_pte); assert(0); }
        assert(!updates && !ct_requests);
    }
    puts("PASS invalid scratch fills: misalignment, underflow, overrun and huge size rejected before relay");
    setup(1,false);
    vf_bootstrap_fill(&ggtt,ggtt.start+ggtt.size,0,scratch_pte);
    assert(!updates && !ct_requests);
    puts("PASS empty fill at end: no request");
    lifetime_setup(); ggtt.scratch=&scratch; ggtt.test_scratch_mapped=true;
    ggtt.test_ct_maps=23; ggtt.test_ct_clears=7;
    assert(!xe_ggtt_vf_ct_test(&gt));
    assert(ggtt.test_ct_maps==1049 && ggtt.test_ct_clears==1033 && backing_frees==2);
    for (unsigned i=0; i<1025; i++) assert(pt[7+i]==scratch_pte);
    puts("PASS post-reset temporary lifetimes: scratch restore and delta accounting with earlier CT mappings");

    for (volatile unsigned fault=1; fault<=3; fault++) {
        lifetime_setup(); reconnect_fault=fault; gt.uc.guc.ct=false;
        if (!setjmp(held)) { vf_uc_scratch_test(&gt.uc); assert(0); }
        assert(enable_calls==1 && connect_calls==(fault>1) && query_calls==(fault>2));
        assert(!allocations && !updates && !resets);
        printf("PASS reconnect failure %u: hold before allocation, reset or teardown\n",fault);
    }
    lifetime_setup(); gt.uc.guc.ct=false; ggtt.scratch=&scratch; ggtt.test_scratch_mapped=true;
    assert(vf_uc_scratch_test(&gt.uc)==-EOPNOTSUPP);
    assert(enable_calls==1 && connect_calls==1 && query_calls==2 && backing_frees==2);
    assert(gt.uc.guc.ct && ggtt.test_scratch_mapped && !resets);
    puts("PASS real reconnect checkpoint: native enable/handshake/query, temporary lifetimes, deliberate stop");
    setup(1,false); ggtt.scratch=&scratch; ggtt.test_used=ggtt.test_scratch_mapped=true;
    node.test_mapped=true;
    struct xe_gt media = gt;
    media.uc.guc.gt=&media; tile.media_gt=&media;
    fail_reset=true; fail_reset_at=2;
    if (!setjmp(held)) { xe_ggtt_vf_bootstrap_finish(&device); assert(0); }
    assert(resets==2 && !updates && node.test_mapped && ggtt.test_scratch_mapped);
    puts("PASS media consumer-reset failure: no GGTT clear after primary-only acknowledgment");
    setup(1,false); ggtt.scratch=&scratch; ggtt.test_used=ggtt.test_scratch_mapped=true;
    node.test_mapped=true; media=gt; media.uc.guc.gt=&media; tile.media_gt=&media;
    xe_ggtt_vf_bootstrap_finish(&device);
    assert(resets==2 && version_requests==2 && updates==4 && !ggtt.test_scratch_mapped && !node.test_mapped);
    puts("PASS both GT consumers reset and renegotiated before shared GGTT cleanup");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='xe-bootstrap-test-') as temp:
    c = Path(temp) / 'test.c'
    exe = Path(temp) / 'test'
    c.write_text(prefix + constants + mock + helpers + update + quiesce + negotiation + bootstrap + fill + initial + mapper + unmapper + lifetime + finish + fini + remove + main_globals + lifecycle_mocks + experiment + reconnect + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-O2', '-Wall', '-Wextra',
                    '-Werror', '-Wno-sign-compare', '-Wno-unused-parameter',
                    '-Wno-unused-but-set-variable', *shlex.split(os.environ.get('CFLAGS', '')), '-I', str(xe),
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
