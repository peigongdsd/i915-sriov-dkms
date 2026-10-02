# ADL-P: analysis of the reuploaded host captures

2026-10-02. This supersedes the earlier CCS-configuration diagnosis as the current test plan. MTL work remains paused. The three replacement archives downloaded successfully from the requested `codex/Develop/` folder; their compressed streams and extracted regular files were validated. The raw captures, coredumps and decoded application memory remain private local evidence. This note contains selected diagnostic facts and hashes.

## Result and next test

The current failure includes **host PF DMA translation faults, render-engine CAT errors, failed engine recovery and full GT resets**. CCS is demonstrably enabled. The loaded Xe source-version identifier matches the module built from our patched branch. Neither an inactive CCS option nor an obviously different source build explains this run.

The next useful hardware test is a **fresh host boot with the same Windows VM and the host Looking Glass client closed**, using RDP or another independent console to inspect the Intel device status. Retain the same guest driver, VF, CCS option and firmware. Capture immediately after the result, while the VM is still running and before VF teardown clears its state. This distinguishes a guest-startup/host-engine failure from the host presentation/import workload without changing the kernel first.

The first run's KVMFR export occurs 12.633 ms before the first DMAR error. However, the second VM attempt faults before any new export is logged. That second attempt shares the already-faulted host boot. These observations justify a controlled test; they do **not** establish KVMFR as the root cause or exonerate it.

## Archive provenance and what their names mean

| Archive | Bytes | Capture time, UTC | SHA-256 |
|---|---:|---|---|
| `adlp-before-ccs.tar.gz` | 121469 | 12:37:09 | `73e581c04e8bc764745afa0a9d90b7f2950930d1597378be8894fa78b80af377` |
| `adlp-after_vf_crash.tar.gz` | 198827 | 12:38:39 | `f801efce2d342ba42cd2b2ae7d1330429ff51edfc2d4de6b18dd572e08ea91a1` |
| `adlp-after-ccs.tar.gz` | 200208 | 12:43:38 | `e6e76f0a72ed3033324208a696c1ee2d12dfec166a43f6b11fe80ccb363c122d` |

All three report `xelp_enable_ccs=Y`, expose `ccs0`, and show actual `RCU_MODE=1`. The first archive is a pre-failure snapshot of an already CCS-enabled boot. These files are **not a CCS-off/CCS-on comparison**. Their kernel logs share the same boot prefix; the last extends the first failed VM run with a second VM start and more failures. The user subsequently confirmed that no other settings were changed between these attempts and Windows consistently showed Code 43. There is no successful Windows startup in this comparison.

All three report Xe `srcversion=E95FB913A81580FDE02EB10`, matching `modinfo -F srcversion` on the locally built patched `xe.ko`. This is a source-version match, not a byte-for-byte module hash or hardware validation of the workaround. The unchanged package banner `2026.09.16-sriov` does not mean the timestamp fix is absent. Kernel is 7.2.8; ADL-P PF is `8086:46a6` at `0000:00:02.0`; its GuC is 70.49.4 and HuC 7.9.3. DG2 firmware lines belong to another GPU.

The collector completed the relevant reads successfully. The initial zero-byte cloud objects were replaced by these valid archives and are no longer a blocker. No collector packaging change is inferred from the failed initial upload.

## First VM attempt: ordered failure

| Host uptime, seconds | Observation | What it establishes |
|---:|---|---|
| 379.553–379.795 | VFIO resets VF `00:02.1`; PF logs VF1 FLRs and VFIO logs reset completion | VF reset activity occurred before the error; these messages do not themselves report reset failure |
| 388.713315 | KVMFR exports 16,384,000 bytes at shared-memory offset 5,701,632 | Buffer export, not proof of successful Xe attachment/mapping/submission |
| 388.725948 | DMAR DMA Write, NO_PASID, requester **PF `00:02.0`**, address `0x78226a000`, reason 0x07 | First recorded IOMMU translation failure |
| 388.725990 | RCS CAT error, GuC ID **65** | PF Xe successfully looked up a host queue for this notification |
| 389.758524–389.788235 | GuC engine-reset request fails; Xe resets the GT | Failure affects the shared host graphics engine and recovery path |
| 394.851709702 | Retained coredump snapshot, GuC ID **49**, Looking Glass | Later timeout, after the first GT reset; does not identify queue 65 |
| 397.889554 | PF DMA fault `0x332792000`, CAT ID **12** | Further failure during the damaged run |
| 408.507338 | PF DMA fault `0x4b0316000`, CAT ID **12** | Repeated failure |
| 419.360718 | VF1 FLR during VM teardown | Subsequent VF state snapshots cannot reconstruct earlier negotiation/counters |

