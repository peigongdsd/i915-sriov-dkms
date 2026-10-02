# Intel Windows 32.0.101.9033: targeted MTL/ARL static analysis

Inspected 2026-10-02. The official Intel package was downloaded by the main research task and its SHA-512 checked against Intel's published value. No driver was installed or modified. This note analyzes the extracted kernel driver and emulates one CPU-only classifier; it does not claim a hardware reproduction.

## Image identity

- Package: `gfx_win_101.9033.exe`.
- Binary: `Graphics/igdkmdn64.sys`, 32,531,840 bytes.
- SHA-256: `2969ef18daf397b43353dd4ff465f52a8107fc1a612eab4a8cc2703dee919a4d`.
- PE version: `32.0.101.9033`.
- Preferred image base: `0x140000000`.
- CodeView PDB identity: GUID `854AAD1E-9060-43A2-8D3A-2251B4374C70`, age 1, `igdkmdn64.pdb`. The matching GUID/age request to Microsoft's symbol server returned HTTP 404; no PDB was obtained.
- INF directly matches MTL `7D45` / `7D55` and ARL-S `7D67` (plus other IDs). This is the current MTL/ARL product lane, not evidence about ADL-P's separate Windows driver lane.

## Confirmed classifier control flow

At image RVA `0xB680`, the driver initializes two adjacent 32-bit fields of its adapter object:

- `+0xE98 = 2`;
- `+0xE9C = 0`.

The first is an environment-classification state (semantic label inferred from its uses); the second is an observed hypervisor-vendor enum. Exact enum names are unavailable without symbols.

The function reads `CPUID.1:ECX[31]`. Without that bit it returns with `2,0`. With the bit, it reads the vendor string from leaf `0x40000000`, matches substrings, and assigns vendor IDs: VMware 2, Microsoft 3, Xen 4, KVM 5, ACRN 6, otherwise a nonempty unknown vendor 1.

It next requires the maximum extended leaf to reach `0x80000004` and looks for `CORE`, `XEON`, or `INTEL` in an uppercase CPU-brand string already stored at `+0x49370`. Failure to match leaves the initial state at 2. For an Intel-brand match:

- Non-Microsoft vendor clears `+0xE98` to zero.
- Microsoft vendor reads `CPUID.0x40000003` and tests **EBX bit 12** (`CpuManagement`). If clear, `+0xE98` becomes zero; if set it remains 2.
- No leaf `0x40000004` query occurs in this classifier, so its nested-hypervisor bit is not considered here.

Key RVAs: init `0xB6A2`; initial hypervisor test `0xB6C4`; Microsoft vendor assignment `0xB75F`; leaf `0x40000003` query `0xB867`; bit test `0xB8B0`; branch preserving state 2 `0xB8B4`; state-zero write `0xB8B6`.

These are descriptive reverse-engineering locations, not a binary modification prescription. Driver bytes were left intact.

## Isolated emulation result

The included `emulate_9033_classifier.py` executes the original function bytes under Unicorn with synthetic CPUID inputs and stubs only for imported `strncpy_s`, imported `strstr`, logging, and stack-cookie validation. The imports were confirmed through the PE import table. The result is recorded in `9033-classifier-emulation.json`.

| CPUID environment, Intel-brand CPU | `+0xE98` | `+0xE9C` | Nested leaf read? |
|---|---:|---:|---|
| No hypervisor bit | 2 | 0 | No |
| KVM vendor | 0 | 5 | No |
| Microsoft Hv, CpuManagement clear | 0 | 3 | No |
| Microsoft Hv, CpuManagement set, nested bit clear | 2 | 3 | No |
| Microsoft Hv, CpuManagement set, nested bit set | 2 | 3 | No |

An additional AMD-brand case leaves state 2 without querying `0x40000003`; that branch is directly visible but is not a diagnosis of the separate B50/AMD-host report.

This independently confirms that the classifier in **9033** does not distinguish a Microsoft Hyper-V root running on bare metal from a Microsoft Hyper-V root itself running inside another VM by inspecting the standard nested indication. It does **not** prove all later initialization paths remain broken in 9033: a later VF-specific correction could compensate, and a full Windows/GPU execution was not performed.

## Confirmed downstream uses and limits

The classifier is called at RVA `0x21D21` during an initialization function. The state is subsequently consumed in BAR/resource handling and other virtualization-related paths. Verified examples:

- RVA `0x25253–0x25294`: a nonzero hypervisor vendor together with state zero selects an 8 MiB resource policy, alongside a separate VF/device-mode override.
- RVA `0x254CF–0x25518`: the driver reads MMIO `0x1901F8`, rejects an all-ones read and checks bit 0, then writes `+0x45660 = 2`. Mainline Xe independently names this exact register/bit `VF_CAP_REG`/`VF_CAP` (`regs/xe_regs.h:62–63`). This confirms the field's value 2 denotes a detected VF, rather than guessing solely from surrounding strings.
- RVA `0x25522–0x25569`: the vendor/state pair affects resource handling; when the detected-VF field at `+0x45660` equals 2 and no vendor was found, this code sets unknown vendor 1 and clears the state to zero. For an already recognized Microsoft vendor, that corrective state write is skipped. So this image contains a hardware-VF correction that preserves recognized Microsoft state. **Platform limit:** the selector at `0x25403–0x25440` excludes internal MTL `0x4F8` and ARL `0x4F9` from this particular register-reading branch. It is not proof that this correction executes on MTL/ARL; other VF-detection paths were not exhaustively traced.
- RVA `0x37A340`: the vendor/state pair gates a registry-based device-ID override path.
- RVA `0x55F3F9–0x55F41E`: state zero clears two capability bits in a nested object; state 2 skips those writes.

