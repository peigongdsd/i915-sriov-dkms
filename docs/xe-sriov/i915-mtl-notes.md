# MTL/ARL i915 versus Xe source investigation

Inspected 2026-10-02. This is a source/history study, not hardware validation.

## Source identities and the most useful new evidence

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

## Phase comparison

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

## Corrections to earlier cache hypotheses

### Declared MTL PAT and MOCS tables already match

i915 PAT indices 0–4 (`intel_gtt.c:505–535`) and Xe's `xelpg_pat_table` (`xe_pat.c:81–87`) encode the same policies: WB/no coherency, WT/no coherency, UC/no coherency, WB/one-way, WB/two-way. Xe internal cache-level mapping is UC→2, WT→1, WB→3 (`xe_pat.c:497–503`).

i915 `mtl_mocs_table` (`intel_mocs.c:382–430`) and Xe `mtl_mocs_desc` (`xe_mocs.c:449–498`) also have the same declared entries. A wholesale table import therefore has no explanatory value. Hardware programming and guest selection can still differ.

The apparent reversed Xe `xelpg_pat_ops` routing (`xe_pat.c:351–358`) deserves awareness, not a root-cause claim: graphics uses plain writes while media uses the MCR helper, opposite the adjacent comment/dump routing and i915. However mainline `xe_gt_mcr_multicast_write()` (`xe_gt_mcr.c:880–894`) itself only takes the MCR lock, performs the same MMIO write, and unlocks; multicast is the default state. During serialized initialization this can produce the same hardware writes. This is present in mainline too, not introduced by the SR-IOV fork.

### GGTT PAT counts do not identify Windows surface policy

The June note inferred that most GGTT entries use UC because they select PAT2. The histogram proves the selected GGTT PAT index, but it does not prove that the corrupt Windows surface is uncached:

1. A Windows application/composition surface is normally accessed using its process GPU page tables. Those PPGTT mappings are not the PF's GGTT shadow.
2. MTL MOCS entries 1–15 in these tables use `IG_PAT` (ignore PAT), and include cached modes. Command/surface MOCS selection matters alongside page-table PAT and coherency.
3. The same physical page may have several GPU/CPU aliases. Mutating one GGTT PAT entry does not establish consistent policy across those aliases.

Thus do not conclude that PAT3 is wrong because it is rare, or that changing those 335 GGTT PTEs to PAT2 should fix Windows. A narrowly scoped cache experiment must identify the corrupt surface and account for its PPGTT/MOCS/CPU aliases. A temporary consistent conservative surface policy can be a diagnostic, not a proposed final fix.

### Flat CCS is not the obvious MTL mechanism

MTL's descriptor has no `has_flat_ccs`; `xe_device.c:783–804` runtime flat-CCS probing is for graphics >=20. `xe_sriov_vf_ccs.c` migration logic is therefore not a demonstrated active path here. MTL can still have auxiliary-surface compression and synchronization issues; do not confuse those with the modern flat-CCS VF migration mechanism.

### Host display code is not automatically Windows VF code

Host Xe scanout/domain/flush/PAT changes often do not touch a Windows VF's private surface allocations. Linux Xe VF `vf_update_device_info()` likewise is not the Windows driver's capability source. For Windows compare the PCI/BAR contract, PF/GuC configuration and runtime replies, PF-programmed hardware, and guest allocation/command choices.

## Experiments already represented in history

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

## Intel primary-source messages

