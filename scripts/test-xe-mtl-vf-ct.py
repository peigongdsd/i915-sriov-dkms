#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the actual single-attempt CT/relay code with scripted completions.

The ring, firmware, locks and clock are modeled. This tests control flow and
lifetime of the software waiters, not hardware ordering or kernel concurrency.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

xe = Path(__file__).resolve().parents[1] / 'drivers/gpu/drm/xe'
ct = (xe / 'xe_guc_ct.c').read_text()
relay = (xe / 'xe_guc_relay.c').read_text()
core = ct[ct.index('#define GUC_SEND_RETRY_LIMIT'):ct.index('static u32 *msg_to_hxg(')]
send = relay[relay.index('static int relay_send_transaction('):relay.index('static void __fini_relay(')]
once = relay[relay.index('int xe_guc_relay_send_to_pf_once('):relay.index('static int relay_handle_failure(')]
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define BIT(n) (1u << (n))
#define GENMASK(h,l) ((uint32_t)((~0ULL >> (63-(h))) & (~0ULL << (l))))
#define FIELD_GET(m,v) (((v) & (m)) >> __builtin_ctz(m))
#include "abi/guc_messages_abi.h"
#define FIELD_PREP(m,v) (((u32)(v) << __builtin_ctz(m)) & (m))
#define HZ 1000
''' + next(line for line in relay.splitlines() if line.startswith('#define RELAY_TIMEOUT_MSEC')) + r'''

