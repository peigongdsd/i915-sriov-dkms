# ADL-P host DMA fault near Looking Glass import

**Later capture update:** the replacement archives and second VM attempt are analyzed in [the current capture note](adlp-reuploaded-capture-analysis.md). All have CCS enabled; the second attempt faults before any new KVMFR export. The user confirms unchanged settings and persistent Code 43. A separate [ADL-P render-context experiment](adlp-indirect-offset-experiment.md) is now built for testing. The source distinctions below remain evidence, not established causes.

Bounded source review, 2026-10-02. MTL work remains paused. No module was built, loaded, unloaded or patched; no VM or configuration was changed.

## Assessment

The supplied log makes the **Linux host Looking Glass / dma-buf import path a priority discriminator**, but does not establish kvmfr as the cause. The first IOMMU fault names PF `0000:00:02.0`, immediately followed by a host Xe render-engine CAT error and later host GT resets. Treating this excerpt as proof of an independent Windows-driver startup rejection is premature. Conversely, the excerpt does not identify the first faulting buffer or its owning process, so the first queue must not be labelled Looking Glass solely from timing.

The first test should be a fresh run **without the Looking Glass client**, observing the guest through an independent path. For a stronger Looking Glass-free control, also stop guest Looking Glass capture. If that run succeeds, repeat with the same shared-memory setup and the supported B7 client option:

```sh
looking-glass-client app:allowDMA=no
```

Preserve any other existing client arguments. This disables the client's direct dma-buf import while retaining `/dev/kvmfr0` shared memory and normal host GPU rendering. It does **not** disable guest capture, all GPU DMA, or the kvmfr module itself. Thus it is more specific than removing the entire shared-memory device from the VM. The [official B7 option documentation](https://looking-glass.io/docs/B7/usage/#all-command-line-options) and pinned source both support the option. Current development master uses `lgmp:allowDMA` as its canonical spelling but retains `app:allowDMA` as a compatibility alias.

## What the supplied log proves

Input: the supplied `pasted-text.txt`, SHA-256 `12d4699b3e4f63e22377514554835e123a3ef00c4bda95e508e42a720d425e8b`. Source pins and exported source copies are in `evidence/adlp-kvmfr/`.

| Timestamp | Observation |
|---|---|
| 7.518967 | kvmfr creates one static device. |
| 377.515628 and later | `/dev/kvmfr0` is mapped with size 134217728 bytes. |
| 388.713315 | kvmfr exports size 16384000, offset 5701632. |
| 388.725941 | DMAR fault handler runs, 12.626 ms after the export log. |
| 388.725948 | DMA Write, NO_PASID, requester PF `00:02.0`, address `0x78226a000`, reason `0x07`: next page-table pointer invalid. |
| 388.725990 | Xe render-engine CAT error, GuC queue ID 65. |
| 389.758529–389.788235 | Engine-reset recovery escalates to a host GT reset. |
| 394.887497 | A later timeout identifies `looking-glass-c` PID 6948, GuC queue 49. |

The first DMAR error line is 12.633 ms after export; the often quoted 12.626 ms is to entry into the fault handler. The later named queue 49 is not the initial queue 65. Subsequent faults name other addresses and queues, amid repeated resets.

The exported range is page aligned and lies inside the logged 128 MiB shared-memory mapping. `5701632` is a **shared-memory offset**, not a DMA address; it cannot be directly compared with `0x78226a000`. The log contains no table associating that IOVA with a particular imported buffer. A DMA **write** fault also does not prove the faulting operation was a read of the captured frame: rendering destinations, page-table operations and other host allocations must remain in scope.

## Source provenance and the likely Nix package

The log's system path identifies nixpkgs abbreviation `f0f0d1a`. Its [kvmfr derivation](https://github.com/NixOS/nixpkgs/blob/f0f0d1a/pkgs/os-specific/linux/kvmfr/default.nix) uses `looking-glass-client.version` and `.src`, builds the `module` directory against the selected kernel, and adds no source patch list of its own. The [client package at that revision](https://github.com/NixOS/nixpkgs/blob/f0f0d1a/pkgs/by-name/lo/looking-glass-client/package.nix) selects **B7**. Therefore an unoverridden `config.boot.kernelPackages.kvmfr` from that package set is B7 source built for the chosen kernel. Linux version 7.2.8 alone does not establish its source revision; overlays and explicit package overrides remain possible.

Official Looking Glass source was downloaded read-only for inspection:

- B7 tag resolves to `27fe47cbe2a3a8da986d310ab866f0b646ed68f5`.
- Development master observed as `236efcb155f952f5d7d9fcd5891a3060ad254e68`.
- Xe mapping comparison uses the existing pinned Linux source `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`. This is a source comparison baseline, not proof of the exact loaded Xe image on the user's host.

## Exporter mapping and lifetime

