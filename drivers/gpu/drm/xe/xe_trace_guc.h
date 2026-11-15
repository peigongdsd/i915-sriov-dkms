/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright © 2024 Intel Corporation
 */

#undef TRACE_SYSTEM
#define TRACE_SYSTEM xe

#if !defined(_XE_TRACE_GUC_H_) || defined(TRACE_HEADER_MULTI_READ)
#define _XE_TRACE_GUC_H_

#include <linux/tracepoint.h>
#include <linux/types.h>

#include "xe_device_types.h"
#include "xe_guc_exec_queue_types.h"
#include "xe_guc_engine_activity_types.h"

#define __dev_name_xe(xe)	dev_name((xe)->drm.dev)

/* These are unlocked diagnostic samples, not a coherent CT snapshot. */
TRACE_EVENT(xe_guc_ct_rx,
	TP_PROTO(struct xe_device *xe, u8 gt, const char *phase, u32 state,
		 u32 _head, u32 memory_head, u32 tail, u32 status, u32 fence,
		 int result, bool pending),
	TP_ARGS(xe, gt, phase, state, _head, memory_head, tail, status, fence, result, pending),
	TP_STRUCT__entry(
		__string(dev, __dev_name_xe(xe))
		__string(phase, phase)
		__field(u8, gt)
		__field(u32, state)
		__field(u32, head)
		__field(u32, memory_head)
		__field(u32, tail)
		__field(u32, status)
		__field(u32, fence)
		__field(int, result)
		__field(bool, pending)
	),
	TP_fast_assign(
		__assign_str(dev);
		__assign_str(phase);
		__entry->gt = gt;
		__entry->state = state;
		__entry->head = _head;
		__entry->memory_head = memory_head;
		__entry->tail = tail;
		__entry->status = status;
		__entry->fence = fence;
		__entry->result = result;
		__entry->pending = pending;
	),
	TP_printk("dev=%s gt=%u phase=%s state=%u head=%u memory_head=%u tail=%u status=%#x fence=%u result=%d pending=%u",
		  __get_str(dev), __entry->gt, __get_str(phase), __entry->state,
		  __entry->head, __entry->memory_head, __entry->tail, __entry->status,
		  __entry->fence,
		  __entry->result, __entry->pending)
);

TRACE_EVENT(xe_memirq_rx,
	TP_PROTO(struct xe_device *xe, u8 tile, const char *phase, bool irq_enabled,
		 bool enabled, bool mapped, u8 guc_source, u8 media_source,
		 u8 guc_status, u8 media_status),
	TP_ARGS(xe, tile, phase, irq_enabled, enabled, mapped, guc_source, media_source,
		guc_status, media_status),
	TP_STRUCT__entry(
		__string(dev, __dev_name_xe(xe))
		__string(phase, phase)
		__field(u8, tile)
		__field(bool, irq_enabled)
		__field(bool, enabled)
		__field(bool, mapped)
		__field(u8, guc_source)
		__field(u8, media_source)
		__field(u8, guc_status)
		__field(u8, media_status)
	),
	TP_fast_assign(
		__assign_str(dev);
		__assign_str(phase);
		__entry->tile = tile;
		__entry->irq_enabled = irq_enabled;
		__entry->enabled = enabled;
		__entry->mapped = mapped;
		__entry->guc_source = guc_source;
		__entry->media_source = media_source;
		__entry->guc_status = guc_status;
		__entry->media_status = media_status;
	),
	TP_printk("dev=%s tile=%u phase=%s irq_enabled=%u enabled=%u mapped=%u guc_source=%#x media_source=%#x guc_status=%#x media_status=%#x",
		  __get_str(dev), __entry->tile, __get_str(phase), __entry->irq_enabled,
		  __entry->enabled, __entry->mapped, __entry->guc_source,
		  __entry->media_source, __entry->guc_status, __entry->media_status)
);

TRACE_EVENT(xe_guc_relay_rx,
	TP_PROTO(struct xe_device *xe, u8 gt, const char *phase, u32 rid,
		 u32 remote, int reply, u32 len, u32 data),
	TP_ARGS(xe, gt, phase, rid, remote, reply, len, data),
	TP_STRUCT__entry(
		__string(dev, __dev_name_xe(xe))
		__string(phase, phase)
		__field(u8, gt)
		__field(u32, rid)
		__field(u32, remote)
		__field(int, reply)
		__field(u32, len)
		__field(u32, data)
	),
	TP_fast_assign(
		__assign_str(dev);
		__assign_str(phase);
		__entry->gt = gt;
		__entry->rid = rid;
		__entry->remote = remote;
		__entry->reply = reply;
		__entry->len = len;
		__entry->data = data;
	),
	TP_printk("dev=%s gt=%u phase=%s rid=%u remote=%u reply=%d len=%u data=%#x",
		  __get_str(dev), __entry->gt, __get_str(phase), __entry->rid,
		  __entry->remote, __entry->reply, __entry->len, __entry->data)
);

DECLARE_EVENT_CLASS(xe_guc_ct_flow_control,
		    TP_PROTO(struct xe_device *xe, u32 _head, u32 _tail, u32 size, u32 space, u32 len),
		    TP_ARGS(xe, _head, _tail, size, space, len),

		    TP_STRUCT__entry(
			     __string(dev, __dev_name_xe(xe))
			     __field(u32, _head)
			     __field(u32, _tail)
			     __field(u32, size)
			     __field(u32, space)
			     __field(u32, len)
			     ),

		    TP_fast_assign(
			   __assign_str(dev);
			   __entry->_head = _head;
			   __entry->_tail = _tail;
			   __entry->size = size;
			   __entry->space = space;
			   __entry->len = len;
			   ),

		    TP_printk("h2g flow control: dev=%s, head=%u, tail=%u, size=%u, space=%u, len=%u",
			      __get_str(dev), __entry->_head, __entry->_tail, __entry->size,
			      __entry->space, __entry->len)
);

