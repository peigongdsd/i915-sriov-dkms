# ADL-P render indirect-context experiment

2026-10-02. This is an isolated Linux Xe experiment motivated by the user's actual captures, not a demonstrated Windows Code 43 fix. MTL work remains paused.

## Why this change is now testable

The supplied **pre-crash** PF default RCS context has an indirect-context pointer but register `0x21c8` is zero. A later saved host LRC also has zero there. Working i915 initializes the Gen12 render field to `0xd` in bits 15:6, giving register value **`0x340`**. The recent Xe discussion identifies the same zero default-image observation after an earlier change stopped explicit programming. [Intel review](https://lkml.rescloud.iu.edu/2609.3/17001.html), [author's default-context follow-up](https://www.mail-archive.com/dri-devel@lists.freedesktop.org/msg640961.html).

This is stronger evidence for a controlled context experiment than generic Code 43. It remains weaker than a causal reproduction: the retained dump follows the first GT reset, the first CAT queue's context was not captured, and Windows constructs its own VF contexts. A PF correction can affect shared engine/default-context behavior without directly changing Windows' LRC construction.

## Exact code and scope

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

## Validation performed

Both the diagnostic-only revision and the combined experiment compiled and relinked the complete Xe module successfully against the same Linux **7.2.8** headers. `MODPOST` passed, and the compatibility-module target remained valid. Incremental compilation reused unchanged objects from the previously successful full build. Both changes received an independent static review of field encoding, platform/class gates, call-path coverage, queue/LRC lifetime and lock use.

The headers-only build environment lacked `vmlinux`, so BTF generation was skipped; it also reported the existing pahole-version warning. These are retained in the build logs. No module was loaded by the assistant and no hardware outcome is claimed.

Records: [diagnostic build](patches/adlp/cat-diagnostics-build-verification.json), [experiment build](patches/adlp/indirect-offset-build-verification.json), [diagnostic log](patches/adlp/build-cat-diagnostics-7.2.8.log), [experiment log](patches/adlp/build-indirect-offset-7.2.8.log).

## How to test on the ADL-P host

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

## Interpret each outcome separately

| Observation with verified offset 0x340 | Conclusion and next action |
|---|---|
| Host stays clean and Windows starts | Evidence for this narrow fix; repeat matched diagnostics-only versus offset boots before promoting it |
| Host faults disappear but Windows remains Code 43 | Host context issue and guest startup failure are separate; retain this result and investigate guest NTSTATUS/service sequence |
| Host still reports DMA/CAT errors | Use the new first-CAT owner/LRC fields to locate the failing object/domain; offset alone is insufficient |
| No VM is running and native graphics regress | Roll back and retain the first host capture; this experimental context change is unsuitable as-is |

The second and third outcomes remain plausible. Missing service negotiation, clock-register compatibility and nested Windows classification are still separate hypotheses; none is established by the post-FLR snapshots. This branch is a measured, minimal experiment toward a Linux fix, not a declaration that the remaining guest problem is solved.
