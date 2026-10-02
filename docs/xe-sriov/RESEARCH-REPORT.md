# Intel SR-IOV research: ADL-P first, then MTL/ARL

Progress report · revision 10 · updated 2026-10-02T21:19:54+08:00

This report supports the concrete goal of fixing Linux Xe SR-IOV on **ADL-P first**, then MTL/ARL, with minimal migration of i915 internals. Windows guest-driver analysis is supporting evidence for separating failure causes. Confirmed source facts, published observations, diagnostic hypotheses, and untested proposals are kept distinct. The assistant has not installed a host driver, changed live GPU configuration or executed a hardware reproduction; user-supplied runtime captures are identified separately.

## Current assessment

**Current task: MTL remains paused; the valid reuploaded ADL-P captures establish host PF DMA/CAT failures while Windows remains Code 43.** All three already have CCS enabled (`Y`, `RCU_MODE=1`). Loaded Xe `srcversion=E95FB913A81580FDE02EB10` matches the previously built timestamp-patched module. The first recorded failure is PF `00:02.0` DMAR write fault → host RCS CAT → failed engine reset → GT reset. VF1 owns GuC IDs 32767–65534, whereas CAT IDs 65/12/14/44 are host queues. The retained Looking Glass coredump is a later post-reset timeout, not the first CAT context. The second VM attempt faults before any new KVMFR export, so the first run's 12.633 ms export-to-fault timing is not a root-cause diagnosis. The user confirms unchanged settings and persistent Code 43 in both attempts.

**New measured Linux context lead:** the pre-crash PF default RCS context has indirect-context offset register `0x21c8=0`, matching the observation in the pending ADL Xe proposal. A separate experimental branch, `codex/xe-adlp-indirect-offset-2026-10-02`, now initializes the Gen12 value `0xd << 6` (`0x340`) only for ADL-P render contexts and logs first-CAT queue ownership. Diagnostic-only commit `22a6e50` and combined experiment `ef7ad6b` both passed compilation, MODPOST and module linking against Linux 7.2.8, with independent code review. Hardware behavior remains untested. A fresh-boot run with the host Looking Glass client closed is a useful low-cost control; the test plan keeps guest driver/firmware/CCS fixed. See the current capture-analysis chapter immediately below for evidence and the test decision table.

**ADL-P already has upstream Xe SR-IOV enablement, but its first failing stage must be identified.** Current upstream includes the platform flag, VF/PF ABI handling, GGTT provisioning, legacy interrupt path, and GuC submission. A VF that times out while recording its default context fails before Mesa starts. That points first to the initial context/GGTT/GuC/reset/interrupt sequence, not to speculative Mesa fixes or a blanket claim that 39-bit DMA is invalid.

**The older MTL attempt progressed further than its default branch suggests.** The fork's June 18 trace branch records accelerated Windows rendering with persistent composition/video artifacts, successful sampled GGTT writes, and completed invalidations. Those observations constrain the remaining investigation; they do not prove all mappings or cache policies correct.

