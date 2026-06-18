#include_next <drm/ttm/ttm_bo.h>

#ifndef __BACKPORT_DRM_TTM_BO_H__
#define __BACKPORT_DRM_TTM_BO_H__


#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 18, 0)
#define ttm_bo_setup_export LINUX_BACKPORT(ttm_bo_setup_export)
int ttm_bo_setup_export(struct ttm_buffer_object *bo,
			struct ttm_operation_ctx *ctx);
#endif

#endif
