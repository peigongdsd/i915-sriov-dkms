# MTL VF PTE planning and rollback diagnostic, v3

Branch: `codex/xe-mtl-vf-pte-plan-v3`, based on tested v2 `fe1ff86`.
Live marker: `diagnostic=mtl-pte-plan-v3`.
Read [the first-mapping analysis](xe-mtl-first-mapping-analysis.md) for the
evidence, alternatives and remaining native enablement requirements.

## Scope

Advance only the observed 4 KiB system-memory BO through existing validation
and GGTT allocation. Calculate the first DMA/PTE entry using the same cursor
and encoded flags as the regular mapper, log it, and remove the unused
software node. Return `-EOPNOTSUPP` through ordinary cleanup.

No PTE write, PF relay, clear or invalidation is issued for the diagnostic
mapping. The code explicitly removes the DRM allocator node, frees it and
sets the BO's GGTT-node pointer to NULL. It does not call the usual removal
helper, which writes scratch PTEs while the GGTT is online. The negative return skips the usual
post-map invalidation. Other BO sizes/placements and the transform path
retain an earlier rejection.

This is not a forwarding implementation, and a good result does not prove
that the BAR write caused the original host hang. The source-level analysis
supports that hypothesis; the failing hardware instruction remains unknown.

## Build and test handoff

Preserve generation 204 and host PF `02acd04`. Reuse the existing Linux 7.3.3
guest kernel and local flake inputs; replace only its out-of-tree driver
source. Build matching Xe/compatibility modules at the supplied commit,
append `-g` to existing module compiler flags, and retain unstripped `xe.ko`.
Do not change host pins, modules or boot entries. Ensure the guest initrd
does not load v1/v2 or the production guarded module first.

Record source SHA, guest kernel identity, module path, SHA-256, vermagic and
srcversion. Require the live v3 identity, not merely the shared package
version string. A local Linux 7.3.4 build is not an exact guest-kernel build.

Use one VF already released by Windows and keep host ownership `vfio-pci`.
Verify current host/guest state and isolate binding-rule races. Stream guest
serial and host logs to an independent receiver before probing. Host-local
captures survived v1/v2 but cannot be relied on for a whole-host hang. If
independent capture is unavailable, prepare the build and report the blocker.

Use guest `loglevel=7`. Reuse the existing GDB setup, loading new unstripped
module symbols at this run's section addresses. The breakpoint is
`xe_ggtt_vf_probe_pte`. At entry, inspect the BO, its GGTT node and PTE flags;
step within the software-only helper or use its log for the calculated DMA
address and full candidate PTE. Do not modify returns, bypass the guard or
call the normal mapper. An unexpected BO may instead hit
`xe_ggtt_vf_probe_stop`; capture that result and stop.

Expected distinguishing output:

```text
VFPROBE: diagnostic=mtl-pte-plan-v3 before VF_CAP ...
... discovery and early GGTT setup complete ...
VFPROBE: before memirq initialization
VFPROBE: before BO validation
VFPROBE: BO validation returned 0
VFPROBE: PTE plan only, ggtt=... relative=... dma=... pte=... pat=...
VFPROBE: BAR offset=... size=... in_bar=... writer=...
... intentional diagnostic stack ...
VFPROBE: unused GGTT node removed; no PTE write or invalidation issued
VFPROBE: memirq initialization returned -95
... Xe probe failure -95 ...
GUEST_ALIVE_AFTER_PROBE
```

If allocation chooses relative offset zero, the predicted GGTT address is
`0x7ec00000` and the BAR offset is `0xbf6000`. Record actual values; do not
force the allocator to match the prediction. `in_bar=1` establishes only a
byte-range check, not permission to access the VF's GGTT window. DMA and PAT
values must come from this run. Do not infer either from an optimized-out
GDB argument, or treat a zero VFID field as proof of a malformed VF PTE.

After this single probe, verify guest responsiveness, normal shutdown, host
health and VF1 still bound to `vfio-pci`. Record all cleanup warnings,
particularly DRM allocator or TTM failures. Do not repeat a failed run or
automatically restart Windows. Return complete logs and the last completed
checkpoint, not only the final -95.

The useful result is a concrete candidate PTE plus verified rollback and
continued responsiveness. If validation or allocation fails earlier, that
result is useful too and must not be relabeled a BAR-access failure.

## Local validation

Xe and `intel_sriov_compat` built successfully against the available Linux
7.3.4 build tree with GCC 16.2.0 and `KCFLAGS=-g`. The build log contained
no compiler warnings or errors. The unstripped Xe module contains
`.debug_info`, `.debug_line` and `xe_ggtt_vf_probe_pte`. The driver delta
passes `checkpatch.pl --no-tree --no-signoff`, and `git diff --check` passes.
No module was loaded and no hardware probe was performed here. Rebuild for
the target's exact Linux 7.3.3 kernel before the proposed guest experiment.
