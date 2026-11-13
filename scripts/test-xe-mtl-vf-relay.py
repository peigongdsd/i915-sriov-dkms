#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the actual v4 C helpers with scripted MMIO replies, without hardware.

This checks request encoding, no-replay behavior and failure containment. It
cannot validate firmware ordering, DMA visibility, TLB completion or VF reset.
Run from any directory with CC pointing at a host C compiler if necessary.
"""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
xe = root / "drivers/gpu/drm/xe"
guc = (xe / "xe_guc.c").read_text()
vf = (xe / "xe_gt_sriov_vf.c").read_text()
transport = guc[guc.index("static int guc_mmio_send_recv("):
                guc.index("int xe_guc_mmio_send(struct", guc.index("static int guc_mmio_send_recv("))]
transaction = vf[vf.index("static int vf_test_mmio_relay("):
                 vf.index("static int guc_action_match_version(")]
abi = (xe / "abi/guc_actions_sriov_abi.h").read_text()
# The tested wire constants come from the real driver header too.
constants = "\n".join(line for line in abi.splitlines() if line.startswith("#define ") and
                      any(name in line for name in (
                          "GUC_ACTION_VF2GUC_MMIO_RELAY_SERVICE", "VF2GUC_MMIO_RELAY_SERVICE_",
                          "IOV_OPCODE_VF2PF_MMIO_", "VF2PF_MMIO_HANDSHAKE_")))
relay = (xe / "abi/guc_relay_actions_abi.h").read_text()
constants += "\n" + next(line for line in relay.splitlines()
                         if line.startswith("#define VF2PF_UPDATE_GGTT32_OFFSET"))

prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <setjmp.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#define GENMASK(h,l) ((uint32_t)((~0ULL >> (63-(h))) & (~0ULL << (l))))
#define FIELD_GET(m,v) (((v) & (m)) >> __builtin_ctz(m))
#define FIELD_PREP(m,v) (((u32)(v) << __builtin_ctz(m)) & (m))
#define FIELD_MAX(m) FIELD_GET(m,m)
#define FIELD_FIT(m,v) ((u64)(v) <= FIELD_MAX(m))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BUILD_BUG_ON(c) _Static_assert(!(c), #c)
#define unlikely(x) (x)
#define noinline __attribute__((noinline))
#define __noreturn __attribute__((noreturn))
#define lower_32_bits(x) ((u32)(x))
#define upper_32_bits(x) ((u32)((x) >> 32))
#define xe_assert(x,c) assert(c)
#define xe_gt_dbg(...) ((void)0)
#define xe_gt_err(...) ((void)0)
#define xe_gt_info(...) ((void)0)
#define ALLOW_ERROR_INJECTION(...)
#define GUC_MAX_MMIO_MSG_LEN 4
#define VF_SW_FLAG_COUNT 4
#define MED_VF_SW_FLAG_COUNT 4
#define MAX_RETRIES_ON_FLR 2
#define MIN_SLEEP_MS_ON_FLR 256
#define XE_GUC_RESPONSE_VF_MIGRATED 0x100
struct xe_reg { u32 addr; };
#define VF_SW_FLAG(i) ((struct xe_reg){(i)*4})
#define MED_VF_SW_FLAG(i) VF_SW_FLAG(i)
struct xe_mmio { int unused; };
struct xe_device { int unused; };
struct xe_gt;
struct xe_guc { struct xe_gt *gt; };
struct xe_gt { struct xe_mmio mmio; struct {struct xe_guc guc;} uc; };
static struct xe_device dev;
#define guc_to_xe(g) (&dev)
#define guc_to_gt(g) ((g)->gt)
#define xe_gt_is_media_type(g) false
static jmp_buf held;
#define DECLARE_COMPLETION_ONSTACK(n) int n = 0
static void wait_for_completion(int *p) { (void)p; longjmp(held, 1); }
static void xe_sleep_relaxed_ms(unsigned x) { (void)x; }
static void xe_sleep_exponential_ms(unsigned *x, unsigned y) { (void)x; (void)y; }
#include "abi/guc_messages_abi.h"
'''
mock = r'''
static u32 requests[8][4], scratch[4], response[4];
static unsigned sends, waits;
static int scenario;
static bool standalone;
static const u64 test_pte = 0x2000001e58e001ULL;
static void xe_mmio_write32(struct xe_mmio *m, struct xe_reg r, u32 v)
{ (void)m; scratch[r.addr / 4] = v; }
static u32 xe_mmio_read32(struct xe_mmio *m, struct xe_reg r)
{ (void)m; return response[r.addr / 4]; }
static void xe_guc_notify(struct xe_guc *g)
{
    (void)g;
    assert(sends < 8);
    for (int i=0; i<4; i++) requests[sends][i] = scratch[i];
    sends++;
    waits = 0;
    u32 magic = FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, scratch[0]);
    response[0] = FIELD_PREP(GUC_HXG_MSG_0_ORIGIN, GUC_HXG_ORIGIN_GUC) |
                  FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_RESPONSE_SUCCESS) |
                  FIELD_PREP(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, magic) |
                  (standalone || sends > 1 ? 1 : 0);
    response[1] = standalone || sends > 1 ? 0 : 0x10000;
    response[2] = response[3] = 0;
}
static int xe_mmio_wait32(struct xe_mmio *m, struct xe_reg r, u32 mask,
                          u32 val, unsigned timeout, u32 *out, bool atomic)
{
    (void)m; (void)r; (void)mask; (void)val; (void)timeout; (void)atomic;
    waits++;
    u32 header = response[0];
    int ret = 0;
    if (standalone) {
        if (sends == 1 && scenario == 11) { header = 0; ret = -ETIMEDOUT; }
        if (sends == 1 && scenario == 12)
            header = 0x80000000u | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_NO_RESPONSE_RETRY);
    } else {
        if ((scenario == 1 && sends == 1) || (scenario == 3 && sends == 2))
            header = 0x80000000u | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_RESPONSE_FAILURE) | 1;
        if (scenario == 2 && sends == 1) response[1] = 0x20000;
        if ((scenario == 4 && sends == 2) || (scenario == 7 && sends == 3)) {
            header = 0x80000000u | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_NO_RESPONSE_BUSY);
            if (waits == 2) ret = -ETIMEDOUT;
        }
        if ((scenario == 5 && sends == 2) || (scenario == 8 && sends == 3))
            header ^= FIELD_PREP(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, 1);
        if (scenario == 6 && sends == 2) header &= ~VF2GUC_MMIO_RELAY_SERVICE_RESPONSE_MSG_0_DATA0;
        if (scenario == 9 && sends == 2) { header = 0; ret = -ETIMEDOUT; }
        if (scenario == 10 && sends == 2)
            header = 0x80000000u | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_NO_RESPONSE_RETRY);
        if (scenario == 13 && sends == 2 && waits == 1)
            header = 0x80000000u | FIELD_PREP(GUC_HXG_MSG_0_TYPE, GUC_HXG_TYPE_NO_RESPONSE_BUSY);
    }
    *out = header;
    return ret;
}
'''
main = r'''
int main(void)
{
    struct xe_gt gt = {0};
    gt.uc.guc.gt = &gt;
    for (scenario = 0; scenario <= 13; scenario++) {
        sends = 0;
        standalone = scenario == 11 || scenario == 12;
        if (setjmp(held)) {
            assert(scenario >= 3 && scenario <= 10);
            assert(sends == (scenario == 7 || scenario == 8 ? 3 : 2));
            printf("PASS scenario %d: held, no retry or later request\n", scenario);
            continue;
        }
        if (standalone) {
            u32 req[4] = {0}, resp[4];
            assert(xe_guc_mmio_send_recv(&gt.uc.guc, req, 4, resp) == 1);
            assert(sends == 2);
            printf("PASS scenario %d: existing caller still replays\n", scenario);
            continue;
        }
        int ret = xe_gt_sriov_vf_test_ggtt(&gt, 7, test_pte);
        if (scenario == 1 || scenario == 2) {
            assert(ret < 0 && sends == 1);
            printf("PASS scenario %d: handshake failure, no PTE request\n", scenario);
            continue;
        }
        assert(scenario == 0 || scenario == 13);
        assert(ret == 0 && sends == 3);
        assert(requests[0][1] == 0x10000);
        for (unsigned n=0; n<3; n++) {
            assert(FIELD_GET(GUC_HXG_REQUEST_MSG_0_ACTION, requests[n][0]) == GUC_ACTION_VF2GUC_MMIO_RELAY_SERVICE);
            assert(FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_MSG_0_MAGIC, requests[n][0]) == n+1);
        }
        assert(FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_REQUEST_MSG_0_OPCODE, requests[0][0]) == IOV_OPCODE_VF2PF_MMIO_HANDSHAKE);
        for (unsigned n=1; n<3; n++) {
            assert(FIELD_GET(VF2GUC_MMIO_RELAY_SERVICE_REQUEST_MSG_0_OPCODE, requests[n][0]) == IOV_OPCODE_VF2PF_MMIO_UPDATE_GGTT);
            assert(requests[n][1] == (7 << 12));
        }
        assert(requests[1][2] == lower_32_bits(test_pte));
        assert(requests[1][3] == upper_32_bits(test_pte));
        assert(requests[2][2] == 1 && requests[2][3] == 0);
        printf("PASS scenario %d: map then ownership restore, distinct magic\n", scenario);
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="xe-relay-test-") as temp:
    c = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    c.write_text(prefix + constants + mock + transport + transaction + main)
    subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-Wno-sign-compare", "-Wno-unused-variable", "-Wno-unused-parameter", "-I", str(xe),
                    str(c), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
