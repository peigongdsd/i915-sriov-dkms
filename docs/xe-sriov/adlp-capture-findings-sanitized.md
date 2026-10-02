# ADL-P Xe SR-IOV: findings from three host captures

All three snapshots have Xe's experimental CCS option enabled, including the snapshot originally labelled “before CCS.” They do not constitute a CCS-off/CCS-on comparison. They show one VF provisioned throughout, a stable PF runtime-register map, and identical decoded default-context templates.

## The failures belong to host PF execution

The VF's actual GuC context allocation is **32767–65534**. Reported CAT contexts **65, 12, 14 and 44** are outside that allocation. The IOMMU reports DMA writes from the **PF PCI function**, and Xe prints the detailed CAT message only after finding the corresponding queue in its own submission table. These facts establish involvement of host PF execution, while leaving the initiating cause open. [Xe queue lookup and CAT handler](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/drivers/gpu/drm/xe/xe_guc_submit.c#L3001)

The first recorded PF DMA fault occurs approximately 13 ms after a Looking Glass shared-buffer export. That is a useful lead, but the complete chronology weakens a simple exporter-only explanation:

- In the second VM run, the first new PF DMA fault occurs at uptime **717.790880 s**; the first new shared-buffer export appears later, at **738.386900 s**.
- At **735.116206 s**, a CAT event for queue14 is followed approximately 106 microseconds later by a queue14 timeout attributed to host **systemd-logind**.
- This second run occurs in the **same boot after earlier PF faults and GT resets**. It neither proves a fresh export caused the new failure nor excludes residual damage from the first run.

The available coredump describes a later Looking Glass queue49 timeout after a GT reset. It does not capture the first CAT event on queue65. A process observed on a later queue cannot automatically be assigned to the first fault, particularly across resets and queue-ID reuse.

The fault addresses fit below the platform's 39-bit host-address limit. The separately configured 47-bit GPU virtual-address limit is a different address space; this evidence does not demonstrate an address-width overflow. “Next page table ptr is invalid” is the **IOMMU** fault reason, not direct proof of a malformed GPU GGTT or per-process page-table entry.

## Provisioning is stable; a raw allocator offset is not a mismatch

The VF consistently has **2 GiB of GGTT**, **32768 context IDs**, and **128 doorbells**. The apparent 2 MiB difference between its provisioned GGTT address and the generic allocator dump is explained by Xe's WOPCM/start bias: the allocator prints relative offsets, while the provisioned address includes that bias. These values agree. The allocation dump does not expose live PTE ownership bits. [Xe address conversion](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/drivers/gpu/drm/xe/xe_ggtt.c#L1147)

Source comparison finds no ADL-P VF-ID bit-encoding discrepancy for VFs1–7: i915 and Xe produce the same ownership value for those IDs. Both assign ownership and invalidate before sending the region configuration to GuC. Actual hardware PTE state at the first fault remains unobserved.

## Post-reset service state does not prove a handshake failure

All snapshots advertise PF service ABI **1.0**, matching the inspected i915 implementation. The later snapshots contain no negotiated VF version, but each follows a VF shutdown/reset that clears that state. Their empty adverse-event counters are also cleared by FLR and cover selected GuC threshold events, not every IOMMU or engine error. These snapshots cannot establish whether startup handshaking succeeded, failed, or was omitted. [Version reset and reporting](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/drivers/gpu/drm/xe/xe_sriov_pf_service.c#L165), [counter reset](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/drivers/gpu/drm/xe/xe_gt_sriov_pf_monitor.c#L16)

Decoded the retained command-transport buffers from all three live snapshots and both available coredump copies. Descriptor values validate the decoding. No complete valid relay handshake/runtime packet remains in those buffers. Unrelated payload words resembling relay action numbers were excluded by checking their surrounding message headers. Ring overwrite and resets make this a **failure to recover earlier traffic**, not evidence that the guest never sent it.

The running Xe map indeed lacks the two clock-register entries exported by the compared i915 implementation. Windows code contains readers of those registers, but its actual ADL-P VF callback path and a connection to Code43 remain unproved. The new PF DMA faults deserve priority over a speculative service-map patch.

The decoded default RCS, CCS, BCS, VCS and VECS templates remain identical across snapshots. These are cached templates that omit the hardware status page, not the failing live context or every GPU-visible ADS copy. Their stability cannot exclude transient context-state or mapping corruption.

## Next discriminating capture

Use a **fresh host boot** and the unchanged guest, starting with the host Looking Glass client stopped. Observe Windows device status independently and preserve the **first** PF DMA/CAT failure, if any. This separates a host rendering/import path without presuming it is the cause. If required, compare Looking Glass with DMA import disabled as a separate step.

The useful code-level evidence is the first failed PF queue, its VM and GPU PTEs, and the corresponding current DMA mappings and attachment lifetimes. If service sequencing remains suspect, collect handshake/runtime requests before the shutdown FLR; later debugfs state cannot reconstruct that exchange. No complete i915-service migration or additional ADL-P relay protocol is justified by these captures.
