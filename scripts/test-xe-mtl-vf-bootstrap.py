#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile actual v5 batching/relay/clear helpers with fake DMA and PF replies.

These tests exercise bounds, encoding and failure decisions, not device DMA,
firmware reset ordering, IRQ delivery or the kernel's TTM/devres integration.
"""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
xe = root / 'drivers/gpu/drm/xe'
vf = (xe / 'xe_gt_sriov_vf.c').read_text()
ggtt = (xe / 'xe_ggtt.c').read_text()
helpers = vf[vf.index('static int vf_test_mmio_relay('):
             vf.index('/*\n * Test the working PF')]
update = vf[vf.index('void xe_gt_sriov_vf_bootstrap_update('):
            vf.index('/* No GGTT update is outstanding:')]
quiesce = vf[vf.index('void xe_gt_sriov_vf_bootstrap_quiesce('):
              vf.index('static int guc_action_match_version(')]
mapper = ggtt[ggtt.index('static void vf_bootstrap_map_bo('):
              ggtt.index('/**\n * xe_ggtt_map_bo -')]
unmapper = ggtt[ggtt.index('static void vf_bootstrap_unmap_node('):
                ggtt.index('/* TTM calls this')]
abi = (xe / 'abi/guc_actions_sriov_abi.h').read_text()
constants = '\n'.join(line for line in abi.splitlines() if line.startswith('#define ') and
                      any(name in line for name in (
                          'GUC_ACTION_VF2GUC_MMIO_RELAY_SERVICE', 'GUC_ACTION_VF2GUC_VF_RESET',
                          'VF2GUC_MMIO_RELAY_SERVICE_',
                          'IOV_OPCODE_VF2PF_MMIO_', 'VF2PF_MMIO_HANDSHAKE_')))
abi = (xe / 'abi/guc_relay_actions_abi.h').read_text()
constants += '\n' + '\n'.join(line for line in abi.splitlines()
                              if line.startswith('#define ') and 'VF2PF_UPDATE_GGTT32_' in line)
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <setjmp.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1u << (n))
#define GENMASK(h,l) ((uint32_t)((~0ULL >> (63-(h))) & (~0ULL << (l))))
#define FIELD_GET(m,v) (((v) & (m)) >> __builtin_ctz(m))
#define FIELD_PREP(m,v) (((u32)(v) << __builtin_ctz(m)) & (m))
#define FIELD_MAX(m) FIELD_GET(m,m)
#define FIELD_FIT(m,v) ((u64)(v) <= FIELD_MAX(m))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define noinline __attribute__((noinline))
#define __noreturn __attribute__((noreturn))
#define lower_32_bits(x) ((u32)(x))
#define upper_32_bits(x) ((u32)((x) >> 32))
#define READ_ONCE(x) (x)
#define min_t(t,a,b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define lockdep_assert_held(x) ((void)0)
#define xe_gt_err(...) ((void)0)
#define xe_gt_info(...) ((void)0)
#define xe_tile_info(...) ((void)0)
#define GUC_MAX_MMIO_MSG_LEN 4
#define XE_PTE_SHIFT 12
#define XE_PAGE_SIZE 4096
#define XE_PAGE_PRESENT 1
struct xe_gt_sriov_vf { bool test_reset_seen, test_relay_ready; u8 test_magic; };
struct xe_guc { bool ct; };
struct xe_gt { struct { struct xe_gt_sriov_vf vf; } sriov; struct {struct xe_guc guc;} uc; };
#define xe_guc_ct_enabled(c) (*(c))
struct xe_tile { struct xe_gt *primary_gt; unsigned id; };
struct xe_ggtt { struct xe_tile *tile; bool test_used; };
struct xe_ggtt_node { struct xe_ggtt *ggtt; struct {u64 start, size;} base; bool test_mapped; };
struct xe_bo { struct xe_ggtt_node *ggtt_node[1]; u64 size; u64 dma[2048]; };
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
static unsigned resets, disables;
static void xe_guc_ct_disable(bool *ct) { *ct = false; disables++; }
static unsigned counts[4096];
static int xe_guc_mmio_send_recv_once(struct xe_guc *guc, const u32 *req, u32 len, u32 *resp)
{
    (void)guc;
    if (FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, req[0]) == GUC_ACTION_VF2GUC_VF_RESET) {
        assert(len == 1 && !resp); resets++;
        return fail_reset ? -ETIMEDOUT : 0;
    }
    assert(len == 4);
    assert(FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, req[0]) == GUC_ACTION_VF2GUC_MMIO_RELAY_SERVICE);
    memset(resp, 0, 4*sizeof(u32));
    resp[0] = 0xf0000000u | (req[0] & VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC);
    unsigned opcode = FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_REQUEST_MSG_0_OPCODE, req[0]);
    if (opcode == IOV_OPCODE_VF2PF_MMIO_HANDSHAKE) {
        handshakes++;
        assert(req[1] == 0x10000 && !req[2] && !req[3]);
        if (fail_handshake) return -ETIMEDOUT;
        resp[1] = 0x10000;
        return resp[0] & 0xfffffff;
    }
    assert(opcode == IOV_OPCODE_VF2PF_MMIO_UPDATE_GGTT);
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
'''
main = r'''
static struct xe_gt gt;
static struct xe_tile tile;
static struct xe_ggtt ggtt;
static struct xe_ggtt_node node;
static struct xe_bo bo;
static const u64 flags = 0x20000000000001ULL;
static void setup(unsigned pages, bool fragmented)
{
    memset(&gt, 0, sizeof(gt));
    tile = (struct xe_tile){&gt, 0};
    ggtt = (struct xe_ggtt){&tile, false};
    node = (struct xe_ggtt_node){&ggtt, {7*4096, (u64)pages*4096}, false};
    bo.ggtt_node[0] = &node; bo.size = (u64)pages*4096;
    for (unsigned i=0; i<pages; i++) bo.dma[i] = 0x1000000ULL + (u64)i*4096 + (fragmented && i>=2 ? 8192 : 0);
    memset(pt, 0, sizeof(pt));
    updates = handshakes = duplicate_batches = replicate_batches = fail_update = 0;
    fail_handshake = fail_reset = bad_count = false;
    resets = disables = 0;
}
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
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='xe-bootstrap-test-') as temp:
    c = Path(temp) / 'test.c'
    exe = Path(temp) / 'test'
    c.write_text(prefix + constants + mock + helpers + update + quiesce + mapper + unmapper + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-O2', '-Wall', '-Wextra',
                    '-Werror', '-Wno-sign-compare', '-Wno-unused-parameter',
                    '-Wno-unused-but-set-variable', '-I', str(xe),
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