1. [Intel LTS runtime-register extension c031d1a](https://github.com/intel/linux-intel-lts/commit/c031d1a2aaea6d9804a6a12af67b424642171836): actually adds `0x10100c` and `0x389140` to the already existing MTL list. It is evidence of a platform-specific runtime contract; its short message does not prove any one missing value causes current corruption.
2. [Mainline c08c364: bypass MTL BAR stolen access](https://github.com/torvalds/linux/commit/c08c364102d07288610734de34111a666e730ae7): Intel explicitly identifies system hangs from MTL stolen BAR access, firmware-enabled direct DSM/GSM as the host workaround, and excludes guests from that direct physical-memory shortcut. Pcode `0x138914 == 1` is the permission check.
3. [Intel follow-up: disable the binder](https://www.mail-archive.com/intel-gfx%40lists.freedesktop.org/msg333305.html): once direct GSM works, Intel does not require MI_UPDATE_GTT; the message notes dependency/async/hang risks, retains binder for VMs, and leaves generic engine updates as a possible optimization. This directly supports preserving hardware semantics without copying old binder machinery.
4. Intel LTS [`bcf6f14318c852a7319cf3ebeb0978432e314c0e`](https://github.com/intel/linux-intel-lts/commit/bcf6f14318c852a7319cf3ebeb0978432e314c0e) is independently retrieved in `evidence/intel-lts-bcf6f143.json`. Its July 2023 message states that MTL VF direct GGTT access is unstable and updates must pass through the PF; it supplies MMIO/bootstrap and CT relay operation `0x0102`. This supports retaining the existing hardware/firmware workaround while reusing Xe transport and choosing a modern PF backend. It does not require porting the old binder or inventing another relay protocol; dropping mediation needs contrary hardware/firmware evidence.

## Recommended Xe-native architecture and next experiments

1. Finish ADL-P separately; do not put MTL binder/dual-GT/GSC work into that platform's fixes. ADL-P provides a simpler test of the shared VF/PF ABI.
2. Rebase the minimum MTL bring-up on current Xe, retaining gated SR-IOV enablement, correct power/firmware lifecycle, public MMIO/relay protocol support, and safe GGTT writes. Reuse Xe's existing provisioning, locks, workqueues and invalidation infrastructure. Modern mainline already models shared tile GGTT plus per-GT GuC state.
3. Direct GSM is the simplest PF backend **when the documented firmware permission is present**. On machines without it, use an engine-assisted backend only after implementing proper bootstrap and completion guarantees. Mainline `xe_migrate_update_pgtables()` (`xe_migrate.c:2051–2081`) offers native scheduling/dma-fence concepts for **PPGTT**; it is not a drop-in safe GGTT update operation. Validate the addressing/MI opcode/invalidation requirements instead of mechanically calling it.
4. Do not acknowledge a semantically complete VF update before physical writes and required invalidation are complete unless ABI ordering explicitly allows it. An asynchronous implementation should attach an actual completion fence and defer the response off the G2H completion worker. Test early MMIO without CT, steady CT, timeout, overlapping updates, and FLR teardown. This is correctness work, not a claim to cure the recorded artifact.
5. Use the June bounded traces, with one exact Windows driver/repro and working i915 PF as control. Capture **all** incremental KLVs on both GTs, GuC version/ADS workaround payload, runtime values, PAT hardware readback, MOCS hardware state and relevant workaround registers. Avoid trace-induced performance perturbation.
6. Reproduce rendering-to-copy-to-video-to-composition sharing with a minimal Windows sample. Capture output before presentation to distinguish GPU producer corruption from display/capture/compositor transfer. Correlate one failing allocation with its guest GPUVA, PPGTT PAT, actual surface/command MOCS, auxiliary metadata and synchronization operations. This is substantially more discriminating than another global GGTT change.
7. Use the host driver's actual PF policy delta to design one-at-a-time experiments. Declared PAT/MOCS table equality and existing Xe WC page-table mapping mean those are not missing features to import.
8. ARL: record actual PCI ID, GMD graphics/media versions and firmware. Current shared descriptor does not imply every ARL SKU/firmware pairing identical to MTL. Gate workarounds by affected IP/stepping, then validate ARL after MTL, not by a marketing-name substitution.

## Windows-driver reverse engineering

No binary download is necessary to establish the kernel differences above. For the older composition artifact, a targeted binary study becomes useful if matched PF captures show equivalent programming/protocol but Windows still selects a different private surface policy. Acquire the exact Intel package version used by that failing guest; record SHA-256/signature/version; inspect INF/device matches and published symbol/PDB metadata first, then static disassembly of relevant initialization or allocation paths. Decode observed GuC/MMIO messages with the open ABI before spending effort reverse-engineering unrelated code.

The broader task identified a separate, narrow opaque contract in recent Windows Code 43 reports: nested Hyper-V environment classification. A targeted **9033** binary analysis and isolated classifier emulation were therefore subsequently completed; see `windows/analysis/9033-findings.md`. It confirms a specific unexamined nested-CPUID distinction in that classifier, not a solution to the historical MTL composition artifact.

No driver code was changed, built, loaded or tested on hardware during this source study.
