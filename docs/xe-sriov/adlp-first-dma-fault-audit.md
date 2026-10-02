# ADL-P: first PF DMA fault after enabling CCS

**Later capture update:** the replacement archives and second VM attempt are analyzed in [the current capture note](adlp-reuploaded-capture-analysis.md). All have CCS enabled; the second attempt faults before any new KVMFR export. The user confirms unchanged settings and persistent Code 43. A separate [ADL-P render-context experiment](adlp-indirect-offset-experiment.md) is now built for testing. The source distinctions below remain evidence, not established causes.

Inspected 2026-10-02 from the user-supplied full host log (SHA-256 `12d4699b3e4f63e22377514554835e123a3ef00c4bda95e508e42a720d425e8b`). Driver-source comparison is pinned to `strongtz/i915-sriov-dkms` `f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88`; upstream DMAR logging was checked at Linux `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`. No code or configuration changes.

## The first recorded failure is host PF DMA translation

CCS and the 47-bit GPU-VA restriction are explicitly enabled in this log. VF1 is provisioned with 2 GiB GGTT and 32768 context IDs, then passed through as `00:02.1`. At 379.686927 seconds VFIO resets that VF and the PF reports its FLR.

The useful event ordering is:

| Time, seconds | Event |
|---:|---|
| 388.713315 | `kvmfr_dmabuf_create`, size 16,384,000, offset 5,701,632 |
| 388.725948 | DMAR **DMA Write NO_PASID**, requester **00:02.0**, address **0x78226a000**, reason 0x07, next page-table pointer invalid |
| 388.725990 | Xe PF render engine CAT error, GuC context ID **65** |
| 389.758524 | Engine reset request fails; GT reset follows |
| 394.857801 | Host `looking-glass-c` queue 49 times out; coredump created |
| 394.887485 | Host `systemd-logind` queue 21 times out |
| 397.889554 | Another PF DMA-write fault, address 0x332792000; CAT context ID 12 |
| 408.507338 | Another PF DMA-write fault, address 0x4b0316000; CAT context ID 12 |

The first DMA-buffer creation precedes the first DMAR fault by 12.633 ms. This is a useful correlation, not proof the exported buffer contains the faulting address. The first CAT queue is **65**, so the later Looking Glass timeout on queue **49** cannot be substituted as an identification of that original queue's process. IDs can also change across resets.

DMAR's wording refers to the **IOMMU translation tables** for the request, not directly to a malformed Intel GPU GGTT/PPGTT entry. The kernel prints the requester from the hardware source ID (`drivers/iommu/intel/dmar.c:1983`). It says PF `00:02.0`, not VF `00:02.1`. A bad GPU mapping could still generate an inappropriate DMA address, but that preceding causal step is not established by the DMAR record alone.

The fault address is below 2^35 and therefore below the reported 39-bit host-address limit (2^39). The separately configured 47-bit **GPU virtual-address** limit is a different address space. This record does not support a 39-versus-47-bit overflow diagnosis. `NO_PASID` is not itself proof that SR-IOV was disabled or misidentified.

## Xe explicitly found a host queue for the CAT event

In `drivers/gpu/drm/xe/xe_guc_submit.c:3001`, the CAT handler obtains the reported GuC ID and calls `g2h_exec_queue_lookup`. That lookup at `:2779` loads from this Xe device's `submission_state.exec_queue_lookup` XArray. If no queue is found, the handler returns EPROTO before printing the detailed `class=rcs ... guc_id=65` message. Unknown PF/VF context has a distinct generic error path at `:3017`.

Therefore the supplied detailed message means the PF driver successfully matched the notification to one of its own execution-queue objects. It does not prove the exact userspace owner of that queue or exclude an earlier cross-VF hardware-state disturbance, but it is stronger evidence of host execution involvement than treating every failure after guest launch as a guest context.

The VF's context IDs are reserved in the PF ID manager and unavailable for PF allocation (`xe_gt_sriov_pf_config.c:887–951`). The manager reserves high IDs for VF ranges and allocates ordinary submissions from the low end (`xe_guc_id_mgr.c:132`). A captured provisioning range can confirm the actual split; do not infer an exact range from quota alone. Existing `xe_exec_queue_memory_cat_error` and queue/job tracepoints can preserve context ID 65 before reset churn; the stock CAT tracepoint does not itself include userspace process ownership.

