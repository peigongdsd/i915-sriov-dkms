#include_next <drm/display/drm_dp.h>
#ifndef __BACKPORT_DRM_DP_H__
#define __BACKPORT_DRM_DP_H__


#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 19, 0)
# define DP_DSC_THROUGHPUT_MODE_0_DELTA_SHIFT 3 /* DP 2.1a, in units of 2 MPixels/sec */
# define DP_DSC_THROUGHPUT_MODE_0_DELTA_MASK  (0x1f << DP_DSC_THROUGHPUT_MODE_0_DELTA_SHIFT)

#define DP_DSC_BRANCH_CAP_SIZE 3
#endif

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0)
# define DP_PANEL_REPLAY_FULL_LINE_GRANULARITY		0xffff
#endif
#endif /* __BACKPORT_DRM_DP_H__ */