The VF's actual reserved GuC-ID range is **32767–65534**, whereas the CAT IDs are small host IDs. Source independently corroborates this: `xe_guc_exec_queue_memory_cat_error_handler()` calls `g2h_exec_queue_lookup()` against the PF queue registry before printing the detailed CAT line. An unknown context follows a different error path. This identifies host execution involvement, while leaving a preceding VF-induced state disturbance possible. Names such as `systemd-logind` in timeout messages identify the DRM file's recorded owner, which can differ from the current submitting process if descriptors were shared.

DMAR's “Next page table ptr is invalid” refers to **IOMMU tables**, not directly to a GPU GGTT/PPGTT root. The reported addresses fit comfortably within 39 bits. GPU VA width 47 and system DMA-address width 39 describe different address spaces. The configured default IOMMU passthrough policy does not establish the actual PF/VF domain mappings after assignment. Increasing DMA width or disabling translation is not supported by this evidence.

## Second VM attempt: why the first timing correlation is insufficient

The last archive adds VM startup around 706.6 seconds, VF resets around 708.6–708.9 seconds, and another first-for-that-attempt fault:

| Host uptime, seconds | Observation |
|---:|---|
| 717.790880 | PF DMA-write fault `0x71d542000` |
| 717.790895 | RCS CAT, GuC ID **14** |
| 718.923369–718.953269 | Engine reset fails, then GT reset |
| 727.339756 | PF DMA-write fault `0x426ed2000`, CAT ID 14 |
| 730.862948–730.863106 | CAT ID **44**, DMA fault `0x77f46a000`, timeout identifying ID 44 as `systemd-logind` |
| 735.115959–735.116312 | DMA fault `0x5af29a000`, CAT ID **14**, timeout identifying ID 14 as `systemd-logind` |
| 738.386900 | First new `kvmfr_dmabuf_create` message in this VM attempt |
| 741.501044 | A later timeout identifies Looking Glass queue **65**, during broader host failures |
| 751.711915 | VF1 FLR at shutdown |

There are KVMFR mappings before 717.79 seconds, but no newly logged buffer export then. Existing objects, previous reset damage and client configuration are not established by this log. Thus “each failure is immediately triggered by a new KVMFR export” is contradicted. Later Looking Glass queue 65 also cannot retroactively identify queue 65 in the first attempt: IDs are reused across destruction/reset.

## Coredump: useful state, incomplete first-fault coverage

The two post-failure archives contain the **same** 1,910,450-byte coredump, SHA-256 `d54b2ccdac910fe900d6cf6ebeba8416b500c612290be050a8ceafdf7e5dae32`. They are two collections of one retained dump, not independent first-fault captures.

The dump describes Looking Glass queue 49/job 244 about **6.126 seconds after** the initial DMAR fault and **5.063 seconds after** the first GT reset completed. Its engine capture source is `Manual`. The RCS fault/address/ring registers are zero in that snapshot. “Full-capture” refers to register-capture coverage, not preservation of every queue, mapping or the original CAT event.

All **26 ASCII85 sections**, totaling **6,320,128 decoded bytes**, were decoded with native-u32 ordering and checked against their declared lengths. A bounded search of 32-bit-aligned 64-bit address/PTE-page fields found none of the first run's three DMAR addresses. This is not a complete page-table walk: the dump contains selected GPU-VA/object contents, no IOMMU or SG DMA map, and `xe_vm_snapshot_capture()` includes only `XE_VMA_DUMPABLE` mappings. It cannot exclude imported buffers or identify which DMA allocation faulted.

One concrete context observation deserves follow-up: RCS register **`0x21c8` (indirect-context offset) is zero** both in the pre-crash PF default LRC and the decoded later queue-49 LRC. The indirect-context pointer is populated. This matches the observation in the pending ADL offset discussion already recorded in the main report. It is a measured candidate, not proof that it caused queue 65's CAT fault, and is not a capture of Windows' own VF context. A separately gated A/B experiment has now been built; see [its exact commits, scope and test plan](adlp-indirect-offset-experiment.md).