**The nested-virtualization startup failure has a separate, concrete Windows-driver lead.** Intel officially acknowledges misclassifying nested Hyper-V as a native Hyper-V host in [KB 000102878](https://www.intel.com/content/www/us/en/support/articles/000102878/graphics.html). A public July report describes an earlier skipped startup-state transition leading to `STATUS_INVALID_PARAMETER` and Code 43. Intel's live KB still says investigation is ongoing; a closed community issue is not evidence of a shipped fix.

## ADL-P: analysis of the reuploaded host captures

2026-10-02. This supersedes the earlier CCS-configuration diagnosis as the current test plan. MTL work remains paused. The three replacement archives downloaded successfully from the requested `codex/Develop/` folder; their compressed streams and extracted regular files were validated. The raw captures, coredumps and decoded application memory remain private local evidence. This note contains selected diagnostic facts and hashes.

### Result and next test

The current failure includes **host PF DMA translation faults, render-engine CAT errors, failed engine recovery and full GT resets**. CCS is demonstrably enabled. The loaded Xe source-version identifier matches the module built from our patched branch. Neither an inactive CCS option nor an obviously different source build explains this run.

The next useful hardware test is a **fresh host boot with the same Windows VM and the host Looking Glass client closed**, using RDP or another independent console to inspect the Intel device status. Retain the same guest driver, VF, CCS option and firmware. Capture immediately after the result, while the VM is still running and before VF teardown clears its state. This distinguishes a guest-startup/host-engine failure from the host presentation/import workload without changing the kernel first.

The first run's KVMFR export occurs 12.633 ms before the first DMAR error. However, the second VM attempt faults before any new export is logged. That second attempt shares the already-faulted host boot. These observations justify a controlled test; they do **not** establish KVMFR as the root cause or exonerate it.

### Archive provenance and what their names mean

| Archive | Bytes | Capture time, UTC | SHA-256 |
|---|---:|---|---|
| `adlp-before-ccs.tar.gz` | 121469 | 12:37:09 | `73e581c04e8bc764745afa0a9d90b7f2950930d1597378be8894fa78b80af377` |
| `adlp-after_vf_crash.tar.gz` | 198827 | 12:38:39 | `f801efce2d342ba42cd2b2ae7d1330429ff51edfc2d4de6b18dd572e08ea91a1` |
| `adlp-after-ccs.tar.gz` | 200208 | 12:43:38 | `e6e76f0a72ed3033324208a696c1ee2d12dfec166a43f6b11fe80ccb363c122d` |

All three report `xelp_enable_ccs=Y`, expose `ccs0`, and show actual `RCU_MODE=1`. The first archive is a pre-failure snapshot of an already CCS-enabled boot. These files are **not a CCS-off/CCS-on comparison**. Their kernel logs share the same boot prefix; the last extends the first failed VM run with a second VM start and more failures. The user subsequently confirmed that no other settings were changed between these attempts and Windows consistently showed Code 43. There is no successful Windows startup in this comparison.

All three report Xe `srcversion=E95FB913A81580FDE02EB10`, matching `modinfo -F srcversion` on the locally built patched `xe.ko`. This is a source-version match, not a byte-for-byte module hash or hardware validation of the workaround. The unchanged package banner `2026.09.16-sriov` does not mean the timestamp fix is absent. Kernel is 7.2.8; ADL-P PF is `8086:46a6` at `0000:00:02.0`; its GuC is 70.49.4 and HuC 7.9.3. DG2 firmware lines belong to another GPU.

The collector completed the relevant reads successfully. The initial zero-byte cloud objects were replaced by these valid archives and are no longer a blocker. No collector packaging change is inferred from the failed initial upload.

### First VM attempt: ordered failure

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

### Second VM attempt: why the first timing correlation is insufficient

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

### Coredump: useful state, incomplete first-fault coverage

The two post-failure archives contain the **same** 1,910,450-byte coredump, SHA-256 `d54b2ccdac910fe900d6cf6ebeba8416b500c612290be050a8ceafdf7e5dae32`. They are two collections of one retained dump, not independent first-fault captures.

The dump describes Looking Glass queue 49/job 244 about **6.126 seconds after** the initial DMAR fault and **5.063 seconds after** the first GT reset completed. Its engine capture source is `Manual`. The RCS fault/address/ring registers are zero in that snapshot. “Full-capture” refers to register-capture coverage, not preservation of every queue, mapping or the original CAT event.

All **26 ASCII85 sections**, totaling **6,320,128 decoded bytes**, were decoded with native-u32 ordering and checked against their declared lengths. A bounded search of 32-bit-aligned 64-bit address/PTE-page fields found none of the first run's three DMAR addresses. This is not a complete page-table walk: the dump contains selected GPU-VA/object contents, no IOMMU or SG DMA map, and `xe_vm_snapshot_capture()` includes only `XE_VMA_DUMPABLE` mappings. It cannot exclude imported buffers or identify which DMA allocation faulted.

One concrete context observation deserves follow-up: RCS register **`0x21c8` (indirect-context offset) is zero** both in the pre-crash PF default LRC and the decoded later queue-49 LRC. The indirect-context pointer is populated. This matches the observation in the pending ADL offset discussion already recorded in the main report. It is a measured candidate, not proof that it caused queue 65's CAT fault, and is not a capture of Windows' own VF context. A separately gated A/B experiment has now been built; see [its exact commits, scope and test plan](adlp-indirect-offset-experiment.md).

### VF provisioning and service state

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

### Controlled retest and decision points

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

---

## ADL-P render indirect-context experiment

2026-10-02. This is an isolated Linux Xe experiment motivated by the user's actual captures, not a demonstrated Windows Code 43 fix. MTL work remains paused.

### Why this change is now testable

The supplied **pre-crash** PF default RCS context has an indirect-context pointer but register `0x21c8` is zero. A later saved host LRC also has zero there. Working i915 initializes the Gen12 render field to `0xd` in bits 15:6, giving register value **`0x340`**. The recent Xe discussion identifies the same zero default-image observation after an earlier change stopped explicit programming. [Intel review](https://lkml.rescloud.iu.edu/2609.3/17001.html), [author's default-context follow-up](https://www.mail-archive.com/dri-devel@lists.freedesktop.org/msg640961.html).

This is stronger evidence for a controlled context experiment than generic Code 43. It remains weaker than a causal reproduction: the retained dump follows the first GT reset, the first CAT queue's context was not captured, and Windows constructs its own VF contexts. A PF correction can affect shared engine/default-context behavior without directly changing Windows' LRC construction.

### Exact code and scope

Repository: `git@github.com:peigongdsd/i915-sriov-dkms.git`.

| Revision | Purpose | Local Xe srcversion |
|---|---|---|
| Existing `codex/xe-adlp-2026-10-02` at `a29999e2aa746782f05c8ed1e9e17811267dd914` | Accepted timestamp correction and original diagnostics collector; matching source version observed in user captures | `E95FB913A81580FDE02EB10` |
| `22a6e50e08f48048fff4d3ddceeaf0b4401ddaa3` | First-CAT diagnostics only; no offset behavior change | `A7F071ECFA1550AA20DF3BA` |
| `ef7ad6b9a803f84153161aa8dc6c3ef8dbe50c83` | Same diagnostics plus the ADL-P render offset experiment | `786184C2F6AEDD74A6B2FDB` |

The new branch is **`codex/xe-adlp-indirect-offset-2026-10-02`**. Later commits on it may update documentation; the two immutable source commits above identify the code. Source-version values are references from these builds, not cryptographic identities of every possible downstream build.

The behavior change is in existing `setup_indirect_ctx()` in `drivers/gpu/drm/xe/xe_lrc.c`. After writing the indirect-context pointer, it writes:

```c
if (lrc_to_xe(lrc)->info.platform == XE_ALDERLAKE_P &&
    hwe->class == XE_ENGINE_CLASS_RENDER)
	xe_lrc_write_ctx_reg(lrc, CTX_CS_INDIRECT_CTX_OFFSET,
			     REG_FIELD_PREP(REG_GENMASK(15, 6), 0xd));
```

This reaches initial Linux kernel contexts/default-context recording as well as later Linux render contexts. It uses the existing Xe LRC lifecycle. It does not adopt the proposal's broad all-pre-Xe2 condition, alter compute/video/copy offsets, change DMA width or add a relay protocol. The source descriptor covers ADL-P and any PCI subplatform that Xe classifies under `XE_ALDERLAKE_P`; the condition is on the driver platform enum, not a marketing name.

The diagnostic commit adds two messages when Xe receives a CAT notification for an ADL-P single-width render queue:

```text
ADLP CAT owner: guc_id=... flags=... in ... [...]
ADLP CAT saved LRC: ggtt=... per_ctx=... indirect=... offset=...
```

It obtains an LRC reference using the existing queue helper and releases it after reading saved context memory. It adds no live MMIO reads, forcewake, waits or mapping changes. The owner is the **DRM file's recorded process/PID**, which can differ from the current submitter when a file descriptor is shared. The saved fields are not an atomic live hardware snapshot. Existing recovery remains in place. This provides the previously missing first-CAT context identity even when the only later coredump belongs to another queue.

### Validation performed

Both the diagnostic-only revision and the combined experiment compiled and relinked the complete Xe module successfully against the same Linux **7.2.8** headers. `MODPOST` passed, and the compatibility-module target remained valid. Incremental compilation reused unchanged objects from the previously successful full build. Both changes received an independent static review of field encoding, platform/class gates, call-path coverage, queue/LRC lifetime and lock use.

The headers-only build environment lacked `vmlinux`, so BTF generation was skipped; it also reported the existing pahole-version warning. These are retained in the build logs. No module was loaded by the assistant and no hardware outcome is claimed.

Records: [diagnostic build](patches/adlp/cat-diagnostics-build-verification.json), [experiment build](patches/adlp/indirect-offset-build-verification.json), [diagnostic log](patches/adlp/build-cat-diagnostics-7.2.8.log), [experiment log](patches/adlp/build-indirect-offset-7.2.8.log).

### How to test on the ADL-P host

Keep an existing working boot generation available. This changes when an indirect batch runs during context restoration, so stability must be checked as well as Windows startup.

1. A cheap initial control is a fresh host boot on the existing build, with the host Looking Glass client closed. Start the unchanged VM and inspect the Intel device through RDP or another independent console. The prior two VM attempts used unchanged settings but shared a boot containing earlier GT resets. This clean control has not yet been recorded.
2. Point the existing Xe package source at **`ef7ad6b9a803f84153161aa8dc6c3ef8dbe50c83`** (or the new experimental branch head), using the same NixOS packaging/build method as the previous test. Rebuild the boot configuration and reboot the host. Retain `xe.xelp_enable_ccs=1`, one VF, GuC 70.49.4 and the same Windows driver. No Windows-driver reinstall is required for this experiment.
3. Before launching the VM, collect a baseline with the already uploaded script:

   ```sh
   sudo bash collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-offset-before-vm
   rg '0x21c8' /tmp/adlp-offset-before-vm/debug-tile0_gt0_default_lrc_rcs.txt
   ```

   Expect register **`0x21c8 = 0x00000340`**, and CCS should still be `Y`. Also retain `module-srcversion.txt`. If the image still shows zero, report that before interpreting Windows results: it could mean the wrong build booted or that the field did not survive default-context capture.
4. Start the same Windows VM with the host Looking Glass client closed initially. Record separately: Windows Code 43 / problem NTSTATUS, first host DMAR/CAT time, whether native host graphics remain responsive, and whether the new diagnostic reports `offset=0x00000340` on a failing queue. If stable, repeat the normal client workload to test the original trigger.
5. Immediately after the first result, **before shutting down the VM**, collect:

   ```sh
   sudo bash collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-offset-after-vm
   ```

   Upload both `.tar.gz` files to `codex/Develop/`. The collector already includes the relevant saved LRC, kernel log, module identity, PF/VF state and surviving devcoredump. Avoid waiting through a reset storm; the useful event is the first failure.

For the cleanest code A/B, compare `22a6e50` (diagnostics only) against `ef7ad6b` (same diagnostics plus offset). Use a fresh host boot for each, with unchanged guest/client conditions. This avoids confusing better diagnostics with an offset effect. Returning to the previous boot generation rolls back the experiment.

### Interpret each outcome separately

| Observation with verified offset 0x340 | Conclusion and next action |
|---|---|
| Host stays clean and Windows starts | Evidence for this narrow fix; repeat matched diagnostics-only versus offset boots before promoting it |
| Host faults disappear but Windows remains Code 43 | Host context issue and guest startup failure are separate; retain this result and investigate guest NTSTATUS/service sequence |
| Host still reports DMA/CAT errors | Use the new first-CAT owner/LRC fields to locate the failing object/domain; offset alone is insufficient |
| No VM is running and native graphics regress | Roll back and retain the first host capture; this experimental context change is unsuitable as-is |

The second and third outcomes remain plausible. Missing service negotiation, clock-register compatibility and nested Windows classification are still separate hypotheses; none is established by the post-FLR snapshots. This branch is a measured, minimal experiment toward a Linux fix, not a declaration that the remaining guest problem is solved.

---

## Executive synthesis: Linux Xe repair, ADL-P first

The first ADL-P implementation is now committed as `32d16259df98d7153daaa9b8c461c2eaa0d24394`, an exact backport of accepted Xe change `38631a7bce19`. It corrects duplicated Xe_LP timestamp-workaround emission in one existing Xe file. The full Xe and compatibility-module build against Linux 7.2.8 headers passed; no module has been installed or hardware-tested. No MTL code change is included. The source defect is established, while a repair of the user's particular failure remains unproven.

**A Windows guest does not execute Linux VF `xe_lrc.c`.** This backport directly changes contexts created by the patched Linux Xe driver. Updating only the Linux PF does not apply that code to a Windows guest's privately constructed contexts, nor to an unpatched Linux guest. PF behavior can affect shared hardware, but a Windows improvement would need its own causal evidence. This distinction governs the first test plan and prevents a buildable Linux fix from being reported as a demonstrated Windows-vGPU repair.

The design constraint is to reuse Xe's existing abstractions and relay transport. No new MTL relay protocol has been accepted as the plan. Future MTL work must distinguish existing guest wire-protocol compatibility handlers, shared Xe transport, and i915's older binder/coalescing internals. A path without PF mediation remains an explicit investigation question; Intel's affected-MTL workaround currently requires VF requests to go through the PF, so a direct-VF alternative needs contrary applicability, stepping or firmware evidence. The PF's permission to write GSM directly does not by itself grant that permission to its VFs.

| Observed failure | Strongest current evidence | First discriminating check | Implementation direction if confirmed |
|---|---|---|---|
| ADL-P Linux VF fails its first default-context job | Current Xe performs GGTT kernel submission and an intentional reset before userspace; related Xe_LP reports include IOMMU/CAT errors | Match the first fault address to LRC/ring/HWSP/batch mappings; separate expected reset, context save, submission and interrupt completion | Correct Xe mapping ownership or context/reset setup through its existing BO, GGTT, GuC and RTP mechanisms |
| ADL-P Linux VF starts, but a Windows VF does not | Upstream Xe_LP CCS0 policy differs from experimental DKMS; the Windows product lane also retains the nested-root classifier behavior | First hold nested Hyper-V inactive; compare engine enablement, GuC engine masks, saved register state and actual first guest submission | A narrowly gated engine/firmware contract change if proved; maintain engine-query/URB agreement for Linux guests |
| VF starts until guest Hyper-V/VBS/WSL is activated | Intel acknowledges a classification defect; original 7092 and 9033 routines preserve native-root state for nested roots; 9033 also has a conditionally reproduced resource rejection | Compare VMX hidden, VMX exposed with Hyper-V inactive, and Hyper-V active before any L2 starts; capture CPUID and the exact startup branch | Correct earlier guest-driver environment/state resolution while retaining later validity checks; no Xe GGTT rewrite follows from this evidence |
| MTL Windows accelerates but corrupts composition/video | The June fork records successful sampled updates and completed invalidations; declared i915/Xe PAT and MOCS tables already match | Locate one corrupt surface before presentation; trace its PPGTT, command/surface MOCS, AUX metadata and producer/consumer synchronization against working i915 | Preserve Xe-native MTL bring-up; repair the measured per-surface, per-engine or PF/GuC contract |
| ARL is assumed equivalent to MTL | The current Xe PCI IDs share the MTL descriptor, but firmware/IP/stepping differ by SKU | Record device ID and graphics/media versions, then repeat the smallest MTL reproduction | Gate fixes by actual affected IP/stepping and validate each target |

Three tempting shortcuts are specifically unsupported. Increasing ADL's DMA width does not follow from a PF-tagged IOMMU fault. Applying a blanket all-platform indirect-context-offset patch does not follow from the ADL-P observation; the new experimental branch is narrowly gated and unvalidated on hardware. Replacing MTL's AUX-map architecture with Xe2 FlatCCS, or globally rewriting GGTT PAT indices, does not identify the defective Windows surface policy.

The modern alternatives are already substantial: RTP entries feed GuC ADS register preservation, Xe supplies BO/VM_BIND and coherency machinery, shared-GGTT/per-GT provisioning exists, and firmware-authorized direct GSM access is a legitimate MTL PF backend. Remaining hardware and guest-protocol requirements should be expressed through those mechanisms. This study has produced narrowed targets and reproducible classifier evidence; it has not yet produced a hardware-validated repair for the user's ADL-P or MTL/ARL case.

## Implemented ADL-P backport and validation status

| Item | Recorded result |
|---|---|
| Clean upstream-sync base | `codex/upstream-sync-2026-10-02`, strongtz commit `f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88` |
| Implementation branch | `codex/xe-adlp-2026-10-02` |
| Implementation commit | `32d16259df98d7153daaa9b8c461c2eaa0d24394` |
| Accepted upstream source | `38631a7bce195b88814b93bf2b6d3e48c827fef2`, authored September 25, accepted October 1, 2026 |
| Code delta | `drivers/gpu/drm/xe/xe_lrc.c`: 25 insertions, 13 deletions |
| Build | **Passed, exit 0:** complete `xe.ko` and `intel_sriov_compat.ko` against Linux 7.2.8 development headers; GCC 16.2.0 and binutils supplied through a Nix build environment |
| Runtime validation | Assistant performed no installation or hardware execution. User captures now show a matching loaded source version with CCS enabled, but Windows still fails and the PF reports DMA/CAT errors. |
| Repository delivery | Both new branches pushed over SSH and verified by remote ref readback; initial ADL-P publication head `2576d0c17909fc5ef450744009c7d4df6528730f` |

The build completed `MODPOST` and linked both modules without unresolved-symbol errors. The log records a missing optional Nix channel path, a `pahole` version warning, and skipped BTF generation because `vmlinux` was unavailable. Those environment limitations are retained in `patches/adlp/build-7.2.8.log`; build success establishes compilation/linkage for this kernel, not GPU correctness or all-kernel DKMS compatibility.

Published and verified: [upstream-sync branch](https://github.com/peigongdsd/i915-sriov-dkms/tree/codex/upstream-sync-2026-10-02) and [ADL-P implementation branch](https://github.com/peigongdsd/i915-sriov-dkms/tree/codex/xe-adlp-2026-10-02). The report and validation records are published under `docs/xe-sriov/` on the implementation branch. The source commit and clean baseline above identify the reviewable code independently of later documentation commits.

The incorrect rebase had placed `Wa_16010904313` in both the indirect context and the post-restore workaround batch. The backport carries the setup location through Xe's existing buffer-setup callbacks and emits the workaround once in the required location:

| Engine class | Correct emission location |
|---|---|
| Render (RCS), compute (CCS) | Indirect context |
| Copy (BCS), video decode (VCS), video enhancement (VECS) | Post-restore workaround batch |

This retains the existing workaround applicability gate and Xe's context/buffer lifecycle. It introduces no i915 memory-management code, GGTT relay implementation, new platform-enablement flag or MTL workaround. The clean sync branch is the comparison baseline; the user's historical MTL branches remain separate.

The earlier baseline-versus-backport Linux VF comparison remains useful for validating the Linux context correction. The valid user captures now establish a matching loaded source version, active CCS, PF DMA/CAT failures and a zero indirect-context offset in the pre-crash default RCS image. These measured observations motivate a separate, narrowly gated context experiment; they do not prove why Windows reports Code 43. The source correction does not by itself repair Windows' environment classifier or establish that a VF failure before context execution is caused by this workaround.

## Work completed and work now underway

| Area | Completed | Still unresolved |
|---|---|---|
| Upstream Xe | Acquired full official history, performed targeted source/diff review, committed the accepted Xe_LP backport, and passed the full Xe/compat build | Validate the user's exact failure on hardware |
| Working i915 versus MTL Xe fork | Compared implementation and later recorded experiments; separated retained bring-up from reverted experiments | **Paused at user request.** Windows composition artifacts, effective guest surface/cache/auxiliary state remain unresolved |
| Mesa / Intel history | Read exact commits on Xe support policy, Xe_LP URB reservation, MTL AUX maps, PAT/coherency | Applicability to an observed failing allocation or workload |
| Windows nested Hyper-V | Emulated original classifiers in both branches and reproduced a conditional 9033 resource-initialization rejection | Actual guest resource descriptors, full Windows/GPU behavior and identity with the older 8826 report |
| Official Windows packages | Both packages extracted; INF matches verified for ADL-P in 7092 and MTL/ARL in 9033; module hashes and classifier RVAs recorded | Map private state fields to complete startup control flow; match the user's actual installed driver |

Official package evidence:

| Package | Bytes | SHA-256 |
|---|---:|---|
| `gfx_win_101.7092.exe` | 780899944 | `9643cc60a899ceadf65df2ec80c17cdb69daeb41cdb2c9ccde0d214a79f968f8` |
| `gfx_win_101.9033.exe` | 932338896 | `86d3ab3ef54610f6680c3649e63c9bac73a9df5e54f5dc7aba17f45c71b2e2bf` |

### Independent Windows binary result: nested-root distinction is absent in the inspected classifier

Both packages contain `Graphics/igdkmdn64.sys`. The 7092 INF is dated 2026-09-03 and includes ADL-P IDs such as `8086:46A6`; the 9033 INF is dated 2026-09-24 and includes MTL `7D40/7D45/7D55` and ARL `7D51/7D67` install sections. These are package compatibility checks, not proof that either is the user's installed driver.

| Module version | Kernel-module SHA-256 | Classifier RVA | Observed object fields |
|---|---|---|---|
| 32.0.101.7092 | `454624942bf9a79a75fd1bfe6c6a2f8d499aabef45cb4268a1353d527902d098` | `0xB3A0` | state `+0xF28`, vendor `+0xF2C` |
| 32.0.101.9033 | `2969ef18daf397b43353dd4ff465f52a8107fc1a612eab4a8cc2703dee919a4d` | `0xB680` | state `+0xE98`, vendor `+0xE9C` |

The original machine-code routines were executed in isolated CPU emulation with controlled CPUID responses. The following values are raw internal fields, not official Intel enum definitions. An Intel CPU-brand input was used for the directly comparable cases.

| Supplied environment | 7092 state / vendor | 9033 state / vendor |
|---|---:|---:|
| No hypervisor | `3 / 0` | `2 / 0` |
| KVM | `0 / 5` | `0 / 5` |
| VMware | `0 / 2` | Not separately run |
| Hyper-V child partition | `0 / 3` | `0 / 3` |
| Native Hyper-V root with management privileges | `3 / 3` | `2 / 3` |
| Nested Hyper-V root with the same privileges and nesting bit available | `3 / 3` | `2 / 3` |

For the Hyper-V root cases, these routines query CPUID `0x40000003` for privilege information but never query `0x40000004`, where Microsoft's TLFS defines EAX bit 12 to indicate that the hypervisor is nested within a Hyper-V partition. Both retain the same initial state for native and nested roots under the tested inputs. This independently corroborates the specific classification mechanism described in [Intel KB 000102878](https://www.intel.com/content/www/us/en/support/articles/000102878/graphics.html), with separate evidence for the ADL-generation and newer-generation packages. The differing state values and offsets show why a byte patch or offset from another driver version cannot be reused blindly. The traces also never query `0x40000001` for the `Hv#1` interface identifier. [Microsoft's feature-discovery specification](https://learn.microsoft.com/en-us/virtualization/hyper-v-on-windows/tlfs/feature-discovery) reserves the vendor string for diagnostics and recommends interface identity for compatibility decisions. A proposed correction should check supported leaf ranges, preserve the real interface and privileges, and interpret the actually exposed nesting fields. EAX bit 12 is not a universal detector of nesting under every host vendor; its applicability to a particular KVM/Hyper-V stack needs a guest CPUID capture.

**Correction to revision 3:** the 9033 image's `VF_CAP_REG` read at `0x254CF` is guarded by a platform selector that excludes MTL/ARL. Its presence in the image must not be presented as a read executed on those platforms. In 7092 the separately analyzed resource branch reads `0x1901F8`, checks bit 0, and sets its VF-mode field at `+0x56B98`; a nonzero hypervisor vendor then skips its corrective environment-state clear. The precise platform dispatch must be retained in interpreting either binary.

The completed 9033 follow-up supplies a different and more directly relevant result. Device-ID dispatch maps MTL `7D45/7D55` to internal enum `0x4F8` and ARL `7D67` to `0x4F9`. Executing the original entire resource-parser routine at RVA `0x25080`, with Microsoft vendor 3 and VF-mode field 2, gives:

| Synthetic Windows resources, tested separately for MTL and ARL | Environment state 0 | Environment state 2 |
|---|---|---|
| One 16 MiB memory descriptor | Success (`0`) | `STATUS_INVALID_PARAMETER` (`0xC000000D`) |
| That descriptor plus a second 256 MiB memory descriptor | Success (`0`) | Success (`0`) |

The second descriptor sets an alternate acceptance flag. Static call tracing connects the classifier and parser to the same initialization sequence, and follows the parser's error through its callers. This establishes a **conditional classification-to-resource-rejection path** in 9033. It does not establish the user's actual resource layout, prove that this is the public 8826 report's identical guard, or propose adding a fictitious PCI resource. Detailed evidence is in `windows/analysis/9033-findings.md`, `9033-resource-emulation.json` and `emulate_9033_resources.py`; the ADL-generation study remains separately recorded in `windows/analysis/7092/findings.md`.

**Scope:** the isolated classifier routines and the 9033 resource-parser routine executed as original machine code under a CPU emulator. String/memory helpers, logging and stack-cookie checking were substituted for the classifier runs; the parser used synthetic Windows resource descriptors and controlled object fields, with logging/PCI-helper stubs where reached. The single-descriptor VF case reaches only the logging stub. Windows, GPU hardware, PF/VF communication and full driver startup were not simulated. These results do not prove the reported Code 43 on the user's machine or explain the separate MTL composition artifacts. They guide which guest CPUID and resource evidence to capture while the Linux ADL-P fix remains the implementation priority.

Reproducible machine-readable records: `windows/analysis/7092/classifier-emulation.json` and `windows/analysis/9033-classifier-emulation.json`. The 7092 module's PE version metadata independently reports `32.0.101.7092` and its embedded CodeView/PDB identifier was retained in `windows/analysis/7092/metadata.json`; an embedded PDB reference is not a recovered private symbol file. Exact GUID-plus-age lookups for both module PDBs on Microsoft's public symbol server returned HTTP 404; no private symbols were recovered. That server response does not prove that symbols do not exist elsewhere.

## Research priorities

1. ADL-P first: publish the committed, build-validated accepted workaround backport and run the matched runtime comparison. Identify whether the user's first failure is VF probe, initial submission, or Windows-only initialization; a Windows guest does not run the patched Linux VF context code.
2. For ADL-P testing, record the exact kernel, GuC and guest-driver identities, then compare one VF under matched i915 and Xe PF conditions. Preserve current Xe BO/GGTT/GuC/RTP machinery and screen older builds for already-fixed workaround defects.
3. Only after the ADL-P phase, return to MTL/ARL. Study the existing Xe relay transport, compatibility handlers for existing guest requests, and the evidence required for a path without PF mediation. Keep accepted modern MTL fixes recorded for that phase rather than mixing them into the first patch.
4. Use Windows classifier/resource results as a separate diagnostic control for nested-only failures. Match real CPUID and resource descriptors before attributing a current guest failure or modifying private state logic.


## Detailed source investigations

The following chapters retain the detailed findings and citations collected so far. Historical support statements are dated; current source status takes precedence over older policy tables. The combined report incorporates subsequent evidence explicitly; the individual source notes remain available as separate research records.


---

## Upstream Xe SR-IOV: ADL-P source audit

Audited 2026-10-02. Upstream Linux checkout: `sources/linux`, commit `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`, committed 2026-10-01T12:47:16-07:00. All Linux paths and line numbers below refer to this immutable snapshot. No runtime changes or hardware tests were performed.

### Status and what Intel actually enabled

`drivers/gpu/drm/xe/xe_pci.c:263` defines ADL-P with `.has_sriov=true`, `.require_force_probe=true`, 39-bit DMA, 48-bit GPU VA, one GT per tile, LLC and cached page tables. ADL-S/N and TGL have the same important properties. Raptor Lake U is an ADL-P subplatform. Therefore current upstream is not missing the basic ADL enablement flag.

Intel commit [2e761039985271a69bf6eada8f236701f8594638](https://github.com/torvalds/linux/commit/2e761039985271a69bf6eada8f236701f8594638), authored 2025-07-22, promoted ADL/ATSM from the CI topic branch and `CONFIG_DRM_XE_DEBUG` gating. Its rationale was that CI had already exercised these platforms, and that `require_force_probe` remained an explicit guard. This supersedes the June 2025 support-status question saying ADL SR-IOV was CI-only.

Intel commit [6983ea9cd720fdd409b4944caf9605731323bb8d](https://github.com/torvalds/linux/commit/6983ea9cd720fdd409b4944caf9605731323bb8d) adds TGL similarly; Intel specifically says TGL was used during feature development but lacked official SR-IOV CI coverage.

That is development availability, not production support. Intel's Matt Roper reiterated in [2026-09-30 review](https://lkml.rescloud.iu.edu/2609.3/17001.html) that Xe1/ADL force-probe support targets driver developers and might lack hardware workarounds. His statement should not be conflated with the separately true `.has_sriov=true` status.

MTL descriptor `xe_pci.c:384` has no `.has_sriov` and is also force-probe. This is a distinct enablement problem. ADL's 39-bit DMA versus MTL's 46-bit DMA does not establish a DMA bug; supported upstream ADL/TGL descriptors deliberately use 39 bits.

### PF/VF initialization and actual mechanisms

1. `xe_sriov.c:62` recognizes VF through `VF_CAP_REG` and PF through PCI/runtime readiness, conditional on platform capability. A hardware-advertised capability with `has_sriov=false` is explicitly suppressed.
2. ADL-P PF selects `i915/adlp_guc_70.bin` with recommendation 70.44.1 (`xe_uc_fw.c:117`). Filename major selection and recommended version are distinct; inspect the loaded firmware, not package age. VF does not upload its own independent GuC.
3. VF minimum GuC interface is 1.1 for TGL through PVC (`xe_gt_sriov_vf.c:170`); newer families require at least 1.2 for GMD_ID discovery. PF/VF relay ABI currently negotiates 1.0 (`abi/guc_relay_actions_abi.h:20`, `xe_gt_sriov_vf.c:826`). Firmware release number, GuC submission ABI, and PF/VF relay ABI are separate version spaces.
4. The PF supplies fuse/runtime register data; TGL/ADL use the gfx1200 runtime table (`xe_gt_sriov_pf_service.c:20`, `:118`). VF MMIO reads not marked VF-accessible go through its cached virtual view (`xe_mmio.c:231`). Topology is therefore not simply unrestricted guest MMIO probing.
5. ADL already receives the required PF `VIRTUAL_CTRL_REG.GUEST_GTT_UPDATE_EN` write (`xe_gt_sriov_pf.c:140`). PF assigns GGTT space using PTE VFID bits and the PRESENT bit (`xe_ggtt.c:943`). VF uses only its provisioned GGTT interval (`xe_ggtt.c:411`), then direct GSM MMIO PTE updates (`xe_ggtt.c:238`). There is an explicit posted-write read and TLB invalidation (`xe_ggtt.c:577`).
6. System memory buffers use DMA API mappings (`xe_bo.c:403`); the device applies the configured DMA mask (`xe_device.c:702`). A trace must distinguish CPU physical addresses, DMA/IOMMU IOVAs, GGTT addresses, and PPGTT GPU VAs. Increasing 39 to 46 is not a justified repair.
7. ADL-P VF IRQ is supported without memory-based interrupts: `vf_irq_reset` has the gfx<1210 register interrupt path (`xe_irq.c:627`). The warning that migration requires memory-based IRQ says migration is disabled; it does not say basic SR-IOV execution is unsupported.

### Earliest GPU execution is the right localization point

`xe_gt_record_default_lrcs()` (`xe_gt.c:385`) creates a kernel queue with `vm=NULL` (`:409`), submits the workaround/state initialization batch (`:417`), then submits a NOP on another queue (`:424`) to force the first context image to be saved. This becomes the template for future contexts.

The batch is from the kernel BB pool and GGTT mapped. `get_ppgtt_flag()` (`xe_ring_ops.c:272`) returns zero for `vm=NULL`. Accordingly, an `emit_wa_job -ETIME` during VF probe is not evidence of a failed userspace VM_BIND or Mesa PPGTT mapping: the basic GGTT/context/GuC/interrupt path already failed before that.

One actual source difference worth an isolated experiment: i915 initializes PPGTT registers even for a GGTT context by using its GGTT alias VM (`sources/i915-sriov-dkms/drivers/gpu/drm/i915/gt/intel_lrc.c:912`, `:972`); Xe only sets PPGTT root when a VM exists (`xe_lrc.c:1526`). That does **not** prove the NULL root is wrong: these jobs are GGTT, restore inhibit and GuC handle other context state. If implicated by fault address/register captures, use an Xe scratch/kernel VM and existing page-table helpers rather than importing i915 VM lifetime code.

The [ADL-S UHD770 first-person issue #454](https://github.com/strongtz/i915-sriov-dkms/issues/454) reports VF `emit_wa_job -ETIME`, PF-attributed IOMMU write fault and engine CAT error while i915 works. It corroborates the stage of failure on a related Xe_LP platform, not the cause on ADL-P. Its assertion that only 46-bit/newer hardware is enabled is contradicted by upstream source. “Next page table ptr is invalid” here is a DMAR/IOMMU report, not by itself a GPU PPGTT root diagnosis. PF requester identity during the VF's first job makes address ownership/VFID/context switching worth tracing, but hardware requester routing can also differ by transaction type.

### Two current context changes to account for

#### Clean NULL context reset: already upstream

[61e7649a1a253609769063a30018e68b970324d6](https://github.com/torvalds/linux/commit/61e7649a1a253609769063a30018e68b970324d6), Intel, March 2026, explains that another VF's modified context might remain when capturing the default image. It adds a deliberately impossible watchdog condition so GuC resets the engine before capture.

Current `xe_gt.c:377` passes `force_reset=true` for VF initial WA jobs. `xe_ring_ops.c:306` emits the watchdog and GGTT semaphore. Therefore, on recent kernels the earliest submission includes an intentional reset; seeing an engine-reset event there is not by itself the defect. Failure to complete/recover, CAT errors, or repeated reset storms are defects. A narrow diagnostic split is to trace this sequence separately from subsequent workaround instructions and fence signalling. Do not simply delete it as a fix: that reintroduces contaminated default contexts.

#### ADL indirect-context offset: pending and disputed

[c9dfd66cb91ef32f76e51f75e315c07907df2b85](https://github.com/torvalds/linux/commit/c9dfd66cb91ef32f76e51f75e315c07907df2b85), Intel, September 2025, removed explicit default-offset programming while extending indirect contexts to more engines, on the premise the hardware default was already appropriate.

Current `xe_lrc.c:1452` still leaves INDIRECT_CTX_OFFSET at its inherited value. The September 30, 2026 proposal to restore programming reports ADL Vulkan/ANGLE hangs. [Intel's initial review](https://lkml.rescloud.iu.edu/2609.3/17001.html) expected reset value 0xd to survive restore-inhibit and context capture, and requested default-LRC dumps. The [author's October 1 follow-up](https://www.mail-archive.com/dri-devel@lists.freedesktop.org/msg640961.html) then supplied an RCS default-context dump containing `0x21c8 = 0` and cited the PRM distinction: engine-context restore inhibit does not inhibit ring-context restoration. This new evidence narrows the dispute and supports checking the actual saved register rather than relying on the expected reset default. Inspect dword 0x17 in the register-state portion/default-LRC dump, respecting the dump's offsets and affected engine. This remains a proposed native-ADL context repair, not an accepted or demonstrated SR-IOV fix. The proposed `GRAPHICS_VER < 20` condition is broader than the ADL-only title; do not apply it indiscriminately.

The related [Mesa CI tracker item 7584](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7584) supplies an important limit: on April 9 the reporter initially implicated `c9dfd66cb91e`, then withdrew confidence after the parent also timed out. July 1 still reports failure on 7.1.1 despite the idledly-unit correction. That incomplete bisect does not establish the cause of the CI hang, and neither the CI hang nor the later RCS register dump establishes the cause of an SR-IOV first-job failure. Keep the measured context-register issue as a controlled hypothesis.

### CCS distinctions and avoiding unnecessary legacy ports

Compute Command Streamer (CCS engine) and Compression Control Surface (CCS metadata) are different things.

Upstream `graphics_xelp` (`xe_pci.c:57`) includes RCS0 and BCS0, not CCS0. Media engines are added separately. Its CCS hardware-enable rule starts at gfx1255 (`xe_hw_engine.c:454`), leaving ADL compute-engine support disabled.

Current strongtz snapshot adds experimental Xe_LP CCS0 only under `xe.xelp_enable_ccs=true` and then reduces GPU VA to 47 bits (`sources/strongtz-current/drivers/gpu/drm/xe/xe_pci.c:884`, `:971`). This opt-in is not an upstream module parameter. It is potentially relevant to a Windows driver expecting CCS engine resources, not automatically a cure for a Linux upstream VF probe failure.

Intel's [78b8d6d05ad0, “Move CCS enablement to engine setup RTP”](https://github.com/torvalds/linux/commit/78b8d6d05ad0) explains both design choices explicitly: Xe_LP physically has a CCS engine, but upstream i915/Xe had never enabled it because of other issues; the rule therefore starts at Xe_HP. The same commit removes manual RCU_MODE insertion into GuC ADS because registers programmed through RTP are added automatically. This supports a modern, centrally described setup/reset contract rather than copying an old manual ADS list.

i915 explicitly adds GEN12_RCU_MODE to its GuC ADS register-save list when CCS is present (`sources/i915-sriov-dkms/drivers/gpu/drm/i915/gt/uc/intel_guc_ads.c:395`). Current Xe serializes RTP-generated `hwe->reg_sr` entries into ADS (`xe_guc_ads.c:851`). Inspect the resulting list and reset domain if adding a narrowly gated Xe_LP rule; symbol-name absence is not evidence that register preservation is missing.

i915 fork's GUC_WA_RCS_CCS_SWITCHOUT bit is restricted to gfx12.70–12.74 and the fork's enable switch (`.../intel_guc.c:321`). It is absent in upstream Xe, but it is not an ADL-P workaround. Xe retains POLLCS for pre-XeHP (`xe_guc.c:202`).

i915 GGTT binder/relay condition is media13.0 plus unavailable direct stolen access (`sources/i915-sriov-dkms/drivers/gpu/drm/i915/gt/intel_gtt.c:24`), so the MTL workaround is not an ADL-P architectural gap. ADL i915 also uses direct GGTT writes. Keep MTL's binder investigation separate.

### Recommended experiments, ranked by diagnostic value

1. Pin exact host/guest driver commits and firmware; classify whether failure is during VF probe, first user submission, Windows device initialization, or later rendering. “Recent” cannot distinguish NULL-context reset changes or DKMS CCS policy. For an older Xe build, first check the two confirmed Xe_LP `Wa_18022495364` corrections (`051be4913397`, `0df99689eb79`) and the failure-specific reset fix (`1b81ed612e12`), described below. All are already in the pinned October source; reapplying them cannot explain a failure on that snapshot.
2. One VF, host driver binding first if reproducible there: instrument initial LRC/BB/ring/HWSP DMA addresses, GGTT offsets, PF-owned PTEs and VFID, GuC context ID and actual engine. Match the *first* DMAR address to these objects. Trace expected watchdog reset, context save, subsequent WA execution and completed sequence number separately. This separates mapping/ownership, context-state and interrupt failures.
3. Compare captured default LRC register values with i915 and the expected reset defaults, especially INDIRECT_CTX_OFFSET and PDP root, but do not assume either is causal. On a failed probe capture before cleanup, since a completed default-LRC file may never exist.
4. Test independent queue variants (GGTT NOP; same with scratch Xe VM; actual WA batch; reset sequence) to identify the first failing transition. Retain current Xe abstractions. These are diagnostic patch ideas, not validated fixes.
5. If failure is Windows-only after a Linux VF succeeds, evaluate the separate CCS0 exposure/enable/reset contract with 47-bit VA using the current DKMS work as a controlled comparison. Do not mix that with compression modifiers.
6. For Linux rendering after probe succeeds, investigate Mesa capability and AuxCCS support then. Kernel AuxCCS handling recently changed in March 2026: [quiesce traffic](https://github.com/torvalds/linux/commit/458b1e64e7c0594cca8515fae8996bc52619d2f6), [wait for invalidation](https://github.com/torvalds/linux/commit/cd1a516234ebb049007ce20c6b6e76936b29bade). These cannot fix a kernel module failing its initial golden-LRC job before Mesa starts.

No source review alone settles the user's ADL-P failure. The highest-value result is a narrower experiment set and rejection of unsupported broad explanations (39-bit DMA intrinsically broken; MTL binder required on ADL; Mesa causing pre-probe kernel failures).

### Authoritative Xe development tree and issue tracker follow-up

The project URL provided by the user is reachable directly via HTTPS/REST (GitLab project ID 13578), even where the web-search tool returns an internal error. The default `main` branch is a README pointer; the actual development branch is `drm-xe-next`. Verified current heads:

- `drm-xe-next`: `cf4171a20d13918e07ed01a1e01a6b546825c601`, 2026-10-01, GuC suspend-pending race fix.
- `drm-xe-fixes`: `72207463f7a4a6818a88f4ef57802b42da534301`, 2026-09-28, keep VF LMEM BAR small when no VFs enabled (dGPU resource allocation).
- `topic/xe-for-CI`: `b275cb3f07a7ab3ef3bd419db86bd42fa95dcedb`, 2026-07-09.

Source `xe-next-pci.c` fetched through the official API confirms the same relevant platform split on the latest next branch: ADL-P has SR-IOV and force-probe; MTL descriptor still lacks SR-IOV; ARL IDs select that MTL descriptor. These were not inferred solely from Torvalds' tree. The newest 100 path-scoped commits were saved to `xe-next-latest-commits.json`. The subsequently completed full-history traversal identified the accepted Xe_LP workaround correction and the separate future MTL/ARL coherency fix documented below; the initial title scan was not sufficient to assess missing fixes.

Saved issue searches include ADL, SR-IOV, sriov, emit_wa_job, Windows, Hyper-V, and IOMMU. Title search is needed because otherwise many unrelated platform logs contain SR-IOV text. A search result or same error signature is not sufficient to assign causality.

Read [work item 8354](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/8354) including discussion: this is a VF stress-test `emit_wa_job -ETIME` issue on WCL, later PTL/NVL, **not ADL-P**. It was automatically closed on 2026-09-09 after being unseen for 21 days; no identified fix is given. Item 3075 reports the same timeout during dGPU wedged testing in 2024; also not ADL-P. Item 6420 is an N100 display/boot blank-screen report, not VF passthrough. They should not be repurposed as confirmation of the user's failure.

GitLab REST `/issues/IID/notes` currently returns 401 unauthenticated, but the public web UI endpoint `/drm/xe/kernel/-/issues/IID/discussions.json` supplies the public discussion. File `xe-item-8354-discussions.json` preserves this read. No account authentication or tracker writes were performed.

Further full-discussion findings:

- [6489](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/6489): November 2025, i5-12500H ADL-P heavy-3D stutters under Xe but not i915. Intel's Jani Nikula says i915 is the supported driver and Xe/ADL-P was a development vehicle. This is a support-policy statement, not proof SR-IOV cannot work.
- [7584](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7584): Mesa CI ADL-P/RPL-U Vulkan hangs, initially reported as 6.17 to 6.19 regression. Crucially, on 2026-04-09 the reporter first implicated `c9dfd66cb91e`, then withdrew confidence after reproducing on its parent. July 1 reports persistence in 7.1.1. Thus the bisect does not prove the indirect-context-offset patch is the cause. These are bare-metal rendering failures, not VF-probe failures. The mentioned partial fix is [7596459f3c93d8d45a1bf12d4d7526b50c15baa2](https://github.com/torvalds/linux/commit/7596459f3c93d8d45a1bf12d4d7526b50c15baa2), correcting idledly unit conversion; it was already present in that still-failing 7.1.1 report.
- [7352](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7352) and [7733](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7733) really do show ADL-P RVP SR-IOV CI failures, but in the `xe-vfio-pci` FLR/reset path (NULL dereference), not initial render execution. These distinguish VFIO migration/reset plumbing from the guest renderer, and show that upstream ADL-P CI use is real despite the end-user support limitation.


### Development-tree fixes and the first Linux candidate

Complete history and patch-content comparison exposed a difference missed by the initial latest-commit title scan:

- [38631a7bce195b88814b93bf2b6d3e48c827fef2](https://gitlab.freedesktop.org/drm/xe/kernel/-/commit/38631a7bce195b88814b93bf2b6d3e48c827fef2), accepted October 1, fixes double emission of `Wa_16010904313` on Xe_LP. RCS/CCS should receive it through the indirect context; BCS/VCS/VECS through post-restore handling. It is absent from the pinned Torvalds snapshot `ce1e0223d8ad...`. This accepted fix has now been backported as implementation commit `32d16259df98d7153daaa9b8c461c2eaa0d24394`; its build/runtime boundary is recorded above.
- [d5b0bf3f37f152583a884c696cf6caa152aa7ed5](https://gitlab.freedesktop.org/drm/xe/kernel/-/commit/d5b0bf3f37f152583a884c696cf6caa152aa7ed5) adds `Wa_22016122933` for media GT 13.00 on MTL/ARL: GuC shared memory must be uncached. Its author reports extended testing on two ARL machines. It is also absent from the pinned Torvalds snapshot, and is recorded for the **later MTL/ARL phase**, with no implementation in the ADL-P patch.
- The ring-WC ordering change `136360290f31` initially appeared missing when comparing hashes, but equivalent Torvalds commit `9f83c94469ff` is already present. It must not be reapplied as a newly missing fix. Branch SHA inequality is insufficient; patch-content equivalence must be checked.

### Additional confirmed fixes found through complete commit-history traversal

The following are established changes, useful for testing what a report means by “recent.” They are already present in the pinned October 2026 upstream source; none proves the cause of a failure there.

- [051be4913397](https://github.com/torvalds/linux/commit/051be49133971076717846e2a04c746ab3476282), January 2026, fixes XeLP Wa_18022495364 programming the wrong register: CS_DEBUG_MODE1 becomes CS_DEBUG_MODE2. [0df99689eb79](https://github.com/torvalds/linux/commit/0df99689eb790bcad3ad82b38fa4ce1cbf3cffa3), April 2026, fixes the same workaround's missing engine-relative MMIO bit in MI_LOAD_REGISTER_IMM. Current `xe_lrc.c:1241` contains both corrections. These concrete errors warrant screening older reports before proposing further speculative default-context changes.
- [f2f90989ccff](https://github.com/torvalds/linux/commit/f2f90989ccff2d010472d47e4e62f7afe8ce67ff), March 2025, explicitly fixes VF workaround initialization by performing register read/modify/write on the engine with MI_MATH instead of CPU reads that fail for a VF. Thus current Xe already has a modern VF-safe workaround execution mechanism; importing i915 CPU-MMIO assumptions would regress that property.
- [e904c56ba6e0](https://github.com/torvalds/linux/commit/e904c56ba6e0d4eff5f48a70356fd5d764c2a966), February 2026, replaces VF GGTT balloon objects with direct GGTT start/size initialization. Its message says the previous scheme worked but was complicated. Missing old ballooning objects is therefore an intentional modernization, not absent virtualization support.
- [1b81ed612e12](https://github.com/torvalds/linux/commit/1b81ed612e12ea9df8c5cb6f0ddd4419fd0b8ac8), April 2026, explicitly closes ADL-P work item 7352. `xe-vfio-pci` had initialized fields needed for reset only when migration was supported, causing a NULL dereference on ADL-P's non-migratable VF. It decouples VF initialization from migration initialization. This is a confirmed ADL-P SR-IOV defect and fix, with a precisely different failure signature from an `emit_wa_job` GPU timeout.
- [d1643db3b037](https://github.com/torvalds/linux/commit/d1643db3b037b57f2af7f85c3821d6fe69c492f6), August 2026, ensures the VF calls `xe_guc_submit_enable()` and applies render/compute scheduling policy before recording default LRCs. The actual policy KLV is conditional on `CCS_INSTANCES` (`xe_guc_submit.c:356`), so this is relevant to CCS-enabled platforms/experiments, not a strong default-upstream ADL-P explanation where CCS0 is absent. [26caeae9fb48](https://github.com/torvalds/linux/commit/26caeae9fb482ec443753b4e3307e5122b60b850) explains modern GuC dual-queue/yield policy. For MTL, audit this current mechanism before proposing the old RCS_CCS_SWITCHOUT flag as a replacement. The newer scheduling policy and the older platform workaround must not be assumed semantically equivalent without checking the actual firmware contract and emitted KLVs.

The post-migration LRC re-creation fixes `c692ae39e9fd` and `f3fb5f1ebbf3` concern contexts raced by VM migration; they should not be promoted to explanations for the first cold-boot ADL-P VF probe without evidence of migration/recovery.


### Full-history acquisition and scope, completed 2026-10-02

`sources/xe-development` is a no-checkout, blob-filtered Git repository with **full commit and tree history**, not a shallow clone. It was seeded with Torvalds' full repository for efficient object transport, then fetched all official `https://gitlab.freedesktop.org/drm/xe/kernel.git` branch refs and tags. `origin` is the authoritative Xe remote; `linux-upstream` records the Torvalds transport source. Source blobs are retrieved lazily when examining patches; filtering file contents does not truncate commit ancestry.

Verification: `git rev-parse --is-shallow-repository` returned false; complete commit traversal succeeded. The snapshot has 16 official Xe branches and 226 advertised tags, 1,490,234 commits reachable from official branch refs including Linux ancestry, and 1,502,905 across all fetched refs including tags and Torvalds. Advertised exact refs are preserved in `xe-full-advertised-refs.txt`, local official branch refs in `xe-full-official-refs.txt`.

`xe-complete-path-history.tsv` indexes all 21,754 non-merge commits touching `drivers/gpu/drm/xe` across these refs, including historical rebases. Scoped searches produced 562 SR-IOV/PF/VF matches, 682 ADL/XeLP/MTL/ARL matches and 47 VF-context/IRQ matches (duplicate/cherry-picked changes are retained). `xe-development-unmerged-history.log` records the 240 commits reachable from next/fixes/CI but not the pinned Torvalds branch by identity; as the ring-barrier example shows, that does not imply 240 unique unapplied patches.

These are full-history acquisition and targeted commit-message/diff traversal, **not a claim that all Linux commits or all 21,754 Xe diffs were manually reviewed**. The source conclusions above were checked at the pinned source and the relevant authoritative development commits. This acquisition and tracker research was read-only. The separately authorized new-branch implementation/publication is recorded in the implementation section above; no tracker messages were posted.


---

## Intel statements, Mesa implications, and modern implementation boundaries

Research date: 2026-10-02. No runtime or configuration modifications. This note separates verified source statements from diagnostic inferences. Mesa source snapshot: `9046ec144bbb18a2cfbb7719adf19303b710a2c3` (main at retrieval, committed 2026-10-02 09:56 UTC). Retrieved source and API responses are under `sources/mesa/`.

### What Intel actually said about platform support

1. José Roberto de Souza's Mesa commit [31920cb60c3cf487bc29ebd1d8ad8b1825e09fab, “intel: Enable Xe KMD support by default”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/31920cb60c3cf487bc29ebd1d8ad8b1825e09fab) (2024-03-12, MR 20418) removed the build-time gate because the upstream Xe userspace ABI had stabilized, while retaining experimental status for platforms older than Lunar Lake. This is not removal of ADL/MTL support. Current `intel_device_info.c:1981-1986` still calls the Xe query backend and prints a warning for `verx10 < 200`; the warning does not itself reject the device.
2. Intel SR-IOV maintainer Michal Wajdeczko [answered on 2025-07-01](https://lkml.iu.edu/2507.0/01102.html) that pre-LNL Xe platforms were not officially supported, so SR-IOV was enabled only on SDV platforms actively tested in public CI (ADL and ATS-M). He described TGL enablement as adding `has_sriov`, but robust MTL enablement as requiring considerably more SR-IOV-specific code and prior native-mode testing. This establishes a support/testing boundary; it does not establish hardware impossibility or specify which MTL changes are unavoidable.
3. Intel's Matt Roper [reiterated on 2026-09-30](https://lkml.rescloud.iu.edu/2609.3/17001.html) that ADL force-probe support was intended for kernel developers and could lack ADL hardware workarounds. This is current, direct evidence that native Xe success should be tested before attributing every VF failure to SR-IOV.

### ADL-P: the compute engine bit is a cross-layer contract

The exact Mesa contribution to inspect is [a364f23a6cfa28e1843ef1e64dce56b4cef5a71e, “intel: Make gen12 URB space reservation dependent on compute engine presence”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/a364f23a6cfa28e1843ef1e64dce56b4cef5a71e), by José Roberto de Souza (MR 21031). Its message explains that `RCU_MODE::Compute Engine Enable` is a global control for dual-context operation and that hardware reserves URB resources when it is set. Mesa subtracts **4 KiB per L3 bank** for Gfx12.0 only when the engine query reports a compute engine. At the time, Intel said the kernel did not enable dual context on these platforms, but anticipated that this could change.

The diff sets `has_compute_engine` from the KMD's queried engine list for both Iris and ANV, then changes `intel_get_urb_config()` to subtract the reservation only when that field is true. This means a patch that silently sets the physical CCS enable bit while hiding CCS from the engine query can produce an inconsistent memory layout. Conversely, reporting CCS without valid hardware setup/context save semantics is not sufficient. This is a **source-supported diagnostic inference**, not a diagnosis of the user's unobserved failure.

The earlier Intel contribution [81d6ae31, “anv, iris: Enable compute engine with INTEL_COMPUTE_CLASS=1”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/81d6ae31) introduced opt-in compute-engine usage (MR 14395). Engine support and compute API availability must not be conflated: compute workloads can execute on a render command streamer. Do not treat “OpenCL/Vulkan compute works” as proof that a separate CCS engine works.

Suggested comparison fields across native Xe, Xe VF, and working i915 VF: physical dual-context/CCS enable state; GuC engine masks; queried render/compute engine list; GuC ADS register save/restore list; default RCS/CCS LRCs; Mesa `has_compute_engine` and computed URB size. Keep CCS = compute command streamer distinct from CCS = compression metadata.

### A proposed ADL context-image correction deserves a controlled test

Helen Koike posted “drm/xe/lrc: Restore CTX_CS_INDIRECT_CTX_OFFSET programming for ADL” on 2026-09-30, identifying [c9dfd66cb91e, “drm/xe/lrc: Allow INDIRECT_CTX for more engine classes”](https://github.com/torvalds/linux/commit/c9dfd66cb91e) as the change after which ADL IntelAngleEnd2EndTestCases sporadically returned `VK_DEVICE_LOST`. This is a proposed fix under discussion, **not a verified merged fix for SR-IOV**.

The [Intel review](https://lkml.rescloud.iu.edu/2609.3/17001.html) initially reasoned that restore-inhibit plus a context switch should preserve the hardware default and asked to inspect `default_lrc_*`, specifically dword offset `(0x16 + 1)`, and to identify affected engines. The [author's October 1 reply](https://www.mail-archive.com/dri-devel@lists.freedesktop.org/msg640961.html) distinguishes **ring context** from **engine context**, cites the TGL PRM, and provides an actual RCS default-context dump with register `0x21c8 = 0x00000000`. Her explanation is that engine restore inhibit does not inhibit ring-context restoration, so zero can be restored before default capture.

This is a sharper lead than generic speculation about bad context images: compare the exact default LRC field and the presence of c9dfd66 in the failing build. The patch's broad `< 20` guard and engine-specific defaults were also questioned; do not copy a single RCS value across every engine/platform. Importantly, **INDIRECT_CTX workaround batches are not the same feature as Xe's Indirect Ring State page**. The latter's 2024 enabling and later GuC ADS engine-state-size fix are separate topics.

The associated [item 7584 discussion](https://gitlab.freedesktop.org/drm/xe/kernel/-/work_items/7584) explicitly retracts confidence in the initial `c9dfd66` bisect after its parent also failed. The later zero-valued register dump is separate, more specific evidence; it does not rehabilitate that bisect or prove an SR-IOV root cause.

### MTL/ARL: compression architecture differs from Xe2

Intel's Mesa [MR 20322 commits](https://gitlab.freedesktop.org/mesa/mesa/-/merge_requests/20322) provide a concise platform-specific explanation:

* [6e33423a6fabca16587a3fada6b74530fb07a57b, “intel/dev: Enable AUX map on MTL”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/6e33423a6fabca16587a3fada6b74530fb07a57b), Jianxun Zhang.
* [f81579628a60de73146c9bc5b774b83a63489a4a, “intel/aux_map: Ignore format bits when using tile-4”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/f81579628a60de73146c9bc5b774b83a63489a4a), Jordan Justen: MTL uses an AUX translation map again, but Gfx12.5+ reads compression format from surface state and ignores format bits in AUX-map metadata. Tile4 replaces Y tiling for this path.
* [5df50292d60dd77f38a19f5b3f7568a7a83d7cd1, “intel/isl: Disable CCS on MTL until B0 (Wa_14017353530)”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/5df50292d60dd77f38a19f5b3f7568a7a83d7cd1): an early-stepping workaround, not a blanket statement that production MTL cannot compress.

Consequently, Xe2 SR-IOV FlatCCS support must not be assumed to solve MTL AUX translation. ADL also has an AUX-map path, so AUX-map existence alone does not explain why MTL needs more work. The relevant MTL contract includes per-context AUX table state, per-engine invalidation, media/render relationships, and the real architecture's cache attributes. Whether any particular missing item causes the user's failure still requires tracing.

Current Mesa `genX_init_state.c` programs AUX table base registers from userspace when `has_aux_map`; `genX_cmd_buffer.c` invalidates per-engine AUX caches. These are existing userspace mechanisms to preserve, not reasons to transplant old i915 memory management wholesale. Source snapshot links: [initial state](https://gitlab.freedesktop.org/mesa/mesa/-/blob/9046ec144bbb18a2cfbb7719adf19303b710a2c3/src/intel/vulkan/genX_init_state.c), [command buffers](https://gitlab.freedesktop.org/mesa/mesa/-/blob/9046ec144bbb18a2cfbb7719adf19303b710a2c3/src/intel/vulkan/genX_cmd_buffer.c).

### PAT, CPU coherency, and scanout are already modern Xe contracts

[500e037661e369927aeee0c1c5cb41fb8b946d4b, “intel: Add PAT entries for gfx12 and newer”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/500e037661e369927aeee0c1c5cb41fb8b946d4b), José Roberto de Souza, explicitly states that Xe requires PAT selection on every supported platform. [29d4d2640677d3cba4fa32acbe4c6e1109999e1a](https://gitlab.freedesktop.org/mesa/mesa/-/commit/29d4d2640677d3cba4fa32acbe4c6e1109999e1a) explains keeping PAT, CPU mmap mode, and BO coherency requirements together in platform information. This favors using Xe's existing BO + VM_BIND/PAT model and correctly adapting platform tables over importing i915 GEM caching APIs.

[0d668f50dc88f06100513abe2ef0fe379ed0ed27, “intel: Update MTL scanout PAT entry”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/0d668f50dc88f06100513abe2ef0fe379ed0ed27) changed the scanout policy because preceding integrated GPUs had noncoherent GT and display caches and Intel had not established that MTL changed this. This directly supports testing scanout/composition separately from offscreen render success. It does not prove that a Windows guest DWM defect is a PAT defect.

### Discriminating tests, in order

1. Establish native Xe and headless VF kernel submission correctness with the same kernel/firmware versions, by engine. If the guest cannot reach driver initialization or the first tiny submission, Mesa compression tuning is downstream of the failure.
2. Query engines/topology/configuration through the guest Xe uAPI. Current Mesa's Xe device-info backend refuses missing geometry-DSS or EU masks; the experimental warning itself is not a blocker. Source [xe/intel_device_info.c](https://gitlab.freedesktop.org/mesa/mesa/-/blob/9046ec144bbb18a2cfbb7719adf19303b710a2c3/src/intel/dev/xe/intel_device_info.c).
3. Record physical enable state versus published engine list and URB reservation. Test RCS-only scheduling separately from CCS opt-in, with known correspondence between PF and VF assumptions.
4. Compare RCS default LRC `0x21c8` and affected source ancestry before trying the September context fix; capture engine-specific default context files.
5. Once headless execution succeeds, separate linear/uncompressed BO copy, tiled render, compressed render, and scanout/composition. Compression disable switches in Linux Mesa can be diagnostic controls, but do not fix a Windows guest's proprietary userspace implementation.
6. For MTL/ARL, audit AUX table save/restore and invalidation and PAT/coherency with actual platform data; do not rename AUX-map platforms as FlatCCS-capable to reuse Xe2 code.

There is no primary evidence in this research establishing one universal “Gen12 Xe Mesa incompatibility,” nor proof that indirect ring state, GPU page-table updates, or FlatCCS is intrinsically required to start an ADL VF. Treat those as separately measurable contracts.

---

## MTL/ARL i915 versus Xe source investigation

Inspected 2026-10-02. This is a source/history study, not hardware validation.

### Source identities and the most useful new evidence

- User fork default `master`: `168f20e718076607aa4e16f9852724548961e751`, March 28 cleanpath with the VF coalescing experiment reverted.
- User fork `upstream-mtl-cleanpath`: `c3ceb2e9eec13709120f6216229f7ef537177427`, includes later upstream merges.
- User fork `upstream-mtl-pf-debug-trace`: `cc36279855fcf688f6ada2dc3e79da87e830c5d0`, June 18, newer than default master and contains recorded live experiments.
- Mainline shared checkout: `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`.

Do not treat the default branch's March README as the end of the investigation. [The June trace results](https://github.com/peigongdsd/i915-sriov-dkms/blob/cc36279855fcf688f6ada2dc3e79da87e830c5d0/XE_MTL_SRIOV_TRACE_RESULTS_20260618.md) are substantially more informative than commit titles. They document a Windows MTL guest that runs accelerated graphics but retains composition/video glitches. They do not document a wholly nonfunctional Windows VF.

The [April investigation](https://github.com/peigongdsd/i915-sriov-dkms/blob/cc36279855fcf688f6ada2dc3e79da87e830c5d0/MTL_XE_SRIOV_GLITCH_INVESTIGATION.md) describes stable artifacts around taskbar/Explorer menus and two PR #415 repros: Firefox video and WinUI3 ContentIslands. It reports Linux render-node use without the same artifacts. That is useful reporter evidence, not proof that every Linux graphics/video path or every ARL SKU works.

June capture details:

- PF `00:02.0` Xe, VF1 `00:02.1` vfio-pci; 2 GiB VF GGTT.
- 6,061 GT0 GGTT updates covering 555,062 PTEs; zero recorded service, MMIO or GGTT errors. GT1 had handshakes/runtime queries but no GGTT-update requests.
- Sampled shadow/live PTE entries 0–31 matched. This sample cannot prove every corrupt surface mapping correct.
- 507 invalidation requests on each GT, all 1,014 sends signaled. No recorded timeout/reset/page fault/wedge in that repro.
- Guest GGTT PAT histogram: PAT0 2,048; PAT1 0; PAT2 552,679; PAT3 335.
- `pat_sw_config` matched the expected software table; this alone does not verify all hardware registers or effective cache policy.
- Media-GT LNCFCMOCS reads were all zero on two samples. This needs correct register/steering/forcewake interpretation and a working-i915 comparison before calling it faulty programming.
- Boot warnings came from **host-side Xe VF autoprobe** before vfio binding. Disable VF autoprobe before creating VFs for clean experiments. They are a separate event from runtime Windows corruption.
- Later Linux harness host freeze occurred during generated EROFS image construction **before QEMU/VFIO attach**. It is not evidence of Xe VF execution failure.

The note's statements about experiments not changing artifact shape are reported history. A commit's presence by itself is not proof it ran, its GuC gates activated, or its results were recorded.

### Phase comparison

Paths/line numbers below refer to fork `168f20e` unless explicitly marked mainline.

| Property | Working i915 design | Xe baseline / current fork | Consequence |
|---|---|---|---|
| Platform gate | `i915_pci.c:771–791`, MTL descriptor enables SR-IOV; ARL IDs reuse it at 884 | Mainline `xe_pci.c:384–395` has `require_force_probe` and no `has_sriov` for MTL. Fork `xe_pci.c:327–334` adds it | Flag is necessary, not a complete implementation or Intel support claim |
| GGTT resource | `intel_iov_provisioning.c:632–639` pushes a shared range to graphics and media GuCs | `xe_gt_sriov_pf_config.c:427–436` already does the same; media full-config encoding takes primary GGTT at 332–343 | Multi-GT GGTT provisioning is already present; do not reimplement it blindly |
| Per-GT resources | GuC contexts/doorbells/scheduling/thresholds | Xe retains per-GT resource allocation and KLV transport; validation uses primary GGTT at 2455–2482 | Compare **actually pushed incremental KLVs**, not only saved/full blobs |
| MTL VF GGTT transport | `intel_iov_ggtt.c:173–263`: coalesced MMIO before CT, larger relay packets after CT | Fork `xe_ggtt.c:235–325`: explicit MMIO bootstrap and relay once CT/submission ready; PF service added in `xe_gt_sriov_pf_service.c` | Preserve external VF/PF message compatibility; sender coalescing is an optimization, not required architecture |
| Physical GGTT writes | `intel_gtt.c:24–29`: binder only if direct stolen access unavailable and media IP13.0. `intel_ggtt.c:1393–1409`: direct GSM when firmware permits; CPU vs binder selected at 2127–2131 | Fork `xe_ggtt.c:117–150`: direct GSM path on host root tile if pcode allows; otherwise BAR. CPU worker applies shadow PTEs | Direct safe CPU path is legitimate. An engine path is a fallback where the hardware workaround needs it, not a mandatory i915 transplant |
| PF completion | i915 dispatches through its GGTT update backend | Fork `xe_ggtt.c:1697–1719` queues shadow apply and returns count before physical apply; invalidation is deferred again | Explicitly define reply/update/invalidate completion ordering. This remains an engineering invariant even though synchronous experiments did not fix artifacts |
| GSC/PXP | i915 knows its own SR-IOV firmware lifecycle | Fork `xe_pci_sriov.c:88–119` drains GSC work, takes GSC forcewake, stops GSC and suspends PXP before enabling VFs; resumes on disable | Use Xe firmware lifecycle/ownership, with unwind, rather than copying i915 internals |
| Runtime values | i915 `intel_iov_service.c:44–62` exposes 17 MTL register values | Fork cleanpath `xe_gt_sriov_pf_service.c:59–70` exposes ten in its 12.70 table; experimental runtime mirror exists | Differences exist, but June service results show no unsupported requests during repro. Compare values/sourcing as a bounded secondary check |
| GPU page tables | i915 WC page-table mapping for MTL (`intel_gtt.c:106–137`) | Xe already WC maps Xe_LPG+ `XE_BO_FLAG_PAGETABLE` (`xe_bo.c:520–529`) | Porting this i915 WC workaround is redundant. Windows builds its own PPGTTs, outside PF Xe BO policy |

### Corrections to earlier cache hypotheses

#### Declared MTL PAT and MOCS tables already match

i915 PAT indices 0–4 (`intel_gtt.c:505–535`) and Xe's `xelpg_pat_table` (`xe_pat.c:81–87`) encode the same policies: WB/no coherency, WT/no coherency, UC/no coherency, WB/one-way, WB/two-way. Xe internal cache-level mapping is UC→2, WT→1, WB→3 (`xe_pat.c:497–503`).

i915 `mtl_mocs_table` (`intel_mocs.c:382–430`) and Xe `mtl_mocs_desc` (`xe_mocs.c:449–498`) also have the same declared entries. A wholesale table import therefore has no explanatory value. Hardware programming and guest selection can still differ.

The apparent reversed Xe `xelpg_pat_ops` routing (`xe_pat.c:351–358`) deserves awareness, not a root-cause claim: graphics uses plain writes while media uses the MCR helper, opposite the adjacent comment/dump routing and i915. However mainline `xe_gt_mcr_multicast_write()` (`xe_gt_mcr.c:880–894`) itself only takes the MCR lock, performs the same MMIO write, and unlocks; multicast is the default state. During serialized initialization this can produce the same hardware writes. This is present in mainline too, not introduced by the SR-IOV fork.

#### GGTT PAT counts do not identify Windows surface policy

The June note inferred that most GGTT entries use UC because they select PAT2. The histogram proves the selected GGTT PAT index, but it does not prove that the corrupt Windows surface is uncached:

1. A Windows application/composition surface is normally accessed using its process GPU page tables. Those PPGTT mappings are not the PF's GGTT shadow.
2. MTL MOCS entries 1–15 in these tables use `IG_PAT` (ignore PAT), and include cached modes. Command/surface MOCS selection matters alongside page-table PAT and coherency.
3. The same physical page may have several GPU/CPU aliases. Mutating one GGTT PAT entry does not establish consistent policy across those aliases.

Thus do not conclude that PAT3 is wrong because it is rare, or that changing those 335 GGTT PTEs to PAT2 should fix Windows. A narrowly scoped cache experiment must identify the corrupt surface and account for its PPGTT/MOCS/CPU aliases. A temporary consistent conservative surface policy can be a diagnostic, not a proposed final fix.

#### Flat CCS is not the obvious MTL mechanism

MTL's descriptor has no `has_flat_ccs`; `xe_device.c:783–804` runtime flat-CCS probing is for graphics >=20. `xe_sriov_vf_ccs.c` migration logic is therefore not a demonstrated active path here. MTL can still have auxiliary-surface compression and synchronization issues; do not confuse those with the modern flat-CCS VF migration mechanism.

#### Host display code is not automatically Windows VF code

Host Xe scanout/domain/flush/PAT changes often do not touch a Windows VF's private surface allocations. Linux Xe VF `vf_update_device_info()` likewise is not the Windows driver's capability source. For Windows compare the PCI/BAR contract, PF/GuC configuration and runtime replies, PF-programmed hardware, and guest allocation/command choices.

### Experiments already represented in history

| Experiment | Commits | Evidence boundary |
|---|---|---|
| MTL enable + GSC/PXP | `0bbf46a`, `e74cb07` | Foundational bring-up, retained |
| MMIO bootstrap then CT relay | `ec0f9b9`, `1dceebf`, `996c7e6`, `0a3545f` | Retained; June live protocol counters show traffic successfully processed |
| Shadow plus staged apply | `4f7a59b`, `13ce808`, `4cee2b9` | Retained |
| Direct GSM host access | `b1936f5` | Retained; matches real hardware workaround |
| i915 VF coalescing | `d713541`; revert `168f20e` | Default cleanpath intentionally removed it; no reason to revive for architectural parity |
| Synchronous apply | `89bdb7f`, `6e27a95`; reverts `9374be0`, `a229c16`; later `9abcb52` | Reported not to change artifact shape; keep completion audit separate from artifact hypothesis |
| Engine/bind queue approach | `e28ee35`, `244bdbc`, `d886462`, `a917143`, `6485483`; CPU `0b67ed3` | Existing attempts must be read before repeating them |
| GuC invalidation | `42502ce`; revert `395bdee` | Cleanpath notes report boot failures; avoid blocking waits on a G2H worker that must also process completion |
| Runtime mirror / PM | `1a4aa7b`; drop `c89f9e1`; mirror `90befe5` | Exact media forcewake/value sourcing not identical to i915; no late unsupported requests in June |
| i915 MTL RCS/CCS GuC WA | `0526c5a`, validation `d4005e1` | Adds `GUC_WA_RCS_CCS_SWITCHOUT`, two ADS KLVs for 12.70–12.74, firmware >=70.10.0. Verify running firmware and emitted KLVs before treating as ruled out |
| Host display/page-table policy tracing | `01d3531`, `a342f77`, `5a03129`, `38100d9`, `57eceee` | Guest surface applicability must be shown |
| Latest bounded observation | `ce2699a`, `2c46b49`, `cc36279` | Common incremental-KLV hook and per-PAT/history rings solve earlier incomplete capture, but the last change's new boot results are not in the note |

### Intel primary-source messages

1. [Intel LTS runtime-register extension c031d1a](https://github.com/intel/linux-intel-lts/commit/c031d1a2aaea6d9804a6a12af67b424642171836): actually adds `0x10100c` and `0x389140` to the already existing MTL list. It is evidence of a platform-specific runtime contract; its short message does not prove any one missing value causes current corruption.
2. [Mainline c08c364: bypass MTL BAR stolen access](https://github.com/torvalds/linux/commit/c08c364102d07288610734de34111a666e730ae7): Intel explicitly identifies system hangs from MTL stolen BAR access, firmware-enabled direct DSM/GSM as the host workaround, and excludes guests from that direct physical-memory shortcut. Pcode `0x138914 == 1` is the permission check.
3. [Intel follow-up: disable the binder](https://www.mail-archive.com/intel-gfx%40lists.freedesktop.org/msg333305.html): once direct GSM works, Intel does not require MI_UPDATE_GTT; the message notes dependency/async/hang risks, retains binder for VMs, and leaves generic engine updates as a possible optimization. This directly supports preserving hardware semantics without copying old binder machinery.
4. [Intel LTS bcf6f14318c852a7319cf3ebeb0978432e314c0e](https://github.com/intel/linux-intel-lts/commit/bcf6f14318c852a7319cf3ebeb0978432e314c0e), now retrieved and verified through the GitHub API, documents unstable direct MTL **VF** GGTT access and removal of its GGTT BAR access. The VF must request PF updates through MMIO and CTB relay. Its `Wa_22018453856` replaces MTL VF insert-page/insert-entries callbacks with relay operations and defines action `0x102` including duplicate/replicate modes. This establishes a hardware-driven external protocol requirement for Xe compatibility. It does not require reproducing i915's internal buffer/coalescing design.

These Intel commits concern different actors: the MTL **VF** uses relay because its direct access is restricted; the **PF** may apply those requests through firmware-authorized direct GSM. A safe direct PF backend and an obligatory VF-to-PF relay are compatible. Preserve both sides of that contract when simplifying the implementation. The original commit response and patch are saved in `evidence/intel-lts-bcf6f143.json`.

### Recommended Xe-native architecture and next experiments

1. Finish ADL-P separately; do not put MTL binder/dual-GT/GSC work into that platform's fixes. ADL-P provides a simpler test of the shared VF/PF ABI.
2. Rebase the minimum MTL bring-up on current Xe, retaining gated SR-IOV enablement, correct power/firmware lifecycle, public MMIO/relay protocol support, and safe GGTT writes. Reuse Xe's existing provisioning, locks, workqueues and invalidation infrastructure. Modern mainline already models shared tile GGTT plus per-GT GuC state.
3. Direct GSM is the simplest PF backend **when the documented firmware permission is present**. On machines without it, use an engine-assisted backend only after implementing proper bootstrap and completion guarantees. Mainline `xe_migrate_update_pgtables()` (`xe_migrate.c:2051–2081`) offers native scheduling/dma-fence concepts for **PPGTT**; it is not a drop-in safe GGTT update operation. Validate the addressing/MI opcode/invalidation requirements instead of mechanically calling it.
4. Do not acknowledge a semantically complete VF update before physical writes and required invalidation are complete unless ABI ordering explicitly allows it. An asynchronous implementation should attach an actual completion fence and defer the response off the G2H completion worker. Test early MMIO without CT, steady CT, timeout, overlapping updates, and FLR teardown. This is correctness work, not a claim to cure the recorded artifact.
5. Use the June bounded traces, with one exact Windows driver/repro and working i915 PF as control. Capture **all** incremental KLVs on both GTs, GuC version/ADS workaround payload, runtime values, PAT hardware readback, MOCS hardware state and relevant workaround registers. Avoid trace-induced performance perturbation.
6. Reproduce rendering-to-copy-to-video-to-composition sharing with a minimal Windows sample. Capture output before presentation to distinguish GPU producer corruption from display/capture/compositor transfer. Correlate one failing allocation with its guest GPUVA, PPGTT PAT, actual surface/command MOCS, auxiliary metadata and synchronization operations. This is substantially more discriminating than another global GGTT change.
7. Use the host driver's actual PF policy delta to design one-at-a-time experiments. Declared PAT/MOCS table equality and existing Xe WC page-table mapping mean those are not missing features to import.
8. ARL: record actual PCI ID, GMD graphics/media versions and firmware. Current shared descriptor does not imply every ARL SKU/firmware pairing identical to MTL. Gate workarounds by affected IP/stepping, then validate ARL after MTL, not by a marketing-name substitution.

### Windows-driver reverse engineering

The source differences above stand independently of binary analysis. The newly authorized Windows investigation now has a concrete separate target: the nested-Hyper-V environment classifier. Both official packages have been extracted and their isolated classifier behavior is reported near the beginning of this report. That finding must not be retroactively presented as a diagnosis of MTL composition defects. For the latter, match the failing guest's exact package/module, identify the surface or synchronization transition, and decode GuC/MMIO messages against the open ABI before attributing an opaque private-driver policy. INF matching and package age alone do not establish the runtime path.

No driver code was changed, built, loaded or tested on hardware during this source study.

---

## Nested Hyper-V, Windows VF startup, and the CPUID contract

Verified against primary sources on 2026-10-02. This chapter records published runtime observations and protocol definitions. The independent classifier emulation near the beginning of this report adds version-specific binary evidence; neither study constitutes a local Windows/GPU runtime reproduction.

### Intel acknowledges a guest-driver classification defect

Intel's [KB 000102878](https://www.intel.com/content/www/us/en/support/articles/000102878/graphics.html) explicitly attributes a VFIO SR-IOV Code 43 failure to treating nested Hyper-V as a native Hyper-V host. Its published resolution still says Intel is investigating; the page identifies driver 32.0.101.8531 and Core Ultra 7 265H. This is not simply a conjecture that nested EPT or IOMMU is broken.

[#1394](https://github.com/IGCIT/Intel-GPU-Community-Issue-Tracker-IGCIT/issues/1394) was closed June 30 when Intel redirected updates to that article, not when a fixed driver was announced. The retrieved API reports `state_reason=completed`, which is misleading if interpreted as evidence of remediation. A July 27 independent lab report identifies `igdkmdn64.sys` 32.0.101.8826, SHA-256 `AECB6FDEB393BA9F92945FF1507D5FB41996E0EB7EE0A575D5AE8E8C14B87B80`, and ARL VF device 7D67. It reports an earlier skipped state transition, leaving a later StartDevice guard to return `0xC000000D`, with DxgKrnl Event 549 and Code 43. The report claims that correcting the earlier transition enabled startup on Windows 11 and Server 2025. Those experiments are the reporter's evidence, not independently repeated here. Intel tracking number: `14027918034`.

The separate B50 [#1468](https://github.com/IGCIT/Intel-GPU-Community-Issue-Tracker-IGCIT/issues/1468) concerns startup regressions reported without nested virtualization. Therefore Code 43 alone cannot identify the nested defect or justify applying its proposed correction to all startup failures.

### Exactly which Hyper-V bits mean what

Microsoft's [feature discovery specification](https://learn.microsoft.com/en-us/virtualization/hyper-v-on-windows/tlfs/feature-discovery) and [partition privilege mask](https://learn.microsoft.com/en-us/virtualization/hyper-v-on-windows/tlfs/datatypes/hv_partition_privilege_mask) define:

| CPUID field | Meaning relevant to this investigation |
|---|---|
| `1:ECX[31]` | Hypervisor present |
| `0x40000000` | Maximum supported hypervisor leaf and diagnostic vendor string |
| `0x40000001:EAX == 0x31237648` | `Hv#1` interface semantics |
| `0x40000003:EBX[0]` | `CreatePartitions` privilege |
| `0x40000003:EBX[12]` | `CpuManagement` privilege |
| `0x40000004:EAX[12]` | Hypervisor is nested within a Hyper-V partition |
| `0x40000006:EAX[13:10]` | Current guest hypervisor nesting level; zero when non-nested |

Microsoft recommends using the interface signature for compatibility, rather than the vendor string. A privilege saying this Windows partition controls its immediate hypervisor's CPUs does not establish that its PCI device is a physical function. The nested indicator provides additional topology information; it must be read only after validating the available leaves and interface.

### Why hypervisor flags are not interchangeable

[QEMU's own Hyper-V documentation](https://www.qemu.org/docs/master/system/i386/hyperv.html) says enabling Hyper-V enlightenments changes the exposed identification to Hyper-V while moving KVM identification to leaves `0x40000100..0x40000101`. Consequently, `Microsoft Hv` is not evidence that Windows' own hypervisor has started. `hv-vendor-id` changes only the identification string, and setting it alone does not enable Hyper-V features. `hv-evmcs` is a performance/virtualization interface between KVM and nested Hyper-V; it is not a VF startup correction.

This investigation must distinguish:

1. L0 KVM permits nesting (`kvm_intel.nested=Y`). This is a host capability.
2. The guest CPU exposes VMX. This allows a guest hypervisor to start but does not prove it started.
3. Windows launches Hyper-V, including when VBS/Memory Integrity or Virtual Machine Platform causes that launch. Its graphics driver runs in the root partition of that immediate hypervisor while its GPU can remain an outer-assigned VF.
4. A further L2 guest actually runs. The reported graphics defect arises at Windows VF startup; no L2 GPU assignment is required to reproduce it.
5. A virtual IOMMU is exposed and the VF is passed onward into L2. That is a separate device-assignment topology with separate translation requirements.

### Proposed diagnostic matrix

Hold PF driver build, GuC firmware, VF count/resources, guest driver hash, VM machine type, PCI topology/BAR layout, and RAM fixed. Use an isolated guest snapshot. Record actual guest CPUID output and Windows hypervisor/VBS state after each cold start.

| Trial | VMX exposed | Windows Hyper-V/VBS actually running | L2 workload | Purpose |
|---|---|---|---|---|
| A | No | No | No | Establish ordinary VF startup baseline |
| B | Yes | No | No | Test VMX exposure separately from guest Hyper-V execution |
| C | Yes | Yes | No | Isolate immediate root-partition classification |
| D | Yes | Yes | Yes, CPU-only | Test nested activity after successful C |
| E | Yes | Yes | GPU assigned to L2 | Separate future vIOMMU/device reassignment test |

For each trial capture CPUID leaves 1, `0x40000000` through `0x40000006`, and outer KVM leaf range if present; PnP problem code; exact DxgKrnl status; PF GuC/VF lifecycle messages; whether PF/VF communication begins before failure. A result where A/B work, C fails with `STATUS_INVALID_PARAMETER`, and GPU communication does not newly fail strongly prioritizes the Windows branch over Xe memory-management changes. A/B failure demands ordinary VF initialization debugging first.

### What a correction should preserve

The most focused candidate is in the Windows driver's **earlier environment classification/state-resolution logic**, accounting for a passed-through VF in a nested root partition. Preserve the later validity checks and error paths. This is the direction supported by the public lab report and Intel's issue description. The report's emulation identifies the environment fields in 7092 and 9033, and conditionally reproduces a 9033 resource rejection. The actual guest resource layout and equivalence to the older reported startup guard remain to be established.

Do not treat hiding VMX, turning off guest Hyper-V, removing VBS, or globally falsifying root-partition privileges as the product fix. Those can be controlled discriminators, but they change guest capabilities. A top-level QEMU vendor string also may not describe the CPUID interface ultimately returned by an active L1 Hyper-V to its own Windows root partition; confirm what the driver actually observes.

The cross-layer implication is useful for the original Xe study: an identical nested-only failure on a known-good i915 PF and an experimental Xe PF can be explained by a shared Windows guest-driver defect. It would not prove both PF implementations have the same missing hardware workaround. Conversely, fixing this Windows branch does not establish MTL/ARL Xe PF correctness for rendering, composition, reset, or multi-VF isolation.


## ADL-P Windows Code 43: supplied-log follow-up

2026-10-02. MTL work is paused at the user's request. This note analyzes the supplied 82-line host log; the assistant has not reproduced this machine's failure. The exact running driver commit, Windows driver version, Windows hypervisor state and complete host log were not supplied with that excerpt.

**Latest evidence supersedes this historical CCS test:** three valid reuploaded captures all show CCS enabled and a loaded source version matching the timestamp-patched build. They establish host PF DMA/CAT faults and GT resets. The user confirms unchanged settings and persistent Windows Code 43 across both VM attempts. Read [the current capture analysis](adlp-reuploaded-capture-analysis.md) and [the isolated ADL-P context experiment](adlp-indirect-offset-experiment.md). The CCS steps below document the earlier diagnosis; repeating that toggle is not the next test.

### First actionable finding

The active ADL-P PF driver is **Xe**, but the boot command line contains `i915.xelp_enable_ccs=1`. At 8.725 seconds the log explicitly says i915 ignored that unknown parameter. This cannot enable Xe's independent parameter. Current DKMS defaults `xe.xelp_enable_ccs` to false, and its September 16 change recommends `xe.xelp_enable_ccs=1` for Windows guest problems on Xe_LP, including ADL.

The absence of Xe's `Enabling experimental CCS0 on Xe_LP` message in this excerpt supports checking CCS first. It does not replace reading the effective parameter: a separate modprobe configuration could set it even when the boot command line does not.

Sources: [current base README](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/README.md#L55), [maintainer explanation, PR 484](https://github.com/strongtz/i915-sriov-dkms/pull/484), [parameter definition](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/drivers/gpu/drm/xe/xe_module.c#L88), and [existing implementation](https://github.com/strongtz/i915-sriov-dkms/commit/2024842930ebacf088929be43af0ce79b33cf0e7).

This is a strong configuration lead, **not yet a demonstrated explanation of Code 43**. The option is a DKMS extension, not a stock upstream Xe parameter. It adds CCS0 to the engine mask, enables its RCU_MODE programming through existing RTP, and selects the associated 47-bit GPU virtual-address configuration. This is not an IOMMU DMA-width change. The current published ADL-P branch already contains it; no new driver patch is needed to try the correct option.

The subsequently supplied `hardware-configuration.nix` confirms that Xe is loaded in the initrd and `pkgs.xe-sriov` is selected. Its `options xe` line has no `xelp_enable_ccs` override; the boot argument at line 147 targets i915. It also configures `kvm_intel nested=0`. These are configuration facts, not proof of the running module values; check `/sys/module/kvm_intel/parameters/nested` if nested virtualization remains in question. The exact implementation of `pkgs.xe-sriov` is outside this file, so it does not establish the source commit or whether the timestamp backport is in the installed module.

A corrected local copy changes only the CCS comment and the one boot argument. `nix-instantiate --parse` passed. No NixOS build or activation was performed. The small [configuration patch](patches/adlp/adlp-xe-ccs.patch) is published with this note; the full machine-specific configuration is retained locally, not in the public repository.

### What the supplied log establishes

| Host time | Evidence | Interpretation |
|---|---|---|
| 2.599 s | ADL-P PCI `8086:46a6`, PF mode, D0 display stepping | The ADL-P PF probes under the DKMS Xe module. The banner alone does not identify the exact built commit. |
| 2.634 s | ADL-P GuC `70.49.4` | Actual firmware identity for this PF. DG2's later `70.53.0` belongs to a different GPU. |
| 8.995–9.146 s | VF1: 2 GiB GGTT, 32768 context IDs, 128 doorbells; one VF enabled | Provisioning completed; this does not establish successful Windows driver initialization. |
| 93.335 s | RCS reset, GuC ID 57, timed-out `.org.gnome.Naut` job, coredump created | A host userspace render queue hung. This is not a Linux VF's initial `emit_wa_job` failure and does not identify a Windows guest context. |
| 107.943 and 108.072 s | `VF1 FLR` | GuC reported VF function-level resets. These messages do not say FLR failed, and do not identify who requested it. |

The RCS reset state `0x3` is the host queue's REGISTERED and ENABLED bits. The large sequence number `4294967169` is Xe's intentional initial fence sequence (`-127` as unsigned), not evidence of sequence-number corruption. The reset handler obtains this queue from the Linux host's GuC submission registry. A shared-engine interaction remains possible, but the log cannot prove that Windows caused the host hang or that the host hang caused Code 43.

The two migration-disabled notices are feature limitations, not startup failures. One is about memory-based interrupts; the other requires GuC 70.54 for migration. Neither establishes that this ADL-P guest needs a GuC upgrade to start. Keep firmware fixed for the first configuration comparison.

The excerpt appears filtered. The absence of DMAR/IOMMU or VFIO errors here does not establish their absence from the full boot log. Host timestamps also do not establish when Windows displayed Code 43; record VM start and failure times for the next run.

### Ordered retest

#### 1. Save the current failure before rebooting

From the repository root on the ADL-P host, using the current branch's collector:

```sh
sudo bash docs/xe-sriov/collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-before-ccs
```

It creates `/tmp/adlp-before-ccs.tar.gz`. The supplied log explicitly identifies `/sys/class/drm/card0/device/devcoredump/data`; the collector matches the PCI device rather than assuming card numbering. Capture immediately if the dump still exists: these dumps expire. A missing expired dump is not proof there was no hang. The updated collector includes the effective `xelp_enable_ccs` value and the saved CCS context image if available.

#### 2. Check and, if necessary, correct the Xe option

```sh
cat /sys/module/xe/parameters/xelp_enable_ccs
```

- `N`: test the correct Xe option below.
- `Y`: this setting is already active; the mistyped boot argument is not the explanation by itself. Retain that result and continue with Windows status/full host diagnostics.
- Missing file: identify the loaded module build before assuming this DKMS extension exists in it.

In the host's existing NixOS `boot.kernelParams`, replace the attempted `i915.xelp_enable_ccs=1` with:

```nix
"xe.xelp_enable_ccs=1"
```

Preserve the existing IOMMU, force-probe, VF-count and unrelated settings. Build the boot configuration using the machine's normal NixOS workflow and reboot the host. This parameter is read-only after module initialization; do not try to write `Y` to sysfs or unload the active display driver. Use the same patched driver build and GuC firmware for this comparison.

After boot, verify:

```sh
cat /sys/module/xe/parameters/xelp_enable_ccs
sudo journalctl -k -b --no-pager | rg 'Enabling experimental CCS0|Restricting VA bits|alderlake_p|Using GuC firmware|Enabled .* VFs'
```

Expect `Y` and the ADL-P CCS-enable message. If the PF now fails probing with a CCS `emit_wa_job` timeout, stop this test and save its first error; do not interpret failure to reach the VM as Windows Code 43.

Cold-start the same Windows VM with one VF. Keep its Intel driver, PCI topology, RAM and Hyper-V settings unchanged in this first comparison, so only the Xe CCS configuration changes. Keep a previous boot generation available because this option is experimental. A clean host boot also prevents the earlier PF hang from contaminating the next result.

#### 3. Record the first new result

Run the host collector immediately after either successful guest startup or the first failure, using a fresh output path:

```sh
sudo bash docs/xe-sriov/collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-after-ccs
```

Record whether the PF hung before the guest was started, while Windows was loading the GPU driver, or only afterwards. If the host hangs again without any guest running, native ADL-P Xe stability needs its own coredump analysis. A host-only timestamp fix remains relevant to that path, but its existence does not establish a cure.

For libvirt, also retain the exact active VM definition (`virsh dumpxml <domain>`) and the VM's startup log. Do not infer nested Hyper-V merely from QEMU's Hyper-V enlightenment flags.

Inside Windows, run these read-only commands in PowerShell and retain their output:

```powershell
Get-CimInstance Win32_PnPSignedDriver |
  Where-Object DeviceClass -eq 'DISPLAY' |
  Format-List DeviceName, DeviceID, DriverVersion, DriverDate, InfName

$intelDisplay = Get-PnpDevice -Class Display -PresentOnly |
  Where-Object InstanceId -like 'PCI\VEN_8086*'
$intelDisplay | Format-List Status, FriendlyName, InstanceId, Problem
foreach ($gpu in $intelDisplay) {
  Get-PnpDeviceProperty -InstanceId $gpu.InstanceId -KeyName `
    'DEVPKEY_Device_ProblemCode', 'DEVPKEY_Device_ProblemStatus' |
    Format-List KeyName, Data
}

bcdedit /enum '{current}'
Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard |
  Format-List VirtualizationBasedSecurityStatus, SecurityServicesConfigured, SecurityServicesRunning
```

Also save the Windows System event log and any available DxgKrnl startup-error event, including the full XML/status and timestamp. `DEVPKEY_Device_ProblemStatus` supplies an NTSTATUS in addition to generic Code 43; see [Microsoft's property definition](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/devpkey-device-problemstatus). Decimal 3221225485 corresponds to `0xC000000D` (`STATUS_INVALID_PARAMETER`), but that status is still not unique to the nested-classifier defect. Absence of one particular event number is not proof of success.

#### 4. If CCS is active and Code 43 persists, separate the nested case

The supplied host configuration sets `nested=0`, so this is secondary to the CCS correction; do not enable nesting for the first retest. If the effective host/VM configuration nevertheless allows Windows Hyper-V/VBS to run, make a separate controlled boot with Windows' hypervisor launch disabled. In an elevated Windows terminal, first retain the current setting and then use:

```powershell
bcdedit /enum '{current}'
bcdedit /set '{current}' hypervisorlaunchtype off
```

Restart Windows fully; for this comparison do not resume a saved VM state or hibernation image. WSL2, Hyper-V guests and VBS protections will be unavailable during this diagnostic boot. Restore the recorded prior value afterwards: typically `bcdedit /set '{current}' hypervisorlaunchtype auto`, or `bcdedit /deletevalue '{current}' hypervisorlaunchtype` if the setting was originally absent. See [Microsoft's BCDEdit reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/bcdedit--set).

Hold the corrected PF CCS configuration fixed across this pair. If disabling the Windows hypervisor changes failure to success, that prioritizes the independently observed Windows classification path. Intel still acknowledges that defect in [KB 000102878](https://www.intel.com/content/www/us/en/support/articles/000102878/graphics.html). The KB's named hardware is newer than ADL-P; our separate 7092 binary analysis supports investigating the same classification issue in the ADL driver lane, but does not establish that it caused this user's failure.

`HypervisorPresent=True` inside a KVM guest is insufficient to prove that Windows launched its own hypervisor. Likewise, host `kvm_intel.nested=Y` only enables a host capability. Keep these distinct from the guest's boot policy and actual VBS/Hyper-V activity.

### If further PF/VF tracing is needed

Capture `sriov/pf/versions`, `sriov/pf/tile0/gt0/adverse_events`, `runtime_registers`, and GuC state during startup before VF teardown. A VF FLR clears its negotiated ABI and monitoring counters, so a post-teardown zero does not prove that the guest never negotiated or encountered an event. The collector already captures the selected snapshots.

Existing `xe:xe_guc_ctb_h2g` and `xe:xe_guc_ctb_g2h` tracepoints expose the outer action, message length and buffer positions. They do **not** expose the entire relay payload/VFID/inner query, so they cannot alone establish what Windows requested. Detailed relay debug output is compiled out without `CONFIG_DRM_XE_DEBUG_SRIOV`; enabling dynamic debug cannot recover omitted callsites. Request a targeted trace only if the simpler configuration and Windows-state comparison leave initialization unresolved.

Current DKMS's ADL runtime-register export already includes `0x9144`. Working i915 additionally exports `CTC_MODE` and `TIMESTAMP_OVERRIDE`; no evidence yet shows that the installed Windows driver fails because those two are absent from Xe's reply. Do not blindly port that table before capturing the actual guest request and failing stage.

### Status of the earlier patch

The branch's accepted timestamp correction remains a legitimate Linux Xe fix. It changes Linux-created contexts; Windows builds its own VF contexts. This new case does not validate that patch as a Windows startup repair. The correct existing Xe CCS option has now been tried without resolving Code 43. The later full captures now narrow the next step to first-CAT context/mapping evidence and a separate ADL-P render-offset experiment. A nested-Hyper-V discriminator remains conditional on evidence that Windows actually launches its hypervisor. This historical CCS analysis introduced no additional driver change; see the newer experiment note for the current branch.


---

## ADL-P after CCS enable: bounded runtime-service audit

**Later capture update:** the replacement archives and second VM attempt are analyzed in [the current capture note](adlp-reuploaded-capture-analysis.md). All have CCS enabled; the second attempt faults before any new KVMFR export. The user confirms unchanged settings and persistent Code 43. A separate [ADL-P render-context experiment](adlp-indirect-offset-experiment.md) is now built for testing. The source distinctions below remain evidence, not established causes.

Inspected on 2026-10-02. Baseline: `strongtz/i915-sriov-dkms` commit `f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88`. Windows binary: official 32.0.101.7092 `igdkmdn64.sys`, SHA-256 `454624942bf9a79a75fd1bfe6c6a2f8d499aabef45cb4268a1353d527902d098`. The actual failing guest's module hash/version has not been established by this inspection. This is source and original-binary analysis, not a GPU test. No driver source or configuration was changed.

The user reports Code 43 persists after enabling CCS. The previously supplied log established a separate PF render-engine timeout in host `.org.gnome.Naut`; it did not establish the first failed guest operation. Preserve that PF coredump and correlate a fresh occurrence with guest startup before assuming an isolated guest-only failure.

### There is no demonstrated ABI 0.1 versus 1.0 version mismatch

The actual working-i915 comparison source defines both base and latest ABI as **1.0**, in `drivers/gpu/drm/i915/gt/iov/abi/iov_version_abi.h:9`. Xe defines the same values in `drivers/gpu/drm/xe/abi/guc_relay_actions_abi.h:24`.

For the valid two-word CT handshake, i915 `intel_iov_service.c:265` and Xe `xe_sriov_pf_service.c:41` both choose 1.0 for a 0.0 ANY request or a newer major, accept a 1.x request with negotiated minor zero, and reject an explicit 0.1 request. Their Linux rejection errno differs; their accepted version sets do not. The Windows handshake bytes have not been recovered or observed. Downgrading Xe's ABI declaration to 0.1 is therefore unsupported by this comparison.

### A real sequencing difference deserves a trace

Xe records successful handshake state per VF, then requires negotiated ABI 1.0 before serving `VF2PF_QUERY_RUNTIME` (action `0x0101`): `xe_gt_sriov_pf_service.c:329` returns `-EACCES` if that state is missing. `xe_sriov_pf_service.c:176` clears the state when the VF connection is reset. Its successful-handshake path logs the negotiated version.

i915's CT handshake sends a reply without recording corresponding negotiated state (`intel_iov_service.c:308`). Its request dispatcher (`:450`) directly invokes the runtime handler; `pf_reply_runtime_query` (`:314`) checks message length and range but has **no equivalent negotiation-state check**. Thus a guest that queries before handshaking, or reuses pre-reset assumptions, can encounter different behavior. That is a concrete difference in PF behavior, **not evidence that Windows actually does this**.

The most discriminating service trace is the VF-specific order and replies: handshake action `0x0001`, runtime action `0x0101`, each reset/FLR, negotiated version, and first failing reply. A successful 1.0 handshake followed by successful runtime pages rules out this particular ordering explanation for that startup. A runtime request rejected with EACCES before negotiation would establish the missing edge and justify a narrowly scoped compatibility decision rather than an ABI-number change.

Verbose service-action logging in `xe_gt_sriov_pf_service.c:382` is conditional on `CONFIG_DRM_XE_DEBUG_SRIOV` through `xe_gt_sriov_printk.h:30`; enabling dynamic debug cannot restore code compiled out by that option. Ordinary successful-handshake logging is not that verbose-only macro. A diagnostic patch, if needed, should log action, VF, result and reset sequence without changing acceptance policy first.

### Two missing clock registers are real, but VF consumption is unproved

At this pinned source, Xe's TGL-family runtime list exports eight register/value entries, whereas i915 exports ten. The additional i915 entries are `CTC_MODE` (`0xA26C`) and `GEN9_TIMESTAMP_OVERRIDE` (`0x44074`): `xe_gt_sriov_pf_service.c:24` versus `intel_iov_service.c:31`. `0x9144` is already present in this DKMS Xe and must not be proposed as a newly missing entry merely because bare mainline differs. The public service returns raw register values, so the EU_ENABLE/EU_DISABLE source-name difference does not itself imply transformed values.

Runtime query `0x0101` is **enumeration by start index and limit**, returning offset/value pairs and remaining count; it does not request a named register address. A trace will therefore show which pages Windows obtains, not a literal request for CTC_MODE. Compare the complete PF runtime maps plus response pages from working i915 and failing Xe with an unchanged guest.

Original 7092 code supports the following narrower statements; all addresses below are RVAs for the hashed file:

- `0x3D236D–0x3D2425` reads `0xA26C`, `0xD00`, and conditionally `0x44074`, computes a clock frequency, and stores it in a nested object's `+0x7F4`. The non-override path derives a nonzero standard frequency from RPM_CONFIG0. A missing CTC_MODE that reads as zero therefore does **not by itself imply an immediate fatal error** in this arithmetic.
- Leaf `0x3D1120` follows nested-object `+0x728` to the adapter, then invokes the function at adapter-vtable `+0xF8` through Control Flow Guard dispatch. The VF-specific target of that callback has **not** been proved.
- `0x269590` searches cached `(offset, value)` pairs: primary GT uses adapter `+0x56BB0` count and `+0x56BB8` pointer; media GT uses `+0x56BC0/+0x56BC8`. If absent, it writes zero through its output argument and logs. This is an actual cache helper, but a call edge from the clock reader to it was not established.
- `0x269A10–0x269D1E` creates a cache from a platform register list (`+0x5AC80/+0x5AC88`) and reads each value through the same vtable `+0xF8` callback. This function contains no proved PF-runtime relay transaction. It can describe native capture; it cannot by itself prove VF negotiation or consumption of PF data.
- Several platform initialization functions install ten-entry lists; for example `0x26C540` installs internal platform `0x25`, a list at RVA `0x8A61E0`, and count ten. This pass did not complete the PCI-ID-to-initializer selection for ADL-P `46A6`. Tables selected for other generations are not ADL-P evidence.

Raw instruction evidence: `windows/analysis/7092/runtime-register-consumers.txt`, `runtime-register-xrefs.txt`, `runtime-query-flow.txt`, `runtime-table-select.txt`, `runtime-count-xrefs.txt`, `runtime-cache-xrefs.txt`, and `runtime-list-xrefs.txt`. The PE exception table omits some leaf functions and splits other functions; a preceding exception-table entry alone must not be treated as a valid function boundary. `runtime-register-consumers.txt` explicitly appends the verified complete `0x3D1120` leaf after the initial exploratory disassembly.

### Evidence-ranked next action

First capture the PF render failure/coredump and the first VF service/submission failure during the same unchanged-guest startup. In that capture, discriminate the concrete handshake-state difference before altering ABI policy. Compare the full runtime maps; if negotiation succeeds and the guest consumes the returned map, an isolated two-register exposure A/B is a small plausible compatibility experiment, but still requires measured startup behavior and timing values. There is no present justification to migrate i915's complete service implementation or introduce an additional relay protocol for ADL-P.

The prior Hyper-V binary findings remain conditional on actual guest CPUID and Hyper-V state; they do not explain a controlled i915-success/Xe-failure pair by themselves. Neither this audit nor the previous classifier emulation proves a path from these two absent registers to Code 43.


---

## ADL-P: first PF DMA fault after enabling CCS

**Later capture update:** the replacement archives and second VM attempt are analyzed in [the current capture note](adlp-reuploaded-capture-analysis.md). All have CCS enabled; the second attempt faults before any new KVMFR export. The user confirms unchanged settings and persistent Code 43. A separate [ADL-P render-context experiment](adlp-indirect-offset-experiment.md) is now built for testing. The source distinctions below remain evidence, not established causes.

Inspected 2026-10-02 from the user-supplied full host log (SHA-256 `12d4699b3e4f63e22377514554835e123a3ef00c4bda95e508e42a720d425e8b`). Driver-source comparison is pinned to `strongtz/i915-sriov-dkms` `f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88`; upstream DMAR logging was checked at Linux `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`. No code or configuration changes.

### The first recorded failure is host PF DMA translation

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

### Xe explicitly found a host queue for the CAT event

In `drivers/gpu/drm/xe/xe_guc_submit.c:3001`, the CAT handler obtains the reported GuC ID and calls `g2h_exec_queue_lookup`. That lookup at `:2779` loads from this Xe device's `submission_state.exec_queue_lookup` XArray. If no queue is found, the handler returns EPROTO before printing the detailed `class=rcs ... guc_id=65` message. Unknown PF/VF context has a distinct generic error path at `:3017`.

Therefore the supplied detailed message means the PF driver successfully matched the notification to one of its own execution-queue objects. It does not prove the exact userspace owner of that queue or exclude an earlier cross-VF hardware-state disturbance, but it is stronger evidence of host execution involvement than treating every failure after guest launch as a guest context.

The VF's context IDs are reserved in the PF ID manager and unavailable for PF allocation (`xe_gt_sriov_pf_config.c:887–951`). The manager reserves high IDs for VF ranges and allocates ordinary submissions from the low end (`xe_guc_id_mgr.c:132`). A captured provisioning range can confirm the actual split; do not infer an exact range from quota alone. Existing `xe_exec_queue_memory_cat_error` and queue/job tracepoints can preserve context ID 65 before reset churn; the stock CAT tracepoint does not itself include userspace process ownership.

### No ADL-P GGTT VF-ID encoding mismatch found

i915 ADL-P uses `TGL_GGTT_PTE_VFID_MASK` bits 4:2, then adds PRESENT (`intel_gtt.h:119`, `intel_ggtt.c:2143–2172`). Xe uses bits 11:2 plus PRESENT (`regs/xe_gtt_defs.h:17`, `xe_ggtt.c:943`). For the supported VF IDs 1 through 7 these encodings are identical; VF1's initial ownership PTE is 0x5 in both. The wider Xe mask alone is not an ADL-P incompatibility.

Both drivers reserve a GGTT region, tag the region with its VF ID and invalidate, then send its start/size to GuC: i915 `intel_iov_provisioning.c:688–702` and `intel_ggtt.c:2175`; Xe `xe_gt_sriov_pf_config.c:534–546` and `xe_ggtt.c:948–981`. The software implementation therefore contains the expected ownership operation. Actual post-FLR PTE contents and timing still require capture if suspicion remains.

PF-owned GuC ADS/golden-context buffers being mapped under PF identity is not inherently incorrect. Xe copies its captured default LRC into its ADS in `xe_guc_ads.c:972`; this inspection did not prove a Windows VF context copies a PF-only address or later writes it under the wrong identity. The existing reset-BB-stack-pointer-on-VF-switch GuC workaround is already enabled for ADL-P by Xe's graphics-version range and the observed 70.49.4 firmware (`xe_wa_oob.rules:48`, `xe_guc_ads.c:328`); importing i915's same workaround again is not a supported fix.

### DMA-buffer import is an immediately separable path

For an external DMA buffer, Xe attaches to the importing DRM device (`xe_dma_buf.c:389`), maps it with `dma_buf_map_attachment(..., DMA_BIDIRECTIONAL)` during `xe_bo_move_dmabuf` (`xe_bo.c:736–775`), and consumes scatterlist **DMA** addresses (`xe_res_cursor.h:336`). i915 likewise maps its imported attachment through the DMA-buffer API (`gem/i915_gem_dmabuf.c:238–263`). Neither examined path deliberately uses a VF's device to map a host Looking Glass buffer.

The current official [Looking Glass kvmfr exporter](https://github.com/gnif/LookingGlass/blob/master/module/kvmfr.c#L99) maps exported pages with the attachment device's DMA API and unmaps them when requested. That source is an external comparison; the exact loaded kvmfr revision has not been established. Xe's mapping lifetime follows TTM movement and differs from i915's object page lifetime. No mapping-lifetime bug or faulting-buffer address has been proved here.

The smallest useful hardware discriminator is a fresh same-guest boot with the **host Looking Glass client stopped**, preserving the VF, guest driver and firmware. Read Windows device status independently of Looking Glass. If Code 43 and the PF CAT/DMAR fault disappear, then reproduce by starting Looking Glass and narrow its DMA-buffer path. If Code 43 remains without PF DMA faults, there may be a separate guest-start problem and the two symptoms must not be conflated. Stopping the client after the first GT corruption is weaker than a fresh startup.

Subsequent recovered capture correction: a second VM start in this same already-faulted boot produces its first new PF DMA fault at 717.790880 seconds, **before** the first new `kvmfr_dmabuf_create` at 738.386900. At 735.116206, CAT queue14 is followed 106 microseconds later by a queue14 timeout attributed to host `systemd-logind`. Therefore the first-run 12.633 ms correlation does not establish that a fresh KVMFR export triggers every fault. This second run is not a clean reboot and cannot rule out prior mapping/state damage either. Keep the client-stopped test as isolation, not a diagnosed fix.

For a code-level capture, correlate the first CAT queue with its VM, relevant GPU PTEs and DMA mapping addresses; record imported-buffer attachment device, direction, mapped SG DMA ranges and map/unmap lifetime. Determine whether 0x78226a000 belongs to a current PF DMA mapping or an imported kvmfr range. Only then select a mapping, ownership or lifetime correction. The older runtime-register/handshake hypotheses remain documented in `adlp-runtime-contract-audit.md`, but the new first-fault evidence gives this DMA/execution path priority.


---

## ADL-P host DMA fault near Looking Glass import

**Later capture update:** the replacement archives and second VM attempt are analyzed in [the current capture note](adlp-reuploaded-capture-analysis.md). All have CCS enabled; the second attempt faults before any new KVMFR export. The user confirms unchanged settings and persistent Code 43. A separate [ADL-P render-context experiment](adlp-indirect-offset-experiment.md) is now built for testing. The source distinctions below remain evidence, not established causes.

Bounded source review, 2026-10-02. MTL work remains paused. No module was built, loaded, unloaded or patched; no VM or configuration was changed.

### Assessment

The supplied log makes the **Linux host Looking Glass / dma-buf import path a priority discriminator**, but does not establish kvmfr as the cause. The first IOMMU fault names PF `0000:00:02.0`, immediately followed by a host Xe render-engine CAT error and later host GT resets. Treating this excerpt as proof of an independent Windows-driver startup rejection is premature. Conversely, the excerpt does not identify the first faulting buffer or its owning process, so the first queue must not be labelled Looking Glass solely from timing.

The first test should be a fresh run **without the Looking Glass client**, observing the guest through an independent path. For a stronger Looking Glass-free control, also stop guest Looking Glass capture. If that run succeeds, repeat with the same shared-memory setup and the supported B7 client option:

```sh
looking-glass-client app:allowDMA=no
```

Preserve any other existing client arguments. This disables the client's direct dma-buf import while retaining `/dev/kvmfr0` shared memory and normal host GPU rendering. It does **not** disable guest capture, all GPU DMA, or the kvmfr module itself. Thus it is more specific than removing the entire shared-memory device from the VM. The [official B7 option documentation](https://looking-glass.io/docs/B7/usage/#all-command-line-options) and pinned source both support the option. Current development master uses `lgmp:allowDMA` as its canonical spelling but retains `app:allowDMA` as a compatibility alias.

### What the supplied log proves

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

### Source provenance and the likely Nix package

The log's system path identifies nixpkgs abbreviation `f0f0d1a`. Its [kvmfr derivation](https://github.com/NixOS/nixpkgs/blob/f0f0d1a/pkgs/os-specific/linux/kvmfr/default.nix) uses `looking-glass-client.version` and `.src`, builds the `module` directory against the selected kernel, and adds no source patch list of its own. The [client package at that revision](https://github.com/NixOS/nixpkgs/blob/f0f0d1a/pkgs/by-name/lo/looking-glass-client/package.nix) selects **B7**. Therefore an unoverridden `config.boot.kernelPackages.kvmfr` from that package set is B7 source built for the chosen kernel. Linux version 7.2.8 alone does not establish its source revision; overlays and explicit package overrides remain possible.

Official Looking Glass source was downloaded read-only for inspection:

- B7 tag resolves to `27fe47cbe2a3a8da986d310ab866f0b646ed68f5`.
- Development master observed as `236efcb155f952f5d7d9fcd5891a3060ad254e68`.
- Xe mapping comparison uses the existing pinned Linux source `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9`. This is a source comparison baseline, not proof of the exact loaded Xe image on the user's host.

### Exporter mapping and lifetime

In [B7 `module/kvmfr.c`](https://github.com/gnif/LookingGlass/blob/27fe47cbe2a3a8da986d310ab866f0b646ed68f5/module/kvmfr.c), the static device uses `vmalloc_user()` (`:502` onward). A buffer export validates alignment and bounds, obtains the corresponding pages with `vmalloc_to_page()`, and exports a dma-buf (`:188` onward). The logged creation message occurs after `dma_buf_export()` but before returning the dma-buf FD. It is **not a log of successful GPU attachment, IOMMU mapping, or submission**.

`map_kvmfrbuf()` (`:106`) creates a fresh scatter-gather table from those pages and calls:

```c
dma_map_sg(at->dev, sg->sgl, sg->nents, direction)
```

The device is the **importing attachment's device**. With Xe importing, mappings are therefore requested for Xe's device, not the kvmfr class device. The callback returns mapped DMA addresses via the normal API; the inspected code does not simply supply unmapped physical page addresses to Xe. `unmap_kvmfrbuf()` uses the same device/direction, unmaps the list, and frees that table. `release_kvmfrbuf()` frees the export's page-pointer array and metadata; it does not free the static backing storage for each exported frame.

B7's client caches dma-buf FDs per frame buffer and invokes `ivshmemGetDMABuf()` when one is needed (`client/src/main.c:783`). Its `useDMA` flag is the conjunction of `app:allowDMA` and shared-memory DMA capability (`:1337`). With DMA disabled, the renderer receives FD `-1` instead (`:796`). The ioctl wrapper rounds buffer size to page size; the export validates the supplied range again. These are source-level ownership observations, not runtime proof that no reset/import race occurred.

#### Scatter-list count discrepancy: real audit finding, unproven explanation

Both B7 and the inspected current master treat `dma_map_sg()`'s return only as success/failure. They do not replace `sg_table.nents` with the returned **mapped** segment count. Linux's [DMA API contract](https://docs.kernel.org/core-api/dma-api.html) permits mapping to merge entries: consumers should use the returned count, while unmapping requires the original input count. Thus an exporter should preserve original versus mapped counts explicitly, normally through the sg-table API or equivalent bookkeeping.

Here `sg->nents` remains the original count, so using it as the unmap argument is **not itself the common wrong-count unmap bug**. The questionable part is returning a table whose `nents` may not describe the mapped segment count. Changing only the map-side field and leaving unmap unchanged would introduce a separate mistake.

Crucially, the inspected Xe PTE paths do not use that field as their loop bound. `xe_pt.c:875` and `xe_ggtt.c:702` call `xe_res_first_sg()`, whose cursor walks mapped addresses and lengths via `sg_dma_len()`/`sg_next()` until the requested byte range is covered (`xe_res_cursor.h:159`, `:214`, `:335`). A smaller mapped count therefore does not, by itself, demonstrate an invalid Xe PTE in this path. No runtime merged counts, map/unmap trace, buffer IOVA list or failing PTE were supplied. Record this as a compatibility/audit concern, **not a proven fix for Code 43 or the DMAR fault**.

### Xe import behavior and limits

[Current inspected Xe `xe_bo.c`](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_bo.c#L740) calls `dma_buf_map_attachment(attach, DMA_BIDIRECTIONAL)` and uses the returned mapped SG table. Its comment describes deferred unmapping until a subsequent remap or destruction after idling, relying on reservation-object synchronization (`:737` onward). This requires lifecycle evidence to diagnose; the export log alone cannot show premature unmapping.

A recent upstream import-lifetime fix, [62775525a27c](https://gitlab.freedesktop.org/drm/xe/kernel/-/commit/62775525a27c3b0d56382e08ba81ee2d322058b6), keeps a dma-buf reference across imported-BO creation failure and deferred destruction. Its documented trigger involves failed attach/BO initialization and a reservation-object use-after-free. It is already an ancestor of the inspected `ce1e` baseline. Neither that trigger nor its characteristic CPU fault is established by the supplied log; do not prescribe it as an absent fix solely because it mentions dma-buf.

### Known-report search and next evidence

A bounded search of official Looking Glass GitHub issues for `DMAR` and `dma_map_sg` returned no matches; a combined IOMMU/Xe-driver/page-table search returned four unrelated older reports. The saved query results are in `evidence/adlp-kvmfr/`. This is not evidence that the problem is unknown everywhere. No verified primary report matching this exact Xe + static-kvmfr + PF DMA-write sequence was established in this review.

Record the outcome of the no-client control first, then `app:allowDMA=no`, using fresh runs so prior host-reset damage does not confound the comparison. Compare **the first** DMAR/CAT error and Windows device status, not only later queue timeouts. If DMA-off isolates the failure, the next useful trace is the attachment device, original/mapped segment counts, mapped IOVA ranges, map/unmap timestamps, and first queue ownership. A valid Xe device coredump captured at the first failure could identify the failing VM/BO/PTE. Without those observations, neither Windows-driver changes nor a scatter-count patch has a demonstrated causal target.