Thus this is not merely a string-based suspicion: actual branches preserve or clear state, and the state is read by later code. The follow-up below establishes a conditional `STATUS_INVALID_PARAMETER` path in 9033, without asserting that it is identical to the community reporter's 8826 path or that the reporter's actual resource descriptors match our synthetic input.

## Relation to online observations

[IGCIT #1394, July 27 independent report](https://github.com/IGCIT/Intel-GPU-Community-Issue-Tracker-IGCIT/issues/1394#issuecomment-5088202869) reports version **8826**, ARL device `7D67`, nested Hyper-V, startup status `0xC000000D`, and a controlled successful experiment when an earlier internal state transition completed. [The reporter's follow-up](https://github.com/IGCIT/Intel-GPU-Community-Issue-Tracker-IGCIT/issues/1394#issuecomment-5089907090) attributes the error to earlier path selection leaving stale state, with a later guard behaving consistently. These are reported hardware findings, separate from our local 9033 static/emulation evidence.

The matching control-flow concern makes nested Hyper-V a concrete diagnostic branch for current MTL/ARL Code 43. It does not explain the user's older Xe-vs-i915 **composition corruption**: that guest already starts and renders. Nor can this 9033 result simply be transferred to ADL-P, which needs its own supported Windows driver binary and guest configuration checked.

## Reproducibility

- `inspect_9033.py`: identifies PE runtime functions containing CPUID and records disassembly plus relevant strings.
- `9033-cpuid-functions.txt`: raw local analysis output; linear disassembly of broad runtime ranges may include embedded data outside the specific classifier. Conclusions above use only validated instruction boundaries/control flow in the classifier and selected branches.
- `9033-hypervisor-state-xrefs.txt`: field-access candidates. Same numerical offsets in unrelated objects are not treated as equivalent state.
- `9033-initialization-snippets.txt`: exploratory initialization disassembly; not every displayed byte range begins at a function boundary.
- `emulate_9033_classifier.py` / `9033-classifier-emulation.json`: original classifier execution with controlled inputs; no system driver installation or patching.

The next useful confirmation is a Windows guest run with exact driver hash and CPUID capture, matched against Intel's nested-Hyper-V issue; the next static task would be to trace the complete VF startup transition/late guard or compare a known-good and failing version of the same product lane. Kernel GGTT rewrites cannot fix a purely guest-side environment classifier.

## Follow-up: a conditional startup rejection reproduced in original code

The device-ID dispatch at RVA `0x9450` sends MTL IDs `7D45`/`7D55` to `0x37F950`, which assigns internal platform `+0x72C = 0x4F8`; ARL ID `7D67` dispatches to `0x37FC20`, which assigns `0x4F9`. These are the driver's internal enum values, not graphics IP versions.

Resource-parser function `0x25080` starts with return status `0xC000000D`. For those MTL/ARL enum values, the final acceptance checks at `0x2597C–0x25A23` can clear the status if a recognized, non-unknown hypervisor has state zero, or if a separately collected memory-resource flag (`+0xC9C` bit 1) is set. A nonzero Microsoft environment state does not satisfy the first condition. The VF-mode flag `+0x45660 = 2` does not bypass this final check.

`emulate_9033_resources.py` executes the **original entire resource-parser function** with synthetic Windows CM descriptors and controlled object fields. Logging and a PCI-configuration helper are stubbed; all branch/state/status code remains original. For each of MTL and ARL, Microsoft vendor 3 and VF mode 2:

| Synthetic resource input | Environment state 0 | Environment state 2 |
|---|---|---|
| One 16 MiB memory resource | Success (`0`) | `0xC000000D` |
| Same resource plus second 256 MiB memory resource | Success (`0`) | Success (`0`) |

The second descriptor sets the alternate acceptance flag. This makes the dependence on both environment classification **and resource shape** explicit. It is not a proposal to invent an extra PCI BAR or fake hardware resources. No actual guest resource list has been obtained, so applicability to a particular guest remains to be verified. The single-resource tests execute no PCI helper at all because VF mode already selects the fixed GGTT resource policy; the only stubbed call on that path is logging.

Static caller flow connects this result to the same initialization sequence that invokes the classifier: parser call at `0xBFF1` → negative result at `0xC00A` → wrapper call at `0xC36E` and its `0xC378` check → wrapper returns `0xC000000D` at `0xC3A5` → initialization call at `0x21D95`, negative check at `0x21D9F`, and error path at `0x21DD0`. This is a concrete initialization-error path, although public symbols are unavailable and we do not assign the exported name `StartDevice` to the internal function solely from inference.

Evidence: `9033-resource-full.txt`, `9033-resource-end.txt`, `emulate_9033_resources.py`, and `9033-resource-emulation.json`. The earlier broad statement that a complete rejection chain was not established should now be read with this bounded refinement: **a conditional classification-to-resource-rejection chain is proven in 9033; identity with the 8826 report and occurrence on real hardware are unproven.** None of this diagnoses the already-started Windows composition corruption in the older Xe MTL experiments.
