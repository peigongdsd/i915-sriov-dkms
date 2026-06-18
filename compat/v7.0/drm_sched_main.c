/*
 * Copyright (c) 2026
 *
 * Backport functionality for older kernels
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#include <linux/export.h>
#include <drm/gpu_scheduler.h>

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0)
/**
 * drm_sched_is_stopped() - Checks whether drm_sched is stopped
 * @sched: DRM scheduler
 *
 * Return: true if sched is stopped, false otherwise
 */
bool drm_sched_is_stopped(struct drm_gpu_scheduler *sched)
{
	return READ_ONCE(sched->pause_submit);
}
EXPORT_SYMBOL(drm_sched_is_stopped);

/**
 * drm_sched_job_is_signaled() - DRM scheduler job is signaled
 * @job: DRM scheduler job
 *
 * Determine if DRM scheduler job is signaled. DRM scheduler should be stopped
 * to obtain a stable snapshot of state. Both parent fence (hardware fence) and
 * finished fence (software fence) are checked to determine signaling state.
 *
 * Return: true if job is signaled, false otherwise
 */
bool drm_sched_job_is_signaled(struct drm_sched_job *job)
{
	struct drm_sched_fence *s_fence = job->s_fence;

	WARN_ON(!drm_sched_is_stopped(job->sched));
	return (s_fence->parent && dma_fence_is_signaled(s_fence->parent)) ||
		dma_fence_is_signaled(&s_fence->finished);
}
EXPORT_SYMBOL(drm_sched_job_is_signaled);
#endif
