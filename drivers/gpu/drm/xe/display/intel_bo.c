// SPDX-License-Identifier: MIT
/* Copyright © 2024 Intel Corporation */

#include <drm/drm_cache.h>
#include <drm/drm_gem.h>
#include <drm/drm_print.h>

#include "xe_bo.h"
#include "intel_bo.h"
#include "intel_frontbuffer.h"

bool intel_bo_is_tiled(struct drm_gem_object *obj)
{
	/* legacy tiling is unused */
	return false;
}

bool intel_bo_is_userptr(struct drm_gem_object *obj)
{
	/* xe does not have userptr bos */
	return false;
}

bool intel_bo_is_shmem(struct drm_gem_object *obj)
{
	return false;
}

bool intel_bo_is_protected(struct drm_gem_object *obj)
{
	return xe_bo_is_protected(gem_to_xe_bo(obj));
}

int intel_bo_fb_mmap(struct drm_gem_object *obj, struct vm_area_struct *vma)
{
	return drm_gem_prime_mmap(obj, vma);
}

int intel_bo_read_from_page(struct drm_gem_object *obj, u64 offset, void *dst, int size)
{
	struct xe_bo *bo = gem_to_xe_bo(obj);

	return xe_bo_read(bo, offset, dst, size);
}

struct xe_frontbuffer {
	struct intel_frontbuffer base;
	struct drm_gem_object *obj;
	struct kref ref;
};

struct intel_frontbuffer *intel_bo_frontbuffer_get(struct drm_gem_object *obj)
{
	struct xe_frontbuffer *front;

	front = kmalloc(sizeof(*front), GFP_KERNEL);
	if (!front)
		return NULL;

	intel_frontbuffer_init(&front->base, obj->dev);

	kref_init(&front->ref);

	drm_gem_object_get(obj);
	front->obj = obj;

	return &front->base;
}

void intel_bo_frontbuffer_ref(struct intel_frontbuffer *_front)
{
	struct xe_frontbuffer *front =
		container_of(_front, typeof(*front), base);

	kref_get(&front->ref);
}

static void frontbuffer_release(struct kref *ref)
{
	struct xe_frontbuffer *front =
		container_of(ref, typeof(*front), ref);

	intel_frontbuffer_fini(&front->base);

	drm_gem_object_put(front->obj);

	kfree(front);
}

void intel_bo_frontbuffer_put(struct intel_frontbuffer *_front)
{
	struct xe_frontbuffer *front =
		container_of(_front, typeof(*front), base);

	kref_put(&front->ref, frontbuffer_release);
}

void intel_bo_frontbuffer_flush_for_display(struct intel_frontbuffer *front)
{
	struct xe_frontbuffer *xe_front =
		container_of(front, typeof(*xe_front), base);
	struct drm_gem_object *obj = xe_front->obj;
	struct xe_bo *bo = gem_to_xe_bo(obj);
	struct xe_device *xe = to_xe_device(obj->dev);
	int ret;

	/*
	 * Keep this experiment narrow: only flush user scanout BOs backed by
	 * normal system pages. This restores a real display flush hook on xe
	 * without changing VRAM/stolen paths.
	 */
	if (!(bo->flags & XE_BO_FLAG_SCANOUT) ||
	    !(bo->flags & XE_BO_FLAG_USER) ||
	    xe_bo_is_vram(bo) ||
	    xe_bo_is_stolen(bo))
		return;

	ret = xe_bo_lock(bo, false);
	if (ret)
		return;

	if (bo->ttm.ttm &&
	    ttm_tt_is_populated(bo->ttm.ttm) &&
	    xe_bo_sg(bo) &&
	    xe_bo_sg(bo)->sgl &&
	    sg_page(xe_bo_sg(bo)->sgl)) {
		drm_clflush_sg(xe_bo_sg(bo));
		drm_info_once(&xe->drm,
			      "xe/display: CPU display flush active for sysmem scanout BOs (bo=%p size=%zu)\n",
			      bo, xe_bo_size(bo));
	}

	xe_bo_unlock(bo);
}

void intel_bo_describe(struct seq_file *m, struct drm_gem_object *obj)
{
	/* FIXME */
}