#define GUC_RELAY_MSG_MIN_LEN 1
#define GUC_RELAY_MSG_MAX_LEN 16
#define GUC_CTB_MAX_DWORDS 256
#define PFID 0
#define GFP_KERNEL 0
#define unlikely(x) (x)
#define READ_ONCE(x) (x)
#define time_before(a,b) ((long)((a)-(b)) < 0)
#define time_after_eq(a,b) (!time_before(a,b))
#define msecs_to_jiffies(x) (x)
#define KUNIT_STATIC_STUB_REDIRECT(...) ((void)0)
#define ALLOW_ERROR_INJECTION(...)
#define xe_gt_dbg(...) ((void)0)
#define xe_gt_warn(...) ((void)0)
#define xe_gt_err(...) ((void)0)
#define relay_debug(...) ((void)0)
#define relay_notice(...) ((void)0)
#define relay_assert(r,c) assert(c)
#define IS_SRIOV_VF(x) true
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define LNL_FLUSH_WORK(...) ((void)0)
#define guard(t) int unused_guard __attribute__((unused)) = 0; (void)
#define xe_device_wedged(x) false
struct xe_gt { int unused; };
static struct xe_gt test_gt;
#define ct_to_gt(c) (&test_gt)
#define ct_to_xe(c) NULL
struct g2h_fence {
    bool done, wait, retry, fail, cancel;
    unsigned seqno, counter, reason, error, hint, response_len, response_data;
};
struct xe_gt_sriov_pf_ggtt_token { int unused; };
struct xe_guc_ct {
    int lock, g2h_fence_wq;
    struct g2h_fence *fence_lookup;
};
static unsigned long jiffies;
static unsigned sends, resets, locks, waits;
static struct xe_guc_ct *current_ct;
enum reply { OK, BUSY, RETRY, FAIL, LOST, FAIL_BUSY, FAIL_NOMSG };
static enum reply guc_replies[128];
static unsigned guc_index;
static void mutex_lock(int *p) { assert(!*p); *p=1; locks++; }
static void mutex_unlock(int *p) { assert(*p); *p=0; locks--; }
static void kick_reset(struct xe_guc_ct *ct) { resets++; }
static bool retry_failure(struct xe_guc_ct *ct, int ret) { return false; }
static void g2h_fence_init(struct g2h_fence *f, u32 *buf) { memset(f,0,sizeof(*f)); }
static void g2h_fence_reinit(struct g2h_fence *f) { f->wait=f->done=false; }
static bool g2h_fence_needs_alloc(struct g2h_fence *f) { return !f->seqno; }
static void xa_erase(struct g2h_fence **p, u32 seqno) { *p=NULL; }
static void *xa_store(struct g2h_fence **p, u32 seqno, struct g2h_fence *f, int flags)
{ *p=f; return NULL; }
#define xa_err(p) ((p) ? -ENOMEM : 0)
static void msleep(unsigned ms) { jiffies += ms; }
static int guc_ct_send(struct xe_guc_ct *ct, const u32 *a, u32 len, u32 g2h, u32 num,
                       struct g2h_fence *f)
{
    assert(!ct->fence_lookup);
    sends++;
    f->seqno = sends;
    ct->fence_lookup = f;
    current_ct = ct;
    return 0;
}
static int guc_ct_send_retry_locked(struct xe_guc_ct *ct, const u32 *a, u32 len,
                                    u32 g2h, u32 num, struct g2h_fence *f,
                                    u32 vfid, const struct xe_gt_sriov_pf_ggtt_token *token)
{ return guc_ct_send(ct,a,len,g2h,num,f); }
static int firmware_wait(unsigned long timeout)
{
    assert(!locks);
    waits++;
    if (!timeout) return 0;
    struct g2h_fence *f = current_ct->fence_lookup;
    enum reply r = guc_replies[guc_index++];
    if (r == LOST) { jiffies += timeout; return 0; }
    jiffies += timeout < 200 ? timeout : 200;
    f->done = true;
    if (r == BUSY) f->wait = true;
    else {
        current_ct->fence_lookup = NULL;
        f->retry = r == RETRY;
        f->fail = r == FAIL;
    }
    return 1;
}
#define wait_event_timeout(wq,cond,t) firmware_wait(t)
'''
relay_mock = r'''
static int xe_guc_ct_send_block(struct xe_guc_ct *ct, const u32 *a, u32 len)
{ return xe_guc_ct_send_recv(ct,a,len,NULL); }
struct list_head { bool linked; };
struct completion { bool done; };
struct relay_transaction {
    bool incoming, ggtt_update, no_retry;
    u32 request_len, response_len, offset, remote, rid;
    u32 request_buf[256], response_buf[256];
    u32 *response;
    int reply;
    struct completion done;
    struct list_head link;
    struct xe_gt_sriov_pf_ggtt_token ggtt_token;
};
struct xe_guc_relay { int lock; struct list_head pending_relays; struct xe_guc_ct ct; };
static struct relay_transaction transaction;
static unsigned releases, pf_index, completion_waits;
static enum reply pf_replies[64];
static bool ready = true, wrong_rid, busy_then_success;
#define relay_to_ct(r) (&(r)->ct)
#define relay_to_xe(r) NULL
#define relay_to_gt(r) (&test_gt)
static bool xe_gt_sriov_pf_service_ggtt_current(struct xe_gt *g, u32 vfid,
                                               const struct xe_gt_sriov_pf_ggtt_token *t)
{ return true; }
static void spin_lock(int *p) { assert(!*p); *p=1; locks++; }
static void spin_unlock(int *p) { assert(*p); *p=0; locks--; }
static void list_add_tail(struct list_head *l, struct list_head *head)
{ assert(!l->linked); l->linked=true; }
static void list_del_init(struct list_head *l) { assert(l->linked); l->linked=false; }
#define list_for_each_entry(p,h,m) for (p=&transaction; p && p->link.linked; p=NULL)
static void complete_all(struct completion *c) { c->done=true; }
static void reinit_completion(struct completion *c)
{ assert(locks); c->done=false; }
static int from_relay_error(int e) { return -e; }
static struct relay_transaction *relay_new_transaction(struct xe_guc_relay *relay,
                                 u32 target, const u32 *msg, u32 len, u32 *buf, u32 size)
{
    if (!ready) return (void *)(intptr_t)-ENODEV;
    memset(&transaction,0,sizeof(transaction));
    transaction.request_len=len; transaction.offset=2; transaction.rid=42;
    memcpy(transaction.request_buf+2,msg,len*sizeof(u32));
    transaction.response=buf; transaction.response_len=size; transaction.reply=-ENOMSG;
    return &transaction;
}
static void relay_release_transaction(struct xe_guc_relay *r, struct relay_transaction *t)
{ assert(!t->link.linked && !locks && !r->ct.fence_lookup); releases++; }
static int relay_handle_reply(struct xe_guc_relay *,u32,u32,int,const u32 *,u32);
static struct xe_guc_relay *active_relay;
static long wait_for_completion_timeout(struct completion *c, unsigned long timeout)
{
    assert(!locks);
    completion_waits++;
    if (c->done) return timeout ? timeout : 1;
    if (!timeout) return 0;
    enum reply r = pf_replies[pf_index++];
    if (r == LOST) { jiffies+=timeout; return 0; }
    jiffies += timeout < 100 ? timeout : 100;
    u32 response = FIELD_PREP(GUC_HXG_MSG_0_TYPE,GUC_HXG_TYPE_RESPONSE_SUCCESS) | 1;
    int reply = r == RETRY ? -EAGAIN : r == BUSY ? -EBUSY : r == FAIL ? EIO : r == FAIL_BUSY ? EBUSY : r == FAIL_NOMSG ? ENOMSG : 0;
    int ret = relay_handle_reply(active_relay,0,wrong_rid ? 43 : 42,reply,&response,1);
    if (wrong_rid) { assert(ret == -ESRCH); jiffies+=timeout; return 0; }
    assert(!ret);
    /* Complete SUCCESS before the waiter consumes BUSY: no reinit may lose it. */
    if (r == BUSY && busy_then_success)
        assert(!relay_handle_reply(active_relay,0,42,0,&response,1));
    return 1;
}
'''
main = r'''
static struct xe_guc_relay relay;
static const u32 msg[] = { 0x102, 0, 1, 0 };
static void setup(void)
{
    memset(&relay,0,sizeof(relay)); memset(&transaction,0,sizeof(transaction));
    memset(guc_replies,0,sizeof(guc_replies)); memset(pf_replies,0,sizeof(pf_replies));
    jiffies=sends=resets=locks=waits=releases=pf_index=guc_index=completion_waits=0;
    active_relay=&relay; ready=true; wrong_rid=busy_then_success=false;
}
int main(void)
{
    u32 response;
    setup();
    assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==1);
    assert(sends==1 && releases==1 && !relay.ct.fence_lookup);
    puts("PASS common CT/relay success: one GuC send, matching PF reply, waiters removed");
    for (unsigned i=0;i<2;i++) {
        setup(); if(i) pf_replies[0]=RETRY; else guc_replies[0]=RETRY;
        assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==-EAGAIN);
        assert(sends==1 && releases==1);
        puts(i ? "PASS PF RETRY: no replay" : "PASS GuC RETRY: no replay");
        setup(); if(i) pf_replies[0]=LOST; else guc_replies[0]=LOST;
        assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==-ETIME);
        assert(sends==1 && releases==1 && !relay.ct.fence_lookup);
        assert(relay_handle_reply(&relay,0,42,0,&response,1)==-ESRCH);
        puts(i ? "PASS lost PF reply: no replay, late reply cannot access released waiter" :
                 "PASS lost GuC reply: no replay, both waiters removed");
        setup(); if(i) pf_replies[0]=BUSY; else guc_replies[0]=BUSY;
        assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==1);
        assert(sends==1 && releases==1);
        puts(i ? "PASS PF BUSY then success: wait without resend" : "PASS GuC BUSY then success: wait without resend");
        setup();
        for (unsigned j=0;j<32;j++) { if(i) pf_replies[j]=BUSY; else guc_replies[j]=BUSY; }
        assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==-ETIME);
        assert(sends==1 && releases==1 && jiffies <= HZ + RELAY_TIMEOUT_MSEC);
        puts(i ? "PASS PF repeated BUSY: bounded deadline" : "PASS GuC repeated BUSY: bounded deadline");
        setup(); if(i) pf_replies[0]=FAIL; else guc_replies[0]=FAIL;
        assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==-EIO);
        assert(sends==1 && releases==1);
        puts(i ? "PASS PF failure propagated" : "PASS GuC failure propagated");
    }
    for (unsigned i=0;i<2;i++) {
        setup(); pf_replies[0]=i ? FAIL_NOMSG : FAIL_BUSY;
        assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==(i ? -ENOMSG : -EBUSY));
        assert(sends==1 && completion_waits==1 && releases==1);
        puts(i ? "PASS PF ENOMSG failure is terminal, not missing response" :
                 "PASS PF EBUSY failure is terminal, not a BUSY notification");
    }
    setup(); pf_replies[0]=BUSY; busy_then_success=true;
    assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==1);
    assert(completion_waits==1 && releases==1);
    puts("PASS success overtaking BUSY: completion not discarded");
    setup(); wrong_rid=true;
    assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==-ETIME);
    assert(sends==1 && releases==1);
    puts("PASS wrong RID ignored, no response misattribution");
    setup(); ready=false;
    assert(xe_guc_relay_send_to_pf_once(&relay,msg,4,&response,1)==-ENODEV);
    assert(!sends && !releases);
    puts("PASS unavailable relay: no send");
    setup(); guc_replies[0]=RETRY;
    assert(!xe_guc_ct_send_recv(&relay.ct,msg,4,NULL));
    assert(sends==2 && !relay.ct.fence_lookup);
    puts("PASS ordinary CT retains firmware RETRY behavior");
    setup();
    assert(xe_guc_relay_send_to_pf_once(&relay,msg,0,&response,1)==-EINVAL);
    assert(!sends && !releases);
    puts("PASS invalid request rejected before allocation");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='xe-ct-once-') as temp:
    c = Path(temp) / 'test.c'
    exe = Path(temp) / 'test'
    c.write_text(prefix + core + relay_mock + send + once + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-O2', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-parameter', '-Wno-unused-variable',
                    *shlex.split(os.environ.get('CFLAGS', '')), '-I', str(xe),
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
