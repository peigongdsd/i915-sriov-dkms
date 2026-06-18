#include_next <linux/gfp.h>

#ifndef __BACKPORT_LINUX_GFP_H__
#define __BACKPORT_LINUX_GFP_H__

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0)
/* Helper macro to avoid gfp flags if they are the default one */
#define __default_gfp(a,...) a
#define default_gfp(...) __default_gfp(__VA_ARGS__ __VA_OPT__(,) GFP_KERNEL)
#endif

#endif