## No ADL-P GGTT VF-ID encoding mismatch found

i915 ADL-P uses `TGL_GGTT_PTE_VFID_MASK` bits 4:2, then adds PRESENT (`intel_gtt.h:119`, `intel_ggtt.c:2143–2172`). Xe uses bits 11:2 plus PRESENT (`regs/xe_gtt_defs.h:17`, `xe_ggtt.c:943`). For the supported VF IDs 1 through 7 these encodings are identical; VF1's initial ownership PTE is 0x5 in both. The wider Xe mask alone is not an ADL-P incompatibility.

Both drivers reserve a GGTT region, tag the region with its VF ID and invalidate, then send its start/size to GuC: i915 `intel_iov_provisioning.c:688–702` and `intel_ggtt.c:2175`; Xe `xe_gt_sriov_pf_config.c:534–546` and `xe_ggtt.c:948–981`. The software implementation therefore contains the expected ownership operation. Actual post-FLR PTE contents and timing still require capture if suspicion remains.

PF-owned GuC ADS/golden-context buffers being mapped under PF identity is not inherently incorrect. Xe copies its captured default LRC into its ADS in `xe_guc_ads.c:972`; this inspection did not prove a Windows VF context copies a PF-only address or later writes it under the wrong identity. The existing reset-BB-stack-pointer-on-VF-switch GuC workaround is already enabled for ADL-P by Xe's graphics-version range and the observed 70.49.4 firmware (`xe_wa_oob.rules:48`, `xe_guc_ads.c:328`); importing i915's same workaround again is not a supported fix.

## DMA-buffer import is an immediately separable path

For an external DMA buffer, Xe attaches to the importing DRM device (`xe_dma_buf.c:389`), maps it with `dma_buf_map_attachment(..., DMA_BIDIRECTIONAL)` during `xe_bo_move_dmabuf` (`xe_bo.c:736–775`), and consumes scatterlist **DMA** addresses (`xe_res_cursor.h:336`). i915 likewise maps its imported attachment through the DMA-buffer API (`gem/i915_gem_dmabuf.c:238–263`). Neither examined path deliberately uses a VF's device to map a host Looking Glass buffer.

The current official [Looking Glass kvmfr exporter](https://github.com/gnif/LookingGlass/blob/master/module/kvmfr.c#L99) maps exported pages with the attachment device's DMA API and unmaps them when requested. That source is an external comparison; the exact loaded kvmfr revision has not been established. Xe's mapping lifetime follows TTM movement and differs from i915's object page lifetime. No mapping-lifetime bug or faulting-buffer address has been proved here.

The smallest useful hardware discriminator is a fresh same-guest boot with the **host Looking Glass client stopped**, preserving the VF, guest driver and firmware. Read Windows device status independently of Looking Glass. If Code 43 and the PF CAT/DMAR fault disappear, then reproduce by starting Looking Glass and narrow its DMA-buffer path. If Code 43 remains without PF DMA faults, there may be a separate guest-start problem and the two symptoms must not be conflated. Stopping the client after the first GT corruption is weaker than a fresh startup.

Subsequent recovered capture correction: a second VM start in this same already-faulted boot produces its first new PF DMA fault at 717.790880 seconds, **before** the first new `kvmfr_dmabuf_create` at 738.386900. At 735.116206, CAT queue14 is followed 106 microseconds later by a queue14 timeout attributed to host `systemd-logind`. Therefore the first-run 12.633 ms correlation does not establish that a fresh KVMFR export triggers every fault. This second run is not a clean reboot and cannot rule out prior mapping/state damage either. Keep the client-stopped test as isolation, not a diagnosed fix.

For a code-level capture, correlate the first CAT queue with its VM, relevant GPU PTEs and DMA mapping addresses; record imported-buffer attachment device, direction, mapped SG DMA ranges and map/unmap lifetime. Determine whether 0x78226a000 belongs to a current PF DMA mapping or an imported kvmfr range. Only then select a mapping, ownership or lifetime correction. The older runtime-register/handshake hypotheses remain documented in `adlp-runtime-contract-audit.md`, but the new first-fault evidence gives this DMA/execution path priority.
