#include_next <linux/overflow.h>

#ifndef __BACKPORT_LINUX_OVERFLOW_H__
#define __BACKPORT_LINUX_OVERFLOW_H__

#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 18, 0)
/**
 * range_overflows() - Check if a range is out of bounds
 * @start: Start of the range.
 * @size:  Size of the range.
 * @max:   Exclusive upper boundary.
 *
 * A strict check to determine if the range [@start, @start + @size) is
 * invalid with respect to the allowable range [0, @max). Any range
 * starting at or beyond @max is considered an overflow, even if @size is 0.
 *
 * Returns: true if the range is out of bounds.
 */
#define range_overflows(start, size, max) ({ \
	typeof(start) start__ = (start); \
	typeof(size) size__ = (size); \
	typeof(max) max__ = (max); \
	(void)(&start__ == &size__); \
	(void)(&start__ == &max__); \
	start__ >= max__ || size__ > max__ - start__; \
})

/**
 * range_overflows_t() - Check if a range is out of bounds
 * @type:  Data type to use.
 * @start: Start of the range.
 * @size:  Size of the range.
 * @max:   Exclusive upper boundary.
 *
 * Same as range_overflows() but forcing the parameters to @type.
 *
 * Returns: true if the range is out of bounds.
 */
#define range_overflows_t(type, start, size, max) \
	range_overflows((type)(start), (type)(size), (type)(max))

/**
 * range_end_overflows() - Check if a range's endpoint is out of bounds
 * @start: Start of the range.
 * @size:  Size of the range.
 * @max:   Exclusive upper boundary.
 *
 * Checks only if the endpoint of a range (@start + @size) exceeds @max.
 * Unlike range_overflows(), a zero-sized range at the boundary (@start == @max)
 * is not considered an overflow. Useful for iterator-style checks.
 *
 * Returns: true if the endpoint exceeds the boundary.
 */
#define range_end_overflows(start, size, max) ({ \
	typeof(start) start__ = (start); \
	typeof(size) size__ = (size); \
	typeof(max) max__ = (max); \
	(void)(&start__ == &size__); \
	(void)(&start__ == &max__); \
	start__ > max__ || size__ > max__ - start__; \
})

/**
 * range_end_overflows_t() - Check if a range's endpoint is out of bounds
 * @type:  Data type to use.
 * @start: Start of the range.
 * @size:  Size of the range.
 * @max:   Exclusive upper boundary.
 *
 * Same as range_end_overflows() but forcing the parameters to @type.
 *
 * Returns: true if the endpoint exceeds the boundary.
 */
#define range_end_overflows_t(type, start, size, max) \
	range_end_overflows((type)(start), (type)(size), (type)(max))
#endif

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0)
/**
 * typeof_flex_counter() - Return the type of the counter variable of a given
 *                         flexible array member annotated by __counted_by().
 * @FAM: Instance of flexible array member within a given struct.
 *
 * Returns: "size_t" if no annotation exists.
 */
#define typeof_flex_counter(FAM)				\
	typeof(_Generic(__flex_counter(FAM),			\
			void *: (size_t)0,			\
			default: *__flex_counter(FAM)))

/**
 * overflows_flex_counter_type() - Check if the counter associated with the
 *				   given flexible array member can represent
 *				   a value.
 * @TYPE: Type of the struct that contains the @FAM.
 * @FAM: Member name of the FAM within @TYPE.
 * @COUNT: Value to check against the __counted_by annotated @FAM's counter.
 *
 * Returns: true if @COUNT can be represented in the @FAM's counter. When
 * @FAM is not annotated with __counted_by(), always returns true.
 */
#define overflows_flex_counter_type(TYPE, FAM, COUNT)		\
	(overflows_type(COUNT, typeof_flex_counter(((TYPE *)NULL)->FAM)))

/**
 * __set_flex_counter() - Set the counter associated with the given flexible
 *                        array member that has been annoated by __counted_by().
 * @FAM: Instance of flexible array member within a given struct.
 * @COUNT: Value to store to the __counted_by annotated @FAM_PTR's counter.
 *
 * This is a no-op if no annotation exists. Count needs to be checked with
 * overflows_flex_counter_type() before using this function.
 */
#define __set_flex_counter(FAM, COUNT)				\
({								\
	*_Generic(__flex_counter(FAM),				\
		  void *:  &(size_t){ 0 },			\
		  default: __flex_counter(FAM)) = (COUNT);	\
})
#endif

#endif
