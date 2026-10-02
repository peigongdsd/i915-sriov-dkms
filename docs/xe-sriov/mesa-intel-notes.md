# Intel statements, Mesa implications, and modern implementation boundaries

Research date: 2026-10-02. No runtime or configuration modifications. This note separates verified source statements from diagnostic inferences. Mesa source snapshot: `9046ec144bbb18a2cfbb7719adf19303b710a2c3` (main at retrieval, committed 2026-10-02 09:56 UTC). Retrieved source and API responses are under `sources/mesa/`.

## What Intel actually said about platform support

1. José Roberto de Souza's Mesa commit [31920cb60c3cf487bc29ebd1d8ad8b1825e09fab, “intel: Enable Xe KMD support by default”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/31920cb60c3cf487bc29ebd1d8ad8b1825e09fab) (2024-03-12, MR 20418) removed the build-time gate because the upstream Xe userspace ABI had stabilized, while retaining experimental status for platforms older than Lunar Lake. This is not removal of ADL/MTL support. Current `intel_device_info.c:1981-1986` still calls the Xe query backend and prints a warning for `verx10 < 200`; the warning does not itself reject the device.
2. Intel SR-IOV maintainer Michal Wajdeczko [answered on 2025-07-01](https://lkml.iu.edu/2507.0/01102.html) that pre-LNL Xe platforms were not officially supported, so SR-IOV was enabled only on SDV platforms actively tested in public CI (ADL and ATS-M). He described TGL enablement as adding `has_sriov`, but robust MTL enablement as requiring considerably more SR-IOV-specific code and prior native-mode testing. This establishes a support/testing boundary; it does not establish hardware impossibility or specify which MTL changes are unavoidable.
3. Intel's Matt Roper [reiterated on 2026-09-30](https://lkml.rescloud.iu.edu/2609.3/17001.html) that ADL force-probe support was intended for kernel developers and could lack ADL hardware workarounds. This is current, direct evidence that native Xe success should be tested before attributing every VF failure to SR-IOV.

## ADL-P: the compute engine bit is a cross-layer contract

The exact Mesa contribution to inspect is [a364f23a6cfa28e1843ef1e64dce56b4cef5a71e, “intel: Make gen12 URB space reservation dependent on compute engine presence”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/a364f23a6cfa28e1843ef1e64dce56b4cef5a71e), by José Roberto de Souza (MR 21031). Its message explains that `RCU_MODE::Compute Engine Enable` is a global control for dual-context operation and that hardware reserves URB resources when it is set. Mesa subtracts **4 KiB per L3 bank** for Gfx12.0 only when the engine query reports a compute engine. At the time, Intel said the kernel did not enable dual context on these platforms, but anticipated that this could change.

The diff sets `has_compute_engine` from the KMD's queried engine list for both Iris and ANV, then changes `intel_get_urb_config()` to subtract the reservation only when that field is true. This means a patch that silently sets the physical CCS enable bit while hiding CCS from the engine query can produce an inconsistent memory layout. Conversely, reporting CCS without valid hardware setup/context save semantics is not sufficient. This is a **source-supported diagnostic inference**, not a diagnosis of the user's unobserved failure.

The earlier Intel contribution [81d6ae31, “anv, iris: Enable compute engine with INTEL_COMPUTE_CLASS=1”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/81d6ae31) introduced opt-in compute-engine usage (MR 14395). Engine support and compute API availability must not be conflated: compute workloads can execute on a render command streamer. Do not treat “OpenCL/Vulkan compute works” as proof that a separate CCS engine works.

Suggested comparison fields across native Xe, Xe VF, and working i915 VF: physical dual-context/CCS enable state; GuC engine masks; queried render/compute engine list; GuC ADS register save/restore list; default RCS/CCS LRCs; Mesa `has_compute_engine` and computed URB size. Keep CCS = compute command streamer distinct from CCS = compression metadata.

## A current ADL context-image regression deserves a controlled test

Helen Koike posted “drm/xe/lrc: Restore CTX_CS_INDIRECT_CTX_OFFSET programming for ADL” on 2026-09-30, identifying [c9dfd66cb91e, “drm/xe/lrc: Allow INDIRECT_CTX for more engine classes”](https://github.com/torvalds/linux/commit/c9dfd66cb91e) as the change after which ADL IntelAngleEnd2EndTestCases sporadically returned `VK_DEVICE_LOST`. This is a proposed fix under discussion, **not a verified merged fix for SR-IOV**.

The [Intel review](https://lkml.rescloud.iu.edu/2609.3/17001.html) initially reasoned that restore-inhibit plus a context switch should preserve the hardware default and asked to inspect `default_lrc_*`, specifically dword offset `(0x16 + 1)`, and to identify affected engines. The [author's October 1 reply](https://www.mail-archive.com/dri-devel@lists.freedesktop.org/msg640961.html) distinguishes **ring context** from **engine context**, cites the TGL PRM, and provides an actual RCS default-context dump with register `0x21c8 = 0x00000000`. Her explanation is that engine restore inhibit does not inhibit ring-context restoration, so zero can be restored before default capture.

This is a sharper lead than generic speculation about bad context images: compare the exact default LRC field and the presence of c9dfd66 in the failing build. The patch's broad `< 20` guard and engine-specific defaults were also questioned; do not copy a single RCS value across every engine/platform. Importantly, **INDIRECT_CTX workaround batches are not the same feature as Xe's Indirect Ring State page**. The latter's 2024 enabling and later GuC ADS engine-state-size fix are separate topics.

## MTL/ARL: compression architecture differs from Xe2

Intel's Mesa [MR 20322 commits](https://gitlab.freedesktop.org/mesa/mesa/-/merge_requests/20322) provide a concise platform-specific explanation:

* [6e33423a6fabca16587a3fada6b74530fb07a57b, “intel/dev: Enable AUX map on MTL”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/6e33423a6fabca16587a3fada6b74530fb07a57b), Jianxun Zhang.
* [f81579628a60de73146c9bc5b774b83a63489a4a, “intel/aux_map: Ignore format bits when using tile-4”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/f81579628a60de73146c9bc5b774b83a63489a4a), Jordan Justen: MTL uses an AUX translation map again, but Gfx12.5+ reads compression format from surface state and ignores format bits in AUX-map metadata. Tile4 replaces Y tiling for this path.
* [5df50292d60dd77f38a19f5b3f7568a7a83d7cd1, “intel/isl: Disable CCS on MTL until B0 (Wa_14017353530)”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/5df50292d60dd77f38a19f5b3f7568a7a83d7cd1): an early-stepping workaround, not a blanket statement that production MTL cannot compress.

Consequently, Xe2 SR-IOV FlatCCS support must not be assumed to solve MTL AUX translation. ADL also has an AUX-map path, so AUX-map existence alone does not explain why MTL needs more work. The relevant MTL contract includes per-context AUX table state, per-engine invalidation, media/render relationships, and the real architecture's cache attributes. Whether any particular missing item causes the user's failure still requires tracing.

Current Mesa `genX_init_state.c` programs AUX table base registers from userspace when `has_aux_map`; `genX_cmd_buffer.c` invalidates per-engine AUX caches. These are existing userspace mechanisms to preserve, not reasons to transplant old i915 memory management wholesale. Source snapshot links: [initial state](https://gitlab.freedesktop.org/mesa/mesa/-/blob/9046ec144bbb18a2cfbb7719adf19303b710a2c3/src/intel/vulkan/genX_init_state.c), [command buffers](https://gitlab.freedesktop.org/mesa/mesa/-/blob/9046ec144bbb18a2cfbb7719adf19303b710a2c3/src/intel/vulkan/genX_cmd_buffer.c).

## PAT, CPU coherency, and scanout are already modern Xe contracts

[500e037661e369927aeee0c1c5cb41fb8b946d4b, “intel: Add PAT entries for gfx12 and newer”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/500e037661e369927aeee0c1c5cb41fb8b946d4b), José Roberto de Souza, explicitly states that Xe requires PAT selection on every supported platform. [29d4d2640677d3cba4fa32acbe4c6e1109999e1a](https://gitlab.freedesktop.org/mesa/mesa/-/commit/29d4d2640677d3cba4fa32acbe4c6e1109999e1a) explains keeping PAT, CPU mmap mode, and BO coherency requirements together in platform information. This favors using Xe's existing BO + VM_BIND/PAT model and correctly adapting platform tables over importing i915 GEM caching APIs.

[0d668f50dc88f06100513abe2ef0fe379ed0ed27, “intel: Update MTL scanout PAT entry”](https://gitlab.freedesktop.org/mesa/mesa/-/commit/0d668f50dc88f06100513abe2ef0fe379ed0ed27) changed the scanout policy because preceding integrated GPUs had noncoherent GT and display caches and Intel had not established that MTL changed this. This directly supports testing scanout/composition separately from offscreen render success. It does not prove that a Windows guest DWM defect is a PAT defect.

## Discriminating tests, in order

1. Establish native Xe and headless VF kernel submission correctness with the same kernel/firmware versions, by engine. If the guest cannot reach driver initialization or the first tiny submission, Mesa compression tuning is downstream of the failure.
2. Query engines/topology/configuration through the guest Xe uAPI. Current Mesa's Xe device-info backend refuses missing geometry-DSS or EU masks; the experimental warning itself is not a blocker. Source [xe/intel_device_info.c](https://gitlab.freedesktop.org/mesa/mesa/-/blob/9046ec144bbb18a2cfbb7719adf19303b710a2c3/src/intel/dev/xe/intel_device_info.c).
3. Record physical enable state versus published engine list and URB reservation. Test RCS-only scheduling separately from CCS opt-in, with known correspondence between PF and VF assumptions.
4. Compare RCS default LRC `0x21c8` and affected source ancestry before trying the September context fix; capture engine-specific default context files.
5. Once headless execution succeeds, separate linear/uncompressed BO copy, tiled render, compressed render, and scanout/composition. Compression disable switches in Linux Mesa can be diagnostic controls, but do not fix a Windows guest's proprietary userspace implementation.
6. For MTL/ARL, audit AUX table save/restore and invalidation and PAT/coherency with actual platform data; do not rename AUX-map platforms as FlatCCS-capable to reuse Xe2 code.

There is no primary evidence in this research establishing one universal “Gen12 Xe Mesa incompatibility,” nor proof that indirect ring state, GPU page-table updates, or FlatCCS is intrinsically required to start an ADL VF. Treat those as separately measurable contracts.