DEFINE_EVENT(xe_guc_ct_flow_control, xe_guc_ct_h2g_flow_control,
	     TP_PROTO(struct xe_device *xe, u32 _head, u32 _tail, u32 size, u32 space, u32 len),
	     TP_ARGS(xe, _head, _tail, size, space, len)
);

DEFINE_EVENT_PRINT(xe_guc_ct_flow_control, xe_guc_ct_g2h_flow_control,
		   TP_PROTO(struct xe_device *xe, u32 _head, u32 _tail, u32 size, u32 space, u32 len),
		   TP_ARGS(xe, _head, _tail, size, space, len),

		   TP_printk("g2h flow control: dev=%s, head=%u, tail=%u, size=%u, space=%u, len=%u",
			     __get_str(dev), __entry->_head, __entry->_tail, __entry->size,
			     __entry->space, __entry->len)
);

DECLARE_EVENT_CLASS(xe_guc_ctb,
		    TP_PROTO(struct xe_device *xe, u8 gt_id, u32 action, u32 len, u32 _head, u32 tail),
		    TP_ARGS(xe, gt_id, action, len, _head, tail),

		    TP_STRUCT__entry(
				__string(dev, __dev_name_xe(xe))
				__field(u8, gt_id)
				__field(u32, action)
				__field(u32, len)
				__field(u32, tail)
				__field(u32, _head)
		    ),

		    TP_fast_assign(
			    __assign_str(dev);
			    __entry->gt_id = gt_id;
			    __entry->action = action;
			    __entry->len = len;
			    __entry->tail = tail;
			    __entry->_head = _head;
		    ),

		    TP_printk("H2G CTB: dev=%s, gt%d: action=0x%x, len=%d, tail=%d, head=%d\n",
			      __get_str(dev), __entry->gt_id, __entry->action, __entry->len,
			      __entry->tail, __entry->_head)
);

DEFINE_EVENT(xe_guc_ctb, xe_guc_ctb_h2g,
	     TP_PROTO(struct xe_device *xe, u8 gt_id, u32 action, u32 len, u32 _head, u32 tail),
	     TP_ARGS(xe, gt_id, action, len, _head, tail)
);

DEFINE_EVENT_PRINT(xe_guc_ctb, xe_guc_ctb_g2h,
		   TP_PROTO(struct xe_device *xe, u8 gt_id, u32 action, u32 len, u32 _head, u32 tail),
		   TP_ARGS(xe, gt_id, action, len, _head, tail),

		   TP_printk("G2H CTB: dev=%s, gt%d: action=0x%x, len=%d, tail=%d, head=%d\n",
			     __get_str(dev), __entry->gt_id, __entry->action, __entry->len,
			     __entry->tail, __entry->_head)

);

TRACE_EVENT(xe_guc_engine_activity,
	    TP_PROTO(struct xe_device *xe, struct engine_activity *ea, const char *name,
		     u16 instance),
	    TP_ARGS(xe, ea, name, instance),

	    TP_STRUCT__entry(
			__string(dev, __dev_name_xe(xe))
			__string(name, name)
			__field(u32, global_change_num)
			__field(u32, guc_tsc_frequency_hz)
			__field(u32, lag_latency_usec)
			__field(u16, instance)
			__field(u16, change_num)
			__field(u16, quanta_ratio)
			__field(u32, last_update_tick)
			__field(u64, active_ticks)
			__field(u64, active)
			__field(u64, total)
			__field(u64, quanta)
			__field(u64, last_cpu_ts)
	    ),

	    TP_fast_assign(
			__assign_str(dev);
			__assign_str(name);
			__entry->global_change_num = ea->metadata.global_change_num;
			__entry->guc_tsc_frequency_hz = ea->metadata.guc_tsc_frequency_hz;
			__entry->lag_latency_usec = ea->metadata.lag_latency_usec;
			__entry->instance = instance;
			__entry->change_num = ea->activity.change_num;
			__entry->quanta_ratio = ea->activity.quanta_ratio;
			__entry->last_update_tick = ea->activity.last_update_tick;
			__entry->active_ticks = ea->activity.active_ticks;
			__entry->active = ea->active;
			__entry->total = ea->total;
			__entry->quanta = ea->quanta;
			__entry->last_cpu_ts = ea->last_cpu_ts;
	    ),

	    TP_printk("dev=%s engine %s:%d Active=%llu, quanta=%llu, last_cpu_ts=%llu\n"
		      "Activity metadata: global_change_num=%u, guc_tsc_frequency_hz=%u lag_latency_usec=%u\n"
		      "Activity data: change_num=%u, quanta_ratio=0x%x, last_update_tick=%u, active_ticks=%llu\n",
		      __get_str(dev), __get_str(name), __entry->instance,
		      (__entry->active +  __entry->total), __entry->quanta, __entry->last_cpu_ts,
		      __entry->global_change_num, __entry->guc_tsc_frequency_hz,
		      __entry->lag_latency_usec, __entry->change_num, __entry->quanta_ratio,
		      __entry->last_update_tick, __entry->active_ticks)
);
#endif

/* This part must be outside protection */
#undef TRACE_INCLUDE_PATH
#undef TRACE_INCLUDE_FILE
#define TRACE_INCLUDE_PATH MODULE_ABS_PATH(drivers/gpu/drm/xe)
#define TRACE_INCLUDE_FILE xe_trace_guc
#include <trace/define_trace.h>
