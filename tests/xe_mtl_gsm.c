/* SPDX-License-Identifier: MIT */
/* Exercise the actual PF GSM admission block with captured MMIO and mapping. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
typedef uint64_t phys_addr_t;
struct xe_tile { int id; };
struct xe_device {
	struct { int platform; } info;
	struct { void *dev; } drm;
	unsigned int graphics, media;
	bool pf;
	struct xe_tile root;
};
struct xe_ggtt { struct xe_tile *tile; void *gsm; };
#define XE_METEORLAKE 1
#define IS_SRIOV_PF(xe) ((xe)->pf)
#define GRAPHICS_VERx100(xe) ((xe)->graphics)
#define MEDIA_VERx100(xe) ((xe)->media)
#define xe_device_get_root_tile(xe) (&(xe)->root)
#define xe_root_tile_mmio(xe) (xe)
/* Register tokens are only used to verify which mocked access is issued. */
#define MTL_PCODE_STOLEN_ACCESS 0x138914
#define STOLEN_ACCESS_ALLOWED 1
#define GSMBASE 0x108100
#define BDSM_MASK (~((1ULL << 20) - 1))
static unsigned int permission_reads, base_reads, mappings;
static u32 permission_value;
static phys_addr_t base_value;
static bool map_fails;
static char error[256], mapped;
#define xe_tile_err(tile, ...) ((void)(tile), snprintf(error, sizeof(error), __VA_ARGS__))

static u32 xe_mmio_read32(struct xe_device *xe, unsigned int reg)
{
	(void)xe;
	assert(reg == MTL_PCODE_STOLEN_ACCESS);
	permission_reads++;
	return permission_value;
}

static phys_addr_t xe_mmio_read64_2x32(struct xe_device *xe, unsigned int reg)
{
	(void)xe;
	assert(reg == GSMBASE);
	base_reads++;
	return base_value;
}

static void *devm_ioremap(void *dev, phys_addr_t base, unsigned int size)
{
	(void)dev;
	assert(base == (base_value & BDSM_MASK) && size == 8 * 1024 * 1024);
	mappings++;
	return map_fails ? NULL : &mapped;
}

static int admit(struct xe_device *xe, struct xe_ggtt *ggtt)
{
	unsigned int gsm_size = 8 * 1024 * 1024;

#include "actual-functions.inc"
	return 0;
}

static void check(unsigned int graphics, unsigned int media, bool root,
		  u32 permission, phys_addr_t base, bool fail_map, int expected,
		  unsigned int reads, unsigned int bases, unsigned int maps,
		  const char *diagnostic)
{
	struct xe_device xe = {
		.info.platform = XE_METEORLAKE, .pf = true,
		.graphics = graphics, .media = media,
	};
	struct xe_tile other = { 0 };
	struct xe_ggtt ggtt = { .tile = root ? &xe.root : &other };

	permission_reads = base_reads = mappings = 0;
	permission_value = permission;
	base_value = base;
	map_fails = fail_map;
	error[0] = '\0';
	assert(admit(&xe, &ggtt) == expected);
	assert(permission_reads == reads && base_reads == bases && mappings == maps);
	if (!expected)
		assert(ggtt.gsm == &mapped);
	if (diagnostic)
		assert(strstr(error, diagnostic));
}

int main(void)
{
	for (unsigned int gfx = 1270; gfx <= 1271; gfx++) {
		check(gfx, 1300, true, 1, 0x100000, false, 0, 1, 1, 1, NULL);
		check(gfx, 1300, true, 0, 0x100000, false, -EOPNOTSUPP,
		      1, 0, 0, "not permitted by firmware");
	}
	check(1274, 1300, true, 1, 0x100000, false, -EOPNOTSUPP,
	      0, 0, 0, "graphics IP 1274, media IP 1300");
	check(1271, 1301, true, 1, 0x100000, false, -EOPNOTSUPP,
	      0, 0, 0, "graphics IP 1271, media IP 1301");
	check(1271, 1300, false, 1, 0x100000, false, -EOPNOTSUPP,
	      0, 0, 0, "root tile");
	check(1271, 1300, true, 2, 0x100000, false, -EOPNOTSUPP,
	      1, 0, 0, "permission 0x2");
	check(1271, 1300, true, 1, 0, false, -ENODEV, 1, 1, 0, NULL);
	check(1271, 1300, true, 1, 0x100000, true, -ENOMEM, 1, 1, 1, NULL);
	puts("MTL GSM IP admission, permission and mapping tests passed");
	return 0;
}
