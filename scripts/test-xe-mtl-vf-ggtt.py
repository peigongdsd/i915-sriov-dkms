#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile actual native batching/relay/clear helpers with fake DMA and PF replies.

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
guc = (xe / 'xe_guc.c').read_text()

softreset = guc[guc.index('int xe_guc_softreset('):guc.index('int xe_guc_suspend(')]
helpers = vf[vf.index('static int vf_mmio_relay('):vf.index('bool xe_gt_sriov_vf_native(')]
containment = ggtt[ggtt.index('bool xe_ggtt_vf_failed('):ggtt.index('static u64 xelp_ggtt_pte_flags(')]
update = vf[vf.index('static void vf_ct_update_ggtt('):vf.index('static int guc_action_match_version(')]
negotiation = vf[vf.index('static int guc_action_match_version('):vf.index('/**\n * xe_gt_sriov_vf_bootstrap -')]
mapper = ggtt[ggtt.index('static void vf_ggtt_map_bo('):ggtt.index('/**\n * xe_ggtt_map_bo -')]
unmapper = ggtt[ggtt.index('static void vf_ggtt_unmap_node('):ggtt.index('/* BO reservation held')]
lifetime = ggtt[ggtt.index('/* BO reservation held'):ggtt.index('static void ggtt_node_fini(')]
remove = ggtt[ggtt.index('static void ggtt_node_remove(struct'):ggtt.index('static void ggtt_node_remove_work_func(')]
fill = ggtt[ggtt.index('static u64 xe_ggtt_scratch_pte('):ggtt.index('static void primelockdep(')]
initial = ggtt[ggtt.index('static void xe_ggtt_initial_clear('):ggtt.index('/* All updates below')]
fini = ggtt[ggtt.index('static void ggtt_fini(void'):ggtt.index('#ifdef CONFIG_LOCKDEP', ggtt.index('static void ggtt_fini(void'))]
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
constants += '\nenum {\n' + next(line for line in (xe / 'abi/guc_actions_abi.h').read_text().splitlines()
                                      if 'XE_GUC_ACTION_CLIENT_SOFT_RESET =' in line) + '\n};\n'
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
#define WRITE_ONCE(x,v) ((x) = (v))
#define scoped_guard(t,p) for (int scope=1; scope; scope=0)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define HZ 1000
#define atomic_read(p) (*(p))
#define mutex_lock(p) ((void)0)
#define mutex_unlock(p) ((void)(ggtt_unlocks++))
static unsigned ggtt_unlocks;
#define min_t(t,a,b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define lockdep_assert_held(x) ((void)0)
#define xe_gt_err(...) ((void)0)
static void test_log(const char *format, ...) { }
#define xe_gt_info(g,...) test_log(__VA_ARGS__)
#define xe_gt_dbg(g,...) test_log(__VA_ARGS__)
#define xe_tile_info(t,...) test_log(__VA_ARGS__)
#define xe_tile_dbg(t,...) test_log(__VA_ARGS__)
#define GUC_MAX_MMIO_MSG_LEN 4
#define XE_PTE_SHIFT 12
#define XE_PAGE_SIZE 4096
struct xe_uc_fw_version { u32 branch, major, minor, patch; };
struct xe_gt_sriov_vf {
    bool ggtt_relay_ready; u8 ggtt_magic;
    struct xe_uc_fw_version guc_version, wanted_guc_version;
};
struct xe_gt;
struct xe_guc_relay { int unused; };
struct xe_guc { bool fw; bool ct; struct xe_gt *gt; struct xe_guc_relay relay; };
struct xe_tile;
struct xe_device { struct { int platform; } info; struct xe_tile *tile; };
enum { XE_TIGERLAKE, XE_PVC, XE_METEORLAKE };
static struct xe_device device = {.info = {XE_METEORLAKE}};
#define gt_to_xe(g) (&device)
#define guc_to_gt(g) ((g)->gt)
#define guc_to_xe(g) (&device)
#define xe_uc_fw_is_running(f) (*(f))
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
struct xe_ggtt { struct xe_tile *tile; bool vf_scratch_mapped, vf_failed; struct xe_bo *scratch; const struct xe_ggtt_pt_ops *pt_ops; u64 start, size; struct mock_mm mm; int lock; unsigned flags; };
struct xe_ggtt_node { struct xe_ggtt *ggtt; struct drm_mm_node base; bool vf_mapped, invalidate_on_remove; };
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
static bool native_mode = true;
#define xe_gt_sriov_vf_native(x) native_mode
#define guard(t) __attribute__((unused)) int guard_value = 0; (void)
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
static unsigned softresets, interface_minor;
static int softreset_error;
static int xe_guc_mmio_send(struct xe_guc *guc, const u32 *req, u32 len)
{
    assert(len == 1 && req[0] == XE_GUC_ACTION_CLIENT_SOFT_RESET);
    softresets++;
    guc_negotiated = pf_negotiated = false;
    return softreset_error;
}
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
    }
    return 1;
}
/* Exercise the real version encoder/validator; only firmware replies are fake. */
static int xe_guc_mmio_send_recv(struct xe_guc *guc, const u32 *req, u32 len, u32 *resp)
{
    assert(!guc->ct);
    if (!native_mode) assert(resets >= 1 && disables == resets);
    assert(len == VF2GUC_MATCH_VERSION_REQUEST_MSG_LEN);
    assert(FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, req[0]) == GUC_ACTION_VF2GUC_MATCH_VERSION);
    assert(!FIELD_GET(VF2GUC_MATCH_VERSION_REQUEST_MSG_1_MBZ, req[1]));
    unsigned major = FIELD_GET(VF2GUC_MATCH_VERSION_REQUEST_MSG_1_MAJOR, req[1]);
    if (major == GUC_VERSION_MAJOR_ANY) {
        version_queries++;
    } else {
        version_requests++;
        assert(major == 1 && FIELD_GET(VF2GUC_MATCH_VERSION_REQUEST_MSG_1_MINOR, req[1]) == interface_minor);
        if (fail_version) return -ENXIO;
        guc_negotiated = true;
    }
    memset(resp, 0, GUC_MAX_MMIO_MSG_LEN * sizeof(u32));
    resp[0] = 0xf0000000u;
    resp[1] = FIELD_PREP(VF2GUC_MATCH_VERSION_RESPONSE_MSG_1_MAJOR, 1) |
              FIELD_PREP(VF2GUC_MATCH_VERSION_RESPONSE_MSG_1_MINOR, interface_minor + changed_version);
    return 0;
}
static int vf_handshake_with_guc(struct xe_gt *gt);
static void drm_mm_remove_node(struct drm_mm_node *n) { n->allocated=false; }
static void ggtt_node_fini(struct xe_ggtt_node *n) { assert(!n->vf_mapped); }
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
    gt.uc.guc.fw = true;
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
    softresets = 0; softreset_error = 0; interface_minor = 2; ggtt_unlocks = 0;
    guc_negotiated = true;
    pf_negotiated = fail_version = changed_version = false;
}
'''
lifecycle_mocks = r'''
static unsigned backing_frees;
static void lifetime_setup(void)
{
    setup(1, false);
    gt.uc.guc.ct = true;
    backing_frees = 0;
}
'''
main = r'''
int main(void)
{
    static struct xe_bo scratch = {.size=4096, .dma={0x71000000}};
    for (unsigned transport=0; transport<2; transport++) {
        for (unsigned n=1; n<=1025; n += n==1 ? 1023 : 1) {
            setup(n,false); gt.uc.guc.ct=transport;
            vf_ggtt_map_bo(&ggtt,&bo,flags);
            assert(node.vf_mapped);
            assert((transport ? ct_requests : updates)==(n+1023)/1024);
            for (unsigned i=0;i<n;i++) assert(pt[7+i]==(flags|bo.dma[i]));
            assert(xe_ggtt_vf_bo_mapped(&bo));
            xe_ggtt_vf_unmap_bo(&bo);
            assert(!node.vf_mapped && !xe_ggtt_vf_bo_mapped(&bo));
            for (unsigned i=0;i<n;i++) assert(pt[7+i]==1);
            ggtt_node_remove(&node); assert(!node.base.allocated);
            printf("PASS transport %u size %u: map, reclaim exclusion, clear before node removal\n",transport,n);
        }
        setup(4,true); gt.uc.guc.ct=transport;
        vf_ggtt_map_bo(&ggtt,&bo,flags);
        assert((transport ? ct_requests : updates)==2);
        for (unsigned i=0;i<4;i++) assert(pt[7+i]==(flags|bo.dma[i]));
        printf("PASS fragmented transport %u splits at DMA discontinuity\n",transport);
    }
    for (volatile unsigned fault=1;fault<=7;fault++) {
        setup(1,false); gt.uc.guc.ct=true; ct_fault=fault;
        if (!setjmp(held)) { vf_ggtt_map_bo(&ggtt,&bo,flags); assert(0); }
        assert(ct_requests==1 && ggtt.vf_failed && node.base.allocated && !updates);
        printf("PASS CT map fault %u retains node without replay\n",fault);
        setup(1,false); gt.uc.guc.ct=true;
        vf_ggtt_map_bo(&ggtt,&bo,flags); ct_fault=fault;
        if (!setjmp(held)) { vf_ggtt_unmap_node(&node); assert(0); }
        assert(ct_requests==2 && node.vf_mapped && ggtt.vf_failed && !updates);
        printf("PASS CT clear fault %u retains backing without MMIO fallback\n",fault);
    }
    setup(1025,false); fail_update=2;
    if (!setjmp(held)) { vf_ggtt_map_bo(&ggtt,&bo,flags); assert(0); }
    assert(updates==2 && ggtt.vf_failed && node.base.allocated && !duplicate_batches);
    puts("PASS lost second MMIO map reply: partial mapping retained without rollback");
    setup(1,false);
    if (!setjmp(held)) { xe_gt_sriov_vf_update_ggtt(&gt,4095,flags,2,true); assert(0); }
    assert(!updates && !ct_requests);
    puts("PASS allocation overrun rejected before submission");
    setup(1,false);
    if (!setjmp(held)) { xe_gt_sriov_vf_update_ggtt(&gt,0,flags|BIT(2),1,true); assert(0); }
    assert(!updates && !ct_requests);
    puts("PASS ownership bits rejected before submission");
    setup(1,false); ggtt.scratch=&scratch; gt.uc.guc.ct=true;
    vf_ggtt_map_bo(&ggtt,&bo,flags);
    xe_ggtt_initial_clear(&ggtt);
    for (unsigned i=0;i<4096;i++) assert(pt[i]==(i==7 ? flags|bo.dma[0] : 0x20000071000001ULL));
    assert(xe_ggtt_vf_bo_mapped(&scratch));
    if (!setjmp(held)) { xe_ggtt_vf_unmap_bo(&scratch); assert(0); }
    assert(ggtt.vf_scratch_mapped && ggtt.scratch==&scratch);
    puts("PASS scratch holes preserve allocated mappings and retain scratch backing");
    lifetime_setup(); native_mode=true;
    vf_ggtt_map_bo(&ggtt,&bo,0x20000000000001ULL);
    assert(ct_requests==1 && !handshakes);
    puts("PASS native CT mapping uses ordinary enabled CT without diagnostic phases");

    vf_ggtt_unmap_node(&node);
    assert(!node.vf_mapped && ct_requests==2);
    puts("PASS native early allocation retires over CT using normal BO lifetime");

    lifetime_setup(); native_mode=true;
    gt.uc.guc.ct=false;
    vf_ggtt_map_bo(&ggtt,&bo,0x20000000000001ULL);
    assert(updates==1 && handshakes==1);
    puts("PASS native MMIO mapping allowed after ordinary CT shutdown");

    lifetime_setup(); native_mode=true;
    ggtt.scratch=&scratch; ggtt.vf_scratch_mapped=true;
    node.base=(struct drm_mm_node){4096,4096,true}; node.vf_mapped=true;
    pt[1]=0xabc001;
    ggtt_fini(&ggtt);
    assert(!ggtt.scratch && !ggtt.vf_scratch_mapped && node.vf_mapped);
    for (unsigned i=0;i<4096;i++) assert(pt[i]==(i==1 ? 0xabc001 : 1));
    puts("PASS native scratch fini clears holes while preserving live CT/BO mapping");

    lifetime_setup(); native_mode=true;
    ggtt.scratch=&scratch; ggtt.vf_scratch_mapped=true;
    node.base=(struct drm_mm_node){4096,4096,true}; node.vf_mapped=false;
    pt[1]=0xdead001;
    ggtt_fini(&ggtt);
    assert(!ggtt.scratch && !ggtt.vf_scratch_mapped);
    for (unsigned i=0;i<4096;i++) assert(pt[i]==1);
    puts("PASS native scratch fini includes retired nodes awaiting software removal");

    lifetime_setup(); native_mode=true;
    ggtt.scratch=&scratch; ggtt.vf_scratch_mapped=true; ct_fault=1;
    if (!setjmp(held)) { ggtt_fini(&ggtt); assert(0); }
    assert(ggtt.scratch==&scratch && ggtt.vf_scratch_mapped);
    puts("PASS lost native scratch clear retains backing rather than freeing live DMA");

    /* Reproduce the captured -ENXIO before any PF handshake or PTE clear. */
    lifetime_setup(); native_mode=true; gt.uc.guc.ct=false;
    gt.sriov.vf.guc_version.minor=interface_minor=26;
    node.vf_mapped=true; pt[7]=0xabc001;
    guc_negotiated=pf_negotiated=false;
    u32 response[GUC_MAX_MMIO_MSG_LEN]={};
    int ret=vf_mmio_relay(&gt, IOV_OPCODE_VF2PF_MMIO_HANDSHAKE, 1,
                             FIELD_PREP(VF2PF_MMIO_HANDSHAKE_REQUEST_MSG_1_MAJOR, 1),
                             0, 0, response);
    assert(ret==-ENXIO && invalid_state==1 && !handshakes && !updates);
    assert(node.vf_mapped && pt[7]==0xabc001);
    puts("PASS missing GuC interface rejects old PF handshake before any PTE request");

    vf_ggtt_unmap_node(&node);
    assert(!node.vf_mapped && pt[7]==1);
    assert(version_requests==1 && handshakes==1 && updates==1 && !resets && !softresets);
    assert(invalid_state==1 && !ct_requests);
    puts("PASS native late clear restores GuC then PF interface without another reset");

    node.vf_mapped=true; pt[7]=0xabc001;
    vf_ggtt_unmap_node(&node);
    assert(!node.vf_mapped && pt[7]==1 && updates==2);
    assert(version_requests==1 && handshakes==1);
    puts("PASS subsequent MMIO clear reuses negotiated interfaces");

    lifetime_setup(); native_mode=true; gt.uc.guc.ct=false;
    node.vf_mapped=true; pt[7]=0xabc001;
    gt.sriov.vf.ggtt_relay_ready=true; pf_negotiated=true;
    assert(!xe_guc_softreset(&gt.uc.guc));
    assert(softresets==1 && !gt.sriov.vf.ggtt_relay_ready && !guc_negotiated);
    vf_ggtt_unmap_node(&node);
    assert(!node.vf_mapped && pt[7]==1);
    assert(version_requests==1 && handshakes==1 && updates==1 && !resets);
    puts("PASS ordinary client soft reset invalidates cached native relay before late clear");

    lifetime_setup(); native_mode=true; gt.uc.guc.ct=false;
    node.vf_mapped=true; pt[7]=0xabc001;
    guc_negotiated=false; fail_version=true;
    if (!setjmp(held)) { vf_ggtt_unmap_node(&node); assert(0); }
    assert(node.vf_mapped && pt[7]==0xabc001 && !gt.sriov.vf.ggtt_relay_ready);
    assert(version_requests==1 && !handshakes && !updates && !backing_frees);
    puts("PASS failed GuC restore retains mapping and backing without PF request");

    lifetime_setup(); native_mode=true; gt.uc.guc.ct=false;
    node.vf_mapped=true; pt[7]=0xabc001; changed_version=true;
    if (!setjmp(held)) { vf_ggtt_unmap_node(&node); assert(0); }
    assert(node.vf_mapped && pt[7]==0xabc001 && !gt.sriov.vf.ggtt_relay_ready);
    assert(version_requests==1 && !handshakes && !updates && !backing_frees);
    puts("PASS native late clear retains original version consistency check");

    lifetime_setup(); native_mode=true;
    gt.sriov.vf.ggtt_relay_ready=true; softreset_error=-ENXIO;
    assert(xe_guc_softreset(&gt.uc.guc)==-ENXIO);
    assert(softresets==1 && !gt.sriov.vf.ggtt_relay_ready && !updates && !version_requests);
    puts("PASS client reset error propagates unchanged with native cache invalidated");

    lifetime_setup(); native_mode=true; gt.uc.guc.fw=false;
    gt.sriov.vf.ggtt_relay_ready=true;
    assert(!xe_guc_softreset(&gt.uc.guc));
    assert(!softresets && gt.sriov.vf.ggtt_relay_ready && !updates && !version_requests);
    puts("PASS stopped firmware retains ordinary soft reset early return");

    lifetime_setup(); native_mode=false; gt.sriov.vf.ggtt_relay_ready=true;
    assert(!xe_guc_softreset(&gt.uc.guc));
    assert(softresets==1 && gt.sriov.vf.ggtt_relay_ready && !version_requests && !updates);
    puts("PASS non-native client soft reset does not change relay cache policy");
    setup(4, false); native_mode=true;
    gt.uc.guc.ct=true; ct_fault=1;
    if (!setjmp(held)) { vf_ggtt_map_bo(&ggtt,&bo,flags); assert(0); }
    assert(ggtt.vf_failed && xe_ggtt_vf_failed(&device));
    assert(ggtt_unlocks==1 && node.base.allocated && bo.ggtt_node[0]==&node);
    unsigned sent = ct_requests;
    if (!setjmp(held)) { xe_gt_sriov_vf_update_ggtt(&gt,7,flags,1,true); assert(0); }
    assert(ct_requests==sent && ggtt_unlocks==2);
    puts("PASS failed native mapping releases shared mutex, retains node, forbids later updates");
    setup(4, false); native_mode=true;
    gt.uc.guc.ct=true; vf_ggtt_map_bo(&ggtt,&bo,flags);
    ct_fault=1;
    if (!setjmp(held)) { vf_ggtt_unmap_node(&node); assert(0); }
    assert(ggtt.vf_failed && node.vf_mapped && node.base.allocated && ggtt_unlocks==1);
    puts("PASS uncertain native clear retains mapped backing without holding shared mutex");
    native_mode=false;
    assert(!xe_ggtt_vf_failed(&device));
    puts("PASS non-native devices do not inherit diagnostic ioctl failure state");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='xe-vf-ggtt-test-') as temp:
    c = Path(temp) / 'test.c'
    exe = Path(temp) / 'test'
    c.write_text(prefix + constants + mock + helpers + containment + update + negotiation + softreset + fill + initial + mapper + unmapper + lifetime + fini + remove + main_globals + lifecycle_mocks + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-O2', '-Wall', '-Wextra',
                    '-Werror', '-Wno-sign-compare', '-Wno-unused-parameter',
                    '-Wno-unused-but-set-variable', *shlex.split(os.environ.get('CFLAGS', '')), '-I', str(xe),
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
