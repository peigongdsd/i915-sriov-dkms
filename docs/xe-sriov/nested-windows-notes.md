# Nested Hyper-V, Windows VF startup, and the CPUID contract

Verified against primary sources on 2026-10-02. This is source analysis, not a local runtime reproduction. The separately conducted binary analysis should identify which of these branches exists in each actual driver image.

## Intel acknowledges a guest-driver classification defect

Intel's [KB 000102878](https://www.intel.com/content/www/us/en/support/articles/000102878/graphics.html) explicitly attributes a VFIO SR-IOV Code 43 failure to treating nested Hyper-V as a native Hyper-V host. Its published resolution still says Intel is investigating; the page identifies driver 32.0.101.8531 and Core Ultra 7 265H. This is not simply a conjecture that nested EPT or IOMMU is broken.

[#1394](https://github.com/IGCIT/Intel-GPU-Community-Issue-Tracker-IGCIT/issues/1394) was closed June 30 when Intel redirected updates to that article, not when a fixed driver was announced. The retrieved API reports `state_reason=completed`, which is misleading if interpreted as evidence of remediation. A July 27 independent lab report identifies `igdkmdn64.sys` 32.0.101.8826, SHA-256 `AECB6FDEB393BA9F92945FF1507D5FB41996E0EB7EE0A575D5AE8E8C14B87B80`, and ARL VF device 7D67. It reports an earlier skipped state transition, leaving a later StartDevice guard to return `0xC000000D`, with DxgKrnl Event 549 and Code 43. The report claims that correcting the earlier transition enabled startup on Windows 11 and Server 2025. Those experiments are the reporter's evidence, not independently repeated here. Intel tracking number: `14027918034`.

The separate B50 [#1468](https://github.com/IGCIT/Intel-GPU-Community-Issue-Tracker-IGCIT/issues/1468) concerns startup regressions reported without nested virtualization. Therefore Code 43 alone cannot identify the nested defect or justify applying its proposed correction to all startup failures.

## Exactly which Hyper-V bits mean what

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

## Why hypervisor flags are not interchangeable

[QEMU's own Hyper-V documentation](https://www.qemu.org/docs/master/system/i386/hyperv.html) says enabling Hyper-V enlightenments changes the exposed identification to Hyper-V while moving KVM identification to leaves `0x40000100..0x40000101`. Consequently, `Microsoft Hv` is not evidence that Windows' own hypervisor has started. `hv-vendor-id` changes only the identification string, and setting it alone does not enable Hyper-V features. `hv-evmcs` is a performance/virtualization interface between KVM and nested Hyper-V; it is not a VF startup correction.

This investigation must distinguish:

1. L0 KVM permits nesting (`kvm_intel.nested=Y`). This is a host capability.
2. The guest CPU exposes VMX. This allows a guest hypervisor to start but does not prove it started.
3. Windows launches Hyper-V, including when VBS/Memory Integrity or Virtual Machine Platform causes that launch. Its graphics driver runs in the root partition of that immediate hypervisor while its GPU can remain an outer-assigned VF.
4. A further L2 guest actually runs. The reported graphics defect arises at Windows VF startup; no L2 GPU assignment is required to reproduce it.
5. A virtual IOMMU is exposed and the VF is passed onward into L2. That is a separate device-assignment topology with separate translation requirements.

## Proposed diagnostic matrix

Hold PF driver build, GuC firmware, VF count/resources, guest driver hash, VM machine type, PCI topology/BAR layout, and RAM fixed. Use an isolated guest snapshot. Record actual guest CPUID output and Windows hypervisor/VBS state after each cold start.

| Trial | VMX exposed | Windows Hyper-V/VBS actually running | L2 workload | Purpose |
|---|---|---|---|---|
| A | No | No | No | Establish ordinary VF startup baseline |
| B | Yes | No | No | Test VMX exposure separately from guest Hyper-V execution |
| C | Yes | Yes | No | Isolate immediate root-partition classification |
| D | Yes | Yes | Yes, CPU-only | Test nested activity after successful C |
| E | Yes | Yes | GPU assigned to L2 | Separate future vIOMMU/device reassignment test |

For each trial capture CPUID leaves 1, `0x40000000` through `0x40000006`, and outer KVM leaf range if present; PnP problem code; exact DxgKrnl status; PF GuC/VF lifecycle messages; whether PF/VF communication begins before failure. A result where A/B work, C fails with `STATUS_INVALID_PARAMETER`, and GPU communication does not newly fail strongly prioritizes the Windows branch over Xe memory-management changes. A/B failure demands ordinary VF initialization debugging first.

## What a correction should preserve

The most focused candidate is in the Windows driver's **earlier environment classification/state-resolution logic**, accounting for a passed-through VF in a nested root partition. Preserve the later validity checks and error paths. This is the direction supported by the public lab report and Intel's issue description; exact predicates and object fields still need independent per-version binary evidence.

Do not treat hiding VMX, turning off guest Hyper-V, removing VBS, or globally falsifying root-partition privileges as the product fix. Those can be controlled discriminators, but they change guest capabilities. A top-level QEMU vendor string also may not describe the CPUID interface ultimately returned by an active L1 Hyper-V to its own Windows root partition; confirm what the driver actually observes.

The cross-layer implication is useful for the original Xe study: an identical nested-only failure on a known-good i915 PF and an experimental Xe PF can be explained by a shared Windows guest-driver defect. It would not prove both PF implementations have the same missing hardware workaround. Conversely, fixing this Windows branch does not establish MTL/ARL Xe PF correctness for rendering, composition, reset, or multi-VF isolation.
