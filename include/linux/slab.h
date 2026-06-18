#include_next <linux/slab.h>

#ifndef __BACKPORT_LINUX_SLAB_H__
#define __BACKPORT_LINUX_SLAB_H__

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0)
/**
 * __alloc_objs - Allocate objects of a given type using
 * @KMALLOC: which size-based kmalloc wrapper to allocate with.
 * @GFP: GFP flags for the allocation.
 * @TYPE: type to allocate space for.
 * @COUNT: how many @TYPE objects to allocate.
 *
 * Returns: Newly allocated pointer to (first) @TYPE of @COUNT-many
 * allocated @TYPE objects, or NULL on failure.
 */
#define __alloc_objs(KMALLOC, GFP, TYPE, COUNT)				\
({									\
	const size_t __obj_size = size_mul(sizeof(TYPE), COUNT);	\
	(TYPE *)KMALLOC(__obj_size, GFP);				\
})

/**
 * __alloc_flex - Allocate an object that has a trailing flexible array
 * @KMALLOC: kmalloc wrapper function to use for allocation.
 * @GFP: GFP flags for the allocation.
 * @TYPE: type of structure to allocate space for.
 * @FAM: The name of the flexible array member of @TYPE structure.
 * @COUNT: how many @FAM elements to allocate space for.
 *
 * Returns: Newly allocated pointer to @TYPE with @COUNT-many trailing
 * @FAM elements, or NULL on failure or if @COUNT cannot be represented
 * by the member of @TYPE that counts the @FAM elements (annotated via
 * __counted_by()).
 */
#define __alloc_flex(KMALLOC, GFP, TYPE, FAM, COUNT)			\
({									\
	const size_t __count = (COUNT);					\
	const size_t __obj_size = struct_size_t(TYPE, FAM, __count);	\
	TYPE *__obj_ptr;						\
	if (WARN_ON_ONCE(overflows_flex_counter_type(TYPE, FAM,	__count))) \
		__obj_ptr = NULL;					\
	else								\
		__obj_ptr = KMALLOC(__obj_size, GFP);			\
	if (__obj_ptr)							\
		__set_flex_counter(__obj_ptr->FAM, __count);		\
	__obj_ptr;							\
})

/**
 * kmalloc_obj - Allocate a single instance of the given type
 * @VAR_OR_TYPE: Variable or type to allocate.
 * @GFP: GFP flags for the allocation.
 *
 * Returns: newly allocated pointer to a @VAR_OR_TYPE on success, or NULL
 * on failure.
 */
#define kmalloc_obj(VAR_OR_TYPE, ...) \
	__alloc_objs(kmalloc, default_gfp(__VA_ARGS__), typeof(VAR_OR_TYPE), 1)

/**
 * kmalloc_objs - Allocate an array of the given type
 * @VAR_OR_TYPE: Variable or type to allocate an array of.
 * @COUNT: How many elements in the array.
 * @GFP: GFP flags for the allocation.
 *
 * Returns: newly allocated pointer to array of @VAR_OR_TYPE on success,
 * or NULL on failure.
 */
#define kmalloc_objs(VAR_OR_TYPE, COUNT, ...) \
	__alloc_objs(kmalloc, default_gfp(__VA_ARGS__), typeof(VAR_OR_TYPE), COUNT)

/**
 * kmalloc_flex - Allocate a single instance of the given flexible structure
 * @VAR_OR_TYPE: Variable or type to allocate (with its flex array).
 * @FAM: The name of the flexible array member of the structure.
 * @COUNT: How many flexible array member elements are desired.
 * @GFP: GFP flags for the allocation.
 *
 * Returns: newly allocated pointer to @VAR_OR_TYPE on success, NULL on
 * failure. If @FAM has been annotated with __counted_by(), the allocation
 * will immediately fail if @COUNT is larger than what the type of the
 * struct's counter variable can represent.
 */
#define kmalloc_flex(VAR_OR_TYPE, FAM, COUNT, ...) \
	__alloc_flex(kmalloc, default_gfp(__VA_ARGS__), typeof(VAR_OR_TYPE), FAM, COUNT)

/* All kzalloc aliases for kmalloc_(obj|objs|flex). */
#define kzalloc_obj(P, ...) \
	__alloc_objs(kzalloc, default_gfp(__VA_ARGS__), typeof(P), 1)
#define kzalloc_objs(P, COUNT, ...) \
	__alloc_objs(kzalloc, default_gfp(__VA_ARGS__), typeof(P), COUNT)
#define kzalloc_flex(P, FAM, COUNT, ...)		\
	__alloc_flex(kzalloc, default_gfp(__VA_ARGS__), typeof(P), FAM, COUNT)

/* All kvmalloc aliases for kmalloc_(obj|objs|flex). */
#define kvmalloc_obj(P, ...) \
	__alloc_objs(kvmalloc, default_gfp(__VA_ARGS__), typeof(P), 1)
#define kvmalloc_objs(P, COUNT, ...) \
	__alloc_objs(kvmalloc, default_gfp(__VA_ARGS__), typeof(P), COUNT)
#define kvmalloc_flex(P, FAM, COUNT, ...) \
	__alloc_flex(kvmalloc, default_gfp(__VA_ARGS__), typeof(P), FAM, COUNT)

/* All kvzalloc aliases for kmalloc_(obj|objs|flex). */
#define kvzalloc_obj(P, ...) \
	__alloc_objs(kvzalloc, default_gfp(__VA_ARGS__), typeof(P), 1)
#define kvzalloc_objs(P, COUNT, ...) \
	__alloc_objs(kvzalloc, default_gfp(__VA_ARGS__), typeof(P), COUNT)
#define kvzalloc_flex(P, FAM, COUNT, ...) \
	__alloc_flex(kvzalloc, default_gfp(__VA_ARGS__), typeof(P), FAM, COUNT)
#endif

#endif
