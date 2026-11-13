/* SPDX-License-Identifier: MIT */
/* Exercise the driver's issue and error-policy paths with captured fence I/O. */
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct xe_tlb_inval;
struct xe_tlb_inval_fence {
	struct { int error; } base;
	unsigned int seqno;
};
struct ops {
	int (*ggtt)(struct xe_tlb_inval *, unsigned int);
	int (*all)(struct xe_tlb_inval *, unsigned int);
};
struct xe_tlb_inval { const struct ops *ops; int seqno_lock; };
#define xe_assert(xe, expr) assert(expr)
#define READ_ONCE(x) (x)
static unsigned int prepared, signalled, waited, issued;
static int issue_error, completion_error;
static void mutex_lock(int *lock) { assert(!*lock); *lock = 1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock = 0; }
static void xe_tlb_inval_fence_init(struct xe_tlb_inval *t,
				  struct xe_tlb_inval_fence *f, bool stack)
{
	(void)t;
	assert(stack);
	memset(f, 0, sizeof(*f));
}
static void xe_tlb_inval_fence_prep(struct xe_tlb_inval_fence *f)
{
	f->seqno = ++prepared;
}
static void xe_tlb_inval_fence_signal_unlocked(struct xe_tlb_inval_fence *f)
{
	assert(f->seqno);
	signalled++;
}
static void xe_tlb_inval_fence_wait(struct xe_tlb_inval_fence *f)
{
	waited++;
	if (!issue_error)
		f->base.error = completion_error;
}
static int issue(struct xe_tlb_inval *t, unsigned int seqno)
{
	assert(t->seqno_lock && seqno == prepared);
	issued++;
	return issue_error;
}
#include "actual-functions.inc"
static void check(int send_error, int fence_error, int ordinary, int strict)
{
	const struct ops ops = { .ggtt = issue, .all = issue };
	struct xe_tlb_inval t = { .ops = &ops };
	struct xe_tlb_inval_fence f;

	issue_error = send_error;
	completion_error = fence_error;
	prepared = signalled = waited = issued = 0;
	assert(xe_tlb_inval_ggtt(&t) == ordinary);
	assert(xe_tlb_inval_ggtt_sync(&t) == strict);
	assert(prepared == 2 && issued == 2 && waited == 2);
	assert(signalled == (send_error < 0 ? 2U : 0U));
	assert(!t.seqno_lock);
	/* The shared issue refactor must preserve the asynchronous API too. */
	xe_tlb_inval_fence_init(&t, &f, true);
	assert(xe_tlb_inval_all(&t, &f) == ordinary);
	assert(prepared == 3 && issued == 3 && waited == 2);
	assert(!t.seqno_lock);
}
int main(void)
{
	check(0, 0, 0, 0);
	check(-ECANCELED, 0, 0, -ECANCELED);
	check(-ENOTRECOVERABLE, 0, 0, -ENOTRECOVERABLE);
	check(-ENOMEM, 0, -ENOMEM, -ENOMEM);
	check(-EIO, 0, -EIO, -EIO);
	check(0, -ETIME, 0, -ETIME);
	puts("Strict and ordinary Xe TLB invalidation error tests passed");
	return 0;
}