In [B7 `module/kvmfr.c`](https://github.com/gnif/LookingGlass/blob/27fe47cbe2a3a8da986d310ab866f0b646ed68f5/module/kvmfr.c), the static device uses `vmalloc_user()` (`:502` onward). A buffer export validates alignment and bounds, obtains the corresponding pages with `vmalloc_to_page()`, and exports a dma-buf (`:188` onward). The logged creation message occurs after `dma_buf_export()` but before returning the dma-buf FD. It is **not a log of successful GPU attachment, IOMMU mapping, or submission**.

`map_kvmfrbuf()` (`:106`) creates a fresh scatter-gather table from those pages and calls:

```c
dma_map_sg(at->dev, sg->sgl, sg->nents, direction)
```

The device is the **importing attachment's device**. With Xe importing, mappings are therefore requested for Xe's device, not the kvmfr class device. The callback returns mapped DMA addresses via the normal API; the inspected code does not simply supply unmapped physical page addresses to Xe. `unmap_kvmfrbuf()` uses the same device/direction, unmaps the list, and frees that table. `release_kvmfrbuf()` frees the export's page-pointer array and metadata; it does not free the static backing storage for each exported frame.

B7's client caches dma-buf FDs per frame buffer and invokes `ivshmemGetDMABuf()` when one is needed (`client/src/main.c:783`). Its `useDMA` flag is the conjunction of `app:allowDMA` and shared-memory DMA capability (`:1337`). With DMA disabled, the renderer receives FD `-1` instead (`:796`). The ioctl wrapper rounds buffer size to page size; the export validates the supplied range again. These are source-level ownership observations, not runtime proof that no reset/import race occurred.

### Scatter-list count discrepancy: real audit finding, unproven explanation

Both B7 and the inspected current master treat `dma_map_sg()`'s return only as success/failure. They do not replace `sg_table.nents` with the returned **mapped** segment count. Linux's [DMA API contract](https://docs.kernel.org/core-api/dma-api.html) permits mapping to merge entries: consumers should use the returned count, while unmapping requires the original input count. Thus an exporter should preserve original versus mapped counts explicitly, normally through the sg-table API or equivalent bookkeeping.

Here `sg->nents` remains the original count, so using it as the unmap argument is **not itself the common wrong-count unmap bug**. The questionable part is returning a table whose `nents` may not describe the mapped segment count. Changing only the map-side field and leaving unmap unchanged would introduce a separate mistake.

Crucially, the inspected Xe PTE paths do not use that field as their loop bound. `xe_pt.c:875` and `xe_ggtt.c:702` call `xe_res_first_sg()`, whose cursor walks mapped addresses and lengths via `sg_dma_len()`/`sg_next()` until the requested byte range is covered (`xe_res_cursor.h:159`, `:214`, `:335`). A smaller mapped count therefore does not, by itself, demonstrate an invalid Xe PTE in this path. No runtime merged counts, map/unmap trace, buffer IOVA list or failing PTE were supplied. Record this as a compatibility/audit concern, **not a proven fix for Code 43 or the DMAR fault**.

## Xe import behavior and limits

[Current inspected Xe `xe_bo.c`](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_bo.c#L740) calls `dma_buf_map_attachment(attach, DMA_BIDIRECTIONAL)` and uses the returned mapped SG table. Its comment describes deferred unmapping until a subsequent remap or destruction after idling, relying on reservation-object synchronization (`:737` onward). This requires lifecycle evidence to diagnose; the export log alone cannot show premature unmapping.

A recent upstream import-lifetime fix, [62775525a27c](https://gitlab.freedesktop.org/drm/xe/kernel/-/commit/62775525a27c3b0d56382e08ba81ee2d322058b6), keeps a dma-buf reference across imported-BO creation failure and deferred destruction. Its documented trigger involves failed attach/BO initialization and a reservation-object use-after-free. It is already an ancestor of the inspected `ce1e` baseline. Neither that trigger nor its characteristic CPU fault is established by the supplied log; do not prescribe it as an absent fix solely because it mentions dma-buf.

## Known-report search and next evidence

A bounded search of official Looking Glass GitHub issues for `DMAR` and `dma_map_sg` returned no matches; a combined IOMMU/Xe-driver/page-table search returned four unrelated older reports. The saved query results are in `evidence/adlp-kvmfr/`. This is not evidence that the problem is unknown everywhere. No verified primary report matching this exact Xe + static-kvmfr + PF DMA-write sequence was established in this review.

Record the outcome of the no-client control first, then `app:allowDMA=no`, using fresh runs so prior host-reset damage does not confound the comparison. Compare **the first** DMAR/CAT error and Windows device status, not only later queue timeouts. If DMA-off isolates the failure, the next useful trace is the attachment device, original/mapped segment counts, mapped IOVA ranges, map/unmap timestamps, and first queue ownership. A valid Xe device coredump captured at the first failure could identify the failing VM/BO/PTE. Without those observations, neither Windows-driver changes nor a scatter-count patch has a demonstrated causal target.