## VF provisioning and service state

All captures agree on VF1's **2 GiB GGTT**, GuC IDs **32767–65534**, and doorbells **0–127**. The provisioned GGTT interval is `[0x7ee00000, 0xfee00000)`. The raw allocator node starts 2 MiB lower because `xe_ggtt` adds its WOPCM/start bias to zero-based allocator offsets; this is not an observed provisioning mismatch. All five default engine-context files are byte-identical across the captures.

The eight exported runtime register values are also unchanged:

| Register | Value |
|---|---|
| `0x0d00` | `0x80000014` |
| `0x9118` | `0` |
| `0x9134` | `0` |
| `0x9138` | `1` |
| `0x913c` | `0x3f` |
| `0x9140` | `0xe00fa` |
| `0x9144` | `0` |
| `0xc1dc` | `0x90001` |

The versions files show base/latest 1.0 without a negotiated VF line. Both post-failure captures were collected **after VF FLR**, which clears negotiated state and adverse-event counters. Consequently these snapshots prove neither that Windows skipped its handshake nor that no adverse event occurred. A bounded decode of the retained live/coredump CTBs found no valid preserved relay packets; raw `0x510x` payload words are not sufficient to identify relay headers. These reset/wrap-limited snapshots cannot recover the startup exchange.

The source-backed differences remain secondary candidates: Xe requires a recorded 1.0 handshake before runtime queries whereas i915 does not enforce the same guard; i915 exports two additional clock registers. No EACCES response, failing runtime query or Windows consumption of those absent entries was observed. A new relay protocol, blanket negotiation bypass or speculative register-table copy is not justified.

## Controlled retest and decision points

1. Reboot the host to clear the existing sequence of engine/GT failures. Keep the tested kernel, `xe.xelp_enable_ccs=1`, GuC, VM topology and guest Intel driver fixed. Leave the host Looking Glass client closed, including any automatic client launch. Start the VM and inspect Windows' Intel device through RDP or another independent console. Record Code 43 and `DEVPKEY_Device_ProblemStatus`, plus the Intel driver version.
2. While the VM is still running, immediately collect the host state using a fresh output path:

   ```sh
   sudo bash collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-no-looking-glass
   ```

   Upload `/tmp/adlp-no-looking-glass.tar.gz` to the same `codex/Develop/` folder. The existing cloud script is sufficient. If a first DMAR/CAT fault appears, collect then; do not wait for repeated recovery or VM shutdown.
3. If that run is stable, test the host client with direct DMA import disabled, preserving its other arguments:

   ```sh
   looking-glass-client app:allowDMA=no
   ```

   This is the documented B7 option. It retains KVMFR shared memory and host GPU rendering while disabling the client's direct dma-buf import; it does not disable all DMA or the guest capture service. Use a fresh host boot for each comparison after a fault. If this works, a further matched run with the normal client setting tests the import boundary. [Official Looking Glass B7 options](https://looking-glass.io/docs/B7/usage/#all-command-line-options).

| Result | Next target |
|---|---|
| No-client run: Windows starts and host stays clean; normal client reproduces fault | Host presentation/import mapping and lifetime; compare DMA-disabled client before blaming guest startup |
| No-client run: Windows remains Code 43 but host stays clean | Separate Windows startup status and PF/VF service trace; the host fault is not sufficient to explain Code 43 |
| No-client run: host still reports DMAR/CAT during guest initialization | Shared engine/context/GuC/VF transition and IOMMU ownership; prioritize first CAT owner and fault-address mapping |
| Host faults before any VM starts | Native ADL-P Xe stability, including the measured indirect-context offset; guest startup is not a necessary trigger |

If the failure survives this control, the next Linux diagnostics should preserve **first-CAT queue ownership before reset**, relevant saved LRC fields and the faulting DMA address's allocation/domain. If the import path is isolated, add attachment-device, original/mapped SG counts, IOVA ranges and map/unmap timing. If Windows alone fails, capture handshake/runtime responses before teardown. These are narrower and more informative than another broad i915-to-Xe port.

The measured zero-offset observation now supports the built, separately gated **ADL-P render-context experiment**, with first-CAT ownership diagnostics. It is not an accepted upstream fix or a demonstrated Windows repair. The existing accepted timestamp correction remains valid Linux code, but the current user result shows that it and CCS enablement have not resolved this Windows case. No Windows binary modification or MTL work is included.
