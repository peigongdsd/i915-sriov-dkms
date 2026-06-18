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

#include <drm/display/drm_dp_helper.h>

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0)

/**
 * drm_dp_dsc_slice_count_to_mask() - Convert a slice count to a slice count mask
 * @slice_count: slice count


 *
 * Convert @slice_count to a slice count mask.
 *
 * Returns the slice count mask.
 */
u32 drm_dp_dsc_slice_count_to_mask(int slice_count)
{
	return BIT(slice_count - 1);
}
EXPORT_SYMBOL(drm_dp_dsc_slice_count_to_mask);

/**
 * drm_dp_dsc_sink_slice_count_mask() - Get the mask of valid DSC sink slice counts
 * @dsc_dpcd: the sink's DSC DPCD capabilities
 * @is_edp: %true for an eDP sink
 *
 * Get the mask of supported slice counts from the sink's DSC DPCD register.
 *
 * Returns:
 * Mask of slice counts supported by the DSC sink:
 * - > 0: bit#0,1,3,5..,23 set if the sink supports 1,2,4,6..,24 slices
 * - 0:   if the sink doesn't support any slices
 */
u32 drm_dp_dsc_sink_slice_count_mask(const u8 dsc_dpcd[DP_DSC_RECEIVER_CAP_SIZE],
				     bool is_edp)
{
	u8 slice_cap1 = dsc_dpcd[DP_DSC_SLICE_CAP_1 - DP_DSC_SUPPORT];
	u32 mask = 0;

	if (!is_edp) {
		/* For DP, use values from DSC_SLICE_CAP_1 and DSC_SLICE_CAP2 */
		u8 slice_cap2 = dsc_dpcd[DP_DSC_SLICE_CAP_2 - DP_DSC_SUPPORT];

		if (slice_cap2 & DP_DSC_24_PER_DP_DSC_SINK)
			mask |= drm_dp_dsc_slice_count_to_mask(24);
		if (slice_cap2 & DP_DSC_20_PER_DP_DSC_SINK)
			mask |= drm_dp_dsc_slice_count_to_mask(20);
		if (slice_cap2 & DP_DSC_16_PER_DP_DSC_SINK)
			mask |= drm_dp_dsc_slice_count_to_mask(16);
	}

	/* DP, eDP v1.5+ */
	if (slice_cap1 & DP_DSC_12_PER_DP_DSC_SINK)
		mask |= drm_dp_dsc_slice_count_to_mask(12);
	if (slice_cap1 & DP_DSC_10_PER_DP_DSC_SINK)
		mask |= drm_dp_dsc_slice_count_to_mask(10);
	if (slice_cap1 & DP_DSC_8_PER_DP_DSC_SINK)
		mask |= drm_dp_dsc_slice_count_to_mask(8);
	if (slice_cap1 & DP_DSC_6_PER_DP_DSC_SINK)
		mask |= drm_dp_dsc_slice_count_to_mask(6);
	/* DP, eDP v1.4+ */
	if (slice_cap1 & DP_DSC_4_PER_DP_DSC_SINK)
		mask |= drm_dp_dsc_slice_count_to_mask(4);
	if (slice_cap1 & DP_DSC_2_PER_DP_DSC_SINK)
		mask |= drm_dp_dsc_slice_count_to_mask(2);
	if (slice_cap1 & DP_DSC_1_PER_DP_DSC_SINK)
		mask |= drm_dp_dsc_slice_count_to_mask(1);

	return mask;
}
EXPORT_SYMBOL(drm_dp_dsc_sink_slice_count_mask);
#endif
