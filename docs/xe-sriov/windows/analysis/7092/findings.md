# Intel Windows 32.0.101.7092: ADL-P nested-Hyper-V investigation

Inspected 2026-10-02. This is independent analysis of Intel's downloaded current ADL-generation package, with isolated execution of its original classifier. It is not a Windows/GPU startup test.

## Identity and relevance

The official 11th–14th-generation download supplied `gfx_win_101.7092.exe`; its published SHA-512 was verified before extraction. The package INF specifies `DriverVer=09/03/2026,32.0.101.7092`, matches ADL-P `8086:46A6`, and installs `igdkmdn64.sys`. The inspected module is 51,609,984 bytes, PE image base `0x140000000`, and SHA-256 `454624942bf9a79a75fd1bfe6c6a2f8d499aabef45cb4268a1353d527902d098`. Its product/file version is independently `32.0.101.7092`.

No driver was modified, installed or loaded. PDB metadata is preserved in `metadata.json`; private symbols were not recovered. All addresses below are image RVAs and apply only to the hashed module.

## Original classifier and isolated execution

Function `0xB3A0–0xB660` initializes adapter fields `+0xF28 = 3` and `+0xF2C = 0`. The second field is a hypervisor-vendor enumeration based on comparison of the CPUID vendor string. The first is an environment-classification state, a descriptive inferred name rather than a recovered Intel symbol.

The classifier tests CPUID leaf 1 ECX bit 31, reads the hypervisor vendor from leaf `0x40000000`, and records VMware=2, Microsoft=3, Xen=4, KVM=5, ACRN=6, other nonempty vendor=1. It checks extended-leaf availability and the stored uppercase CPU brand (`CORE`, `XEON`, or `INTEL`). Its caller at `0x20D80` constructs and uppercases that brand before calling the classifier at `0x21057`; the uppercase emulation input therefore models an actual caller contract.

For eligible Intel-brand inputs, non-Microsoft hypervisors clear state to zero. For Microsoft, it reads CPUID `0x40000003` EBX bit 12 (`CpuManagement`): set preserves state 3, clear produces zero. It never reads `0x40000004` in this routine, so the TLFS EAX bit 12 nested-partition indication does not distinguish the two Hyper-V root cases here.

`../emulate_7092_classifier.py` executes the original bytes under Unicorn, providing CPUID inputs and substituting only string/memory library calls, logging and stack-cookie checking. The expected original hash is asserted. Recorded results in `classifier-emulation.json`:

| Input environment | State `+0xF28` | Vendor `+0xF2C` |
|---|---:|---:|
| Bare metal | 3 | 0 |
| KVM | 0 | 5 |
| VMware | 0 | 2 |
| Hyper-V child, management clear | 0 | 3 |
| Hyper-V root, management set | 3 | 3 |
| Nested Hyper-V root, management set, nested indication available | 3 | 3 |

This confirms a classification distinction is absent, not that the driver necessarily fails every possible later startup path. Windows, GPU execution, MMIO and PF/VF communication were not simulated.

## Hardware VF detection does not always correct this state

The resource-initialization function `0x240E0–0x24D88` reads MMIO `0x1901F8` at `0x246C8`. It rejects all-ones and tests bit zero, then sets adapter `+0x56B98 = 2` at `0x24711`. Upstream Xe names this register/bit `VF_CAP_REG`/`VF_CAP`, providing an independent hardware definition for the inferred VF-mode field.

The following original control flow is explicit:

```text
if (hypervisor_vendor != 0 && environment_state == 0) OR vf_mode == 2:
    use the virtual/VF resource branch
    if vf_mode == 2 AND hypervisor_vendor == 0:
        hypervisor_vendor = 1
        environment_state = 0
```

At `0x24750`, a nonzero vendor jumps past the corrective state write. Thus an identified Microsoft vendor can retain state 3 even after hardware VF recognition succeeds. This is independently the same relevant shape found in MTL/ARL driver 9033, although offsets and initial state differ.

Other verified state consumers include:

- `0x24AC7–0x24ADC`: vendor present with state zero selects an 8 MiB resource value at `+0xC10`; the other path obtains a PCI-derived size. Whether that difference is harmful depends on actual resources and PCI values.
- `0x268D85–0x268DC6`: vendor/state gate a memory-size helper, but an explicit `vf_mode == 2` test bypasses that helper; do not attribute every such native-path read to VFs.
- `0x3D1C46–0x3D1C6D`: state zero clears two capability bits in a nested object; state 3 skips those clears. Exact public meanings of these bits were not recovered.

Validated instruction ranges are saved in `vf-init.asm`. `state-f28-xrefs.txt` is an exploratory index, not proof that every equal displacement denotes this adapter field: different objects reuse offsets and RIP-relative displacement coincidences occur.

## Evidence boundary and next diagnostic step

Intel's [KB 000102878](https://www.intel.com/content/www/us/en/support/articles/000102878/graphics.html) acknowledges nested-Hyper-V misclassification. [IGCIT #1394](https://github.com/IGCIT/Intel-GPU-Community-Issue-Tracker-IGCIT/issues/1394) contains a separate hardware-backed 8826/ARL report describing an earlier skipped state transition followed by `0xC000000D` and Code 43. [i915 issue #263](https://github.com/strongtz/i915-sriov-dkms/issues/263) reports ADL-P Code 43 after enabling WSL, with i915 as PF. These corroborate the category; neither substitutes for a 7092 hardware test.

This analysis has not traced the full 7092 chain to that reported pending-start state or proven a specific Code 43 path. In particular, finding another `0xC000000D` literal is insufficient: that status is used by many resource checks. A robust correction should preserve the real hypervisor interface/privileges and recognize a nested environment in the correct earlier transition; blindly bypassing a later guard or copying private offsets is not established as correct.

For discrimination, compare the same VF and hashed driver with VMX hidden, VMX exposed but guest Hyper-V disabled, and guest Hyper-V running before any L2 starts. A failure merely from VMX exposure and a failure only once Hyper-V runs are different phenomena. Capture the guest CPUID vendor, leaves `0x40000003`, `0x40000004`, and nesting-depth leaf where supported. These are proposed hardware tests, not performed results.
