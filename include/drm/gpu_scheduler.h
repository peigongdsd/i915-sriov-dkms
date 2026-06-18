#include_next <drm/gpu_scheduler.h>
#ifndef __BACKPORT_DRM_GPU_SCHEDULER_H__
#define __BACKPORT_DRM_GPU_SCHEDULER_H__

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0)

#define drm_sched_is_stopped LINUX_BACKPORT(drm_sched_is_stopped)
bool drm_sched_is_stopped(struct drm_gpu_scheduler *sched);
#define drm_sched_job_is_signaled LINUX_BACKPORT(drm_sched_job_is_signaled)
bool drm_sched_job_is_signaled(struct drm_sched_job *job);


/**
 * struct drm_sched_pending_job_iter - DRM scheduler pending job iterator state
 * @sched: DRM scheduler associated with pending job iterator
 */
struct drm_sched_pending_job_iter {
	struct drm_gpu_scheduler *sched;
};

/* Drivers should never call this directly */
static inline struct drm_sched_pending_job_iter
__drm_sched_pending_job_iter_begin(struct drm_gpu_scheduler *sched)
{
	struct drm_sched_pending_job_iter iter = {
		.sched = sched,
	};

	WARN_ON(!drm_sched_is_stopped(sched));
	return iter;
}

/* Drivers should never call this directly */
static inline void
__drm_sched_pending_job_iter_end(const struct drm_sched_pending_job_iter iter)
{
	WARN_ON(!drm_sched_is_stopped(iter.sched));
}

DEFINE_CLASS(drm_sched_pending_job_iter, struct drm_sched_pending_job_iter,
	     __drm_sched_pending_job_iter_end(_T),
	     __drm_sched_pending_job_iter_begin(__sched),
	     struct drm_gpu_scheduler *__sched);
static inline void *
class_drm_sched_pending_job_iter_lock_ptr(class_drm_sched_pending_job_iter_t *_T)
{ return _T; }
#define class_drm_sched_pending_job_iter_is_conditional false

/**
 * drm_sched_for_each_pending_job() - Iterator for each pending job in scheduler
 * @__job: Current pending job being iterated over
 * @__sched: DRM scheduler to iterate over pending jobs
 * @__entity: DRM scheduler entity to filter jobs, NULL indicates no filter
 *
 * Iterator for each pending job in scheduler, filtering on an entity, and
 * enforcing scheduler is fully stopped
 */
#define drm_sched_for_each_pending_job(__job, __sched, __entity)		\
	scoped_guard(drm_sched_pending_job_iter, (__sched))			\
		list_for_each_entry((__job), &(__sched)->pending_list, list)	\
			for_each_if(!(__entity) || (__job)->entity == (__entity))
#endif
#endif
