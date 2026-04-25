# MTL Xe SR-IOV Windows Glitch Investigation Notes

## Scope

This note summarizes the current investigation around `xe` KMD SR-IOV support
for Meteor Lake, and possibly Arrow Lake, using the `peigongdsd` experiment
branches around `upstream-mtl-cleanpath`.

The observed state is:

- Windows guest boots and has working graphics on the `xe` SR-IOV path.
- The remaining failures are small, stable graphics glitches, especially around
  taskbar or Explorer right-click menu rendering.
- Two reproducible failure paths were reported in PR #415:
  - Firefox video playback.
  - WinUI3 ContentIslands demo.
- Edge/Chrome video paths are reportedly better than Firefox.
- Linux VF render-node usage does not show the same problem.
- The same repo's `i915` SR-IOV KMD path works on the same platform.

The last point is important: this is probably not a generic Windows, firmware,
hardware, or "MTL SR-IOV is impossible" issue. It is more likely a contract or
policy difference between the working `i915` SR-IOV environment and the local
`xe` SR-IOV environment.

## Paths That Look Mostly Eliminated

The visible `peigongdsd` branch history already covers many of the obvious
suspects. These should not be chased again unless new logs show a direct
failure.

### GGTT Transport, Packet Shape, And Apply Ordering

Several branch families varied the MTL GGTT path:

- MMIO bootstrap versus steady-state relay.
- Literal updates versus coalesced updates.
- i915-like PTE coalescing.
- PTE sanitization.
- PF shadow tracking.
- Staged shadow apply.
- Direct synchronous PF apply.
- CPU apply versus engine-mediated apply.
- Direct GSM mapping on the PF.
- Immediate, deferred, and GuC-backed GGTT invalidation.
- Readback or shadow verification.

None of these experiments reportedly changed the shape of the Windows glitches.
That makes a primary GGTT packet/order/invalidate bug less likely.

Residual risk:

- A shared invariant across all GGTT experiments could still be wrong.
- This path should only return to the top if logs show dropped GGTT updates,
  wrong VF ownership bits, page faults, GuC CT failures, or mismatched shadow
  state during the exact repro.

### Runtime Register Exposure

The runtime register path was also explored.

Notable commits:

- `1a4aa7b` added MTL runtime/MMIO service tracing and included i915-like MTL
  runtime registers, including `0x38c1dc`, plus media forcewake around runtime
  snapshot when executed on a media GT.
- `c89f9e1` dropped that runtime snapshot experiment.
- `90befe5` reintroduced a cleaner i915-like MTL runtime register exposure
  mirror, though without `0x38c1dc` and without the same media-forcewake
  snapshot behavior.

If the `1a4aa7b` experiment was tested and did not alter the failure shape, then
the "missing runtime register" hypothesis is also weakened.

Residual risk:

- i915 forcewakes the media GT while refreshing runtime values for the service.
  The xe experiment only forcewoke when the runtime update was running on a
  media GT. This is not identical sourcing semantics.
- The risk is now lower, but exact VF-visible runtime values under working i915
  and failing xe may still be worth comparing once.

### Single Workaround Imports

Several branches tested individual i915/upstream-inspired policy ideas:

- MTL RCS/CCS GuC workaround path.
- Runtime register mirror.
- Sysmem scanout flush hook.
- Scanout PAT tracing/guarding.
- Scanout framebuffer alignment.
- VF CCS metadata logging.
- Direct stolen/DSMBASE style policy.
- Pagetable WC policy visibility.

Since none reportedly changed the failure shape, the remaining bug is less
likely to be one isolated missing knob. It may be a broader policy or capability
selection mismatch.

## Current Clues

### i915 Working Is The Anchor

The working `i915` path proves the platform can support this use case. The task
is therefore to identify which part of the i915 PF/VF environment makes Windows
choose a safe path, or makes the same path execute correctly.

Areas where i915 and xe may still differ:

- VF-visible capability shape.
- GuC ADS and workaround environment.
- Engine class exposure and scheduling behavior.
- Media/HuC/PXP/GSC state semantics.
- Compression/CCS/PAT policy for shared or composed surfaces.
- Cross-engine synchronization behavior.

### Repro Paths Point At Composition And Shared-Surface Behavior

Firefox video playback and WinUI3 ContentIslands are both likely to exercise
Windows presentation/composition paths, not just simple render submission.

Likely involved components:

- DWM composition.
- DirectComposition.
- Video present.
- Shared surfaces.
- Render-to-present transitions.
- Media/copy/render engine handoff.
- Possibly MPO or overlay-like decisions.

The fact that Linux render-node usage does not reproduce the issue is
consistent with this. Linux render-node tests do not exercise the same WDDM,
DWM, or Windows composition path.

### Small Stable Glitches Do Not Look Like Gross Address Translation Failure

The reported glitches are small and stable rather than catastrophic. That makes
these classes plausible:

- Cache or coherency mismatch.
- Compression metadata mismatch.
- Cross-engine synchronization error.
- Missing render/media workaround state.
- Bad feature selection by the Windows KMD.

It makes these classes less likely:

- Total GGTT update failure.
- Random VF memory ownership failure.
- General GuC communication failure.
- Basic Windows driver incompatibility.

## Stronger Remaining Hypotheses

### 1. Guest Composition Surface Cache/Compression/CCS Policy

The strongest remaining guess is that the faulty pixels come from guest
composition or video-present surfaces whose cache/compression state is not
handled like i915.

This may not be host scanout. The failing objects may never pass through the
host-side scanout code paths that were already instrumented.

Potential symptoms:

- Stable small artifacts.
- No page fault.
- No engine reset.
- Firefox and WinUI3 affected.
- Edge/Chrome less affected because they pick a different present/video path.

Useful debug direction:

- Make a deliberately conservative branch that disables or avoids compression
  and CCS for VF-visible surfaces.
- Force conservative PAT/cache policy broadly for VF-owned or VF-presented
  objects.
- If the glitches disappear, narrow from there.

This is a diagnostic experiment, not necessarily a final design.

### 2. Cross-Engine Synchronization

Firefox video and WinUI3 composition can involve media, copy, render, and DWM
composition handoff. The bug may be between engines rather than inside one
engine.

Useful debug direction:

- Disable Firefox hardware video decode and compare.
- Disable Firefox WebRender or DirectComposition if available and compare.
- Look for a toggle that changes both Firefox video and WinUI3 behavior.
- Try forcing paths away from copy/media engines if the Windows-side driver
  allows it.
- Watch for missing fences, semaphore behavior, or implicit sync assumptions
  differing between i915 and xe.

### 3. GuC ADS / Workaround Environment Difference

The MTL RCS/CCS workaround branch tested one targeted path, but i915 may still
provide a different aggregate workaround environment.

Useful debug direction:

- Compare the full GuC ADS/workaround programming between working i915 and
  failing xe.
- Do not only compare one workaround bit.
- Check whether Windows composition workloads use a context/engine combination
  whose workaround state differs between i915 and xe.

### 4. VF Personality Or Capability Mismatch

xe shapes VF device info centrally. i915 spreads equivalent assumptions through
service, runtime, and platform policy. Windows may be choosing a legal but bad
path because the xe VF advertises a subtly different capability set.

Useful debug direction:

- Compare Windows-reported GPU capabilities under i915 PF versus xe PF.
- Prefer negative tests: hide features from xe VF rather than expose more.
- Disable one class at a time:
  - media/HuC-related paths,
  - CCS/compression paths,
  - copy-engine-heavy paths,
  - advanced present/composition paths.
- If hiding a feature removes the artifact, the real bug is probably behind
  that feature path.

### 5. Later MMIO/Relay Requests During The Exact Repro

Boot-time runtime register queries are likely not the whole story. Windows may
issue later requests only during the failing composition/media path.

Useful debug direction:

- Capture relay/MMIO misses and unsupported opcodes during the exact Firefox
  and WinUI3 repros.
- Keep the log narrow:
  - unsupported opcode,
  - unsupported offset,
  - failed reply,
  - timeout,
  - relay error.
- Compare against working i915 under the same repro.

If there are no misses or relay errors during the repro, this hypothesis should
drop further.

## Refined i915-vs-xe Comparison

This section records the more concrete differences found after comparing the
working i915 path against the xe cleanpath and the visible peigongdsd debug
branches.

### GuC RCS/CCS Workaround Environment

i915 programs an MTL-specific RCS/CCS workaround environment:

- `intel_guc.c` sets `GUC_WA_RCS_CCS_SWITCHOUT` for GT IP 12.70-12.74 when the
  MTL RCS/CCS workaround parameter is enabled.
- `intel_guc_ads.c` emits the GuC workaround KLVs
  `GUC_WORKAROUND_KLV_SERIALIZED_RA_MODE` and
  `GUC_WORKAROUND_KLV_AVOID_GFX_CLEAR_WHILE_ACTIVE` for the same MTL range.
- `intel_guc_submission.c` also marks render/compute engines as using the
  hold-switchout workaround.

The xe cleanpath does not have the same baseline policy. Its GuC WA flag path
sets `GUC_WA_POLLCS`, `GUC_WA_HOLD_CCS_SWITCHOUT`, and dual-queue/pre-parser
related flags, but not the i915 MTL `GUC_WA_RCS_CCS_SWITCHOUT` path. Its ADS
workaround KLV list also does not include the two i915 MTL KLVs above.

However, peigongdsd commit `0526c5a` on the `upstream-mtl-rcs-ccs-wa` branch
appears to import exactly this missing xe-side path:

- Adds `GUC_WA_RCS_CCS_SWITCHOUT`.
- Adds the two missing GuC workaround KLV IDs.
- Adds MTL 12.70-12.74 gating.
- Emits the same two ADS workaround KLVs.

Interpretation:

- This is a real i915-vs-xe difference in the cleanpath branch.
- If `0526c5a` was tested on the same Windows repro and did not change the
  failure shape, then this exact missing-WA explanation is probably not the
  root cause.
- It is still worth verifying that the branch actually ran on the intended GuC
  version and that the KLVs were emitted, because otherwise the experiment may
  have been structurally correct but inactive.

### Cache, PAT, And Surface Coherency

The broader cache/coherency model differs more substantially.

i915 uses an object-domain model:

- Render writes can mark an object `cache_dirty`.
- Display pinning changes the whole object to WT or uncached.
- Scanout preparation flushes dirty cachelines.
- The cache level is treated as a global object property across VMAs.
- The code explicitly tries to keep scanout coherent by making non-MOCS GPU
  access use the same conservative cache policy.

xe uses a BO/PTE/PAT-oriented model:

- Display GGTT and DPT mappings use `XE_CACHE_NONE`.
- Non-dGFX scanout and page-table BOs can be forced to write-combined CPU
  mappings.
- The transient-display-flush helper is aimed at Xe2/dGFX-style transient L3
  cases and returns early on MTL.

Interpretation:

- The host display scanout path may not directly touch the failing Windows guest
  surfaces, so scanout-only instrumentation is not enough.
- The interesting question is whether VF-owned Windows DComp/video/WinUI shared
  surfaces get cache/PAT/MOCS/compression treatment equivalent to the working
  i915 environment.
- This remains the strongest surviving class of guesses because the symptom is
  stable pixel corruption without obvious address-translation failure, engine
  reset, or GuC transport failure.

Debug direction:

- Compare actual PTE PAT/cache bits for guest surfaces under the failing repro,
  not only host scanout buffers.
- Add a deliberately conservative diagnostic branch that forces VF-visible
  system/TT/user-present surfaces away from risky cached/compressed paths.
- Judge the experiment only by whether the visual failure changes; performance
  does not matter for this test.

### Flat CCS Is Probably Not The Main MTL Path

The earlier "CCS metadata" guess should be narrowed.

On the MTL cleanpath descriptor, SR-IOV is enabled but `has_flat_ccs` is not set.
The xe VF flat-CCS probe also exits early for SR-IOV VF. The VF CCS migration
helper only becomes active when `xe_device_has_flat_ccs()` is true.

Interpretation:

- For MTL, the specific flat-CCS/VF-CCS-migration path is probably inactive.
- Do not spend much more time on `xe_sriov_vf_ccs.c` unless logs prove that
  path is running.
- This does not eliminate cache/compression/coherency generally. It only lowers
  the priority of the flat-CCS metadata sub-hypothesis.

### Runtime Registers And MMIO Relay

i915 exposes a wider MTL runtime register list than xe cleanpath, including
registers such as `0xA26C`, `0x44074`, `0x10100C`, `0x116c68`, `0x138010`,
`0x389140`, and `0x38C1DC`.

i915 also wraps MMIO relay processing in a runtime PM wakeref. The xe cleanpath
processes the MMIO relay without an equivalent guard around
`mmio_relay_process`.

peigongdsd commit `1a4aa7b` appears to have tested this class:

- Adds MTL runtime/MMIO service tracing.
- Adds i915-like runtime registers including `0x38C1DC`.
- Adds runtime PM protection around xe MMIO relay processing.
- Adds media-GT forcewake behavior for the runtime snapshot case.

Interpretation:

- The cleanpath difference is real.
- If `1a4aa7b` was tested and there were no missing-offset hits and no visual
  change, then this path should be demoted.
- One residual mismatch remains: i915 forcewakes media GT while refreshing
  runtime values for the service, while the xe experiment forcewoke only when
  the runtime update path was executing on a media GT. This is probably not the
  first thing to chase, but it is not a byte-for-byte behavioral match.

Debug direction:

- During the exact Firefox and WinUI3 repros, log only late MMIO relay misses,
  unsupported opcodes, failed replies, and timeouts.
- If the log stays quiet during visible glitches, drop this hypothesis further.

### PF VF Configuration KLV Shape

i915 and xe both push the basic VF GuC configuration, but the shape is not
identical.

i915 always emits:

- GGTT start and size if allocated.
- Begin context ID and number of contexts.
- Begin doorbell ID and number of doorbells.
- Exec quantum.
- Preempt timeout.
- Thresholds.
- Optional tile mask.

xe emits mostly the same logical data, but:

- Begin context and begin doorbell are conditional on detailed config and
  nonzero counts.
- LMEM size may be emitted when present.
- Media GT config explicitly takes GGTT config from the primary GT.

Interpretation:

- This is a concrete contract difference, but it is less directly aligned with
  "tiny stable graphics corruption" than cache/coherency or GuC workaround
  state.
- It is still worth dumping the final KLV streams from working i915 and failing
  xe and comparing them byte-for-byte for the same VF.
- If quantum, preempt timeout, thresholds, or media-GT GGTT sourcing differ, it
  could affect present/composition scheduling, but it is not currently the
  leading theory.

### Linux VF Device Info Is Not The Windows Contract

One earlier line of thought was comparing xe VF-side `vf_update_device_info()`
style shaping. That is useful for Linux VF behavior, but it does not directly
explain Windows guest behavior unless the same capability is communicated
through the PF/Guc/PCI/device contract that Windows actually sees.

Interpretation:

- For Windows, prioritize PF-provided GuC config, runtime relay behavior, BAR
  layout, PCI-visible properties, and hardware policy.
- Linux-only VF-side capability shaping should not be treated as proof of what
  Windows sees.

## Visible Previous Debug Efforts

This section summarizes the peigongdsd-visible debug history across the MTL
branches. The purpose is to avoid re-testing paths that were already varied
without changing the observed Windows glitch shape.

### Base Bring-Up And Platform Enablement

The initial bring-up made MTL usable enough for the current Windows guest state.

Relevant commits:

- `0bbf46a` / `ee32c8e`: enabled MTL SR-IOV in xe and added GSC/PXP handling.
- `e74cb07` / `0286b13`: held GSC forcewake during MTL VF gating.
- `b2e47b6`: added noisy SR-IOV GSC tracing.
- `e832066`, `5527108`, `46c1d51`: added PF/VF FLR state tracing and
  snapshots.
- `9ecfc53`: dispatched VF FLR across multi-GT.
- `11d4dfb`, `abda595`: removed and then restored SR-IOV debug noise while
  narrowing which diagnostics were still needed.

What this tested:

- Whether MTL PF/VF bring-up needs explicit GSC/PXP sequencing.
- Whether VF enable/disable and FLR lifecycle were obviously broken.
- Whether multi-GT FLR dispatch was missing.

Current interpretation:

- These changes are part of the foundation. They made the branch functional,
  but they do not explain the remaining small rendering artifacts by themselves.

### MMIO Relay, Runtime Registers, And Relay Diagnostics

Several commits built and instrumented the VF/PF MMIO relay service.

Relevant commits:

- `70aa4bd`: handled G2H MMIO relay service for SR-IOV.
- `e90fba7`: added `VF2PF_UPDATE_GGTT32` relay support.
- `2365620`: fixed relay build warnings.
- `5e99db2`: fixed the GGTT shadow helper include after the shadow tracking
  work landed.
- `3e70dbf`: restored MMIO relay trace debugfs.
- `4b38666`: instrumented MTL/ARL relay and VF MMIO paths.
- `0c9f8a4` / `dfc1a1d`: unsuppressed relay diagnostics.
- `1a4aa7b`: traced MTL runtime and MMIO service paths, added i915-like runtime
  register coverage including `0x38c1dc`, and added runtime PM protection
  around xe MMIO relay processing.
- `c89f9e1`: dropped the MTL runtime snapshot experiment.
- `90befe5`: mirrored i915 MTL runtime register exposure again in a cleaner
  branch.

What this tested:

- Missing runtime register replies.
- Unsupported MMIO relay opcodes or offsets.
- Whether relay service needed runtime PM protection.
- Whether i915-like MTL runtime register coverage changed Windows behavior.

Current interpretation:

- This weakens the "one missing runtime register" explanation.
- It does not fully eliminate late relay issues unless the exact Firefox and
  WinUI3 repros were run with narrow miss/error logging enabled.
- If there are no late relay errors during visible glitches, this path should
  drop further.

### GGTT Transport, Packet Shape, Shadowing, And Apply Timing

The largest debug area was the MTL VF GGTT path.

Relevant commits:

- `ec0f9b9`: used relay for steady-state VF GGTT updates.
- `1dceebf`: kept MMIO bootstrap and delayed GGTT relay.
- `0fb82b6`: scoped the MTL GGTT path and logged transitions.
- `996c7e6`: used explicit MMIO GGTT bootstrap on MTL VF.
- `0a3545f`: parsed MMIO GGTT relay responses on MTL.
- `581ea7a`, `4f7a59b`, `13ce808`, `4cee2b9`: added PF shadow tracking,
  fixed build fallout, and staged MTL PF GGTT apply through shadow.
- `297409f`, `a7543fa`: deferred VF GGTT invalidation out of the G2H worker and
  added a runtime-PM guard around deferred GGTT invalidation.
- `8022280`: sanitized PF VF GGTT PTE updates.
- `9b39bc6`: dropped the no-op PTE sanitize experiment.
- `e28ee35`, `244bdbc`, `d886462`, `a917143`, `6485483`: tried bind-engine or
  upstream bind queue based GGTT flush/apply sequencing.
- `0b67ed3`: kept MTL VF GGTT updates on CPU apply.
- `89bdb7f`, `6e27a95`, `9374be0`, `a229c16`: tried synchronous shadow apply
  and async bootstrap variants, then reverted them.
- `c9ff841`: tested MTL foundation GGTT paths.
- `d713541`: tried i915-like VF GGTT PTE coalescing.
- `168f20e`: reverted the i915-like coalescing experiment from cleanpath.
- `5efe0aa`, `73c181b`, `0e1e4e1`: forced literal-only or literalized MMIO
  bootstrap/VF GGTT updates.
- `4c58eef`, `c2e6132`, `9abcb52`, `17a5203`: forced or validated direct
  synchronous PF GGTT apply.
- `b1936f5`, `728d8fa`: tried i915-style direct GSM/DSMBASE stolen access.
- `2d9c528`: verified staged shadow GGTT applies.
- `42502ce`: validated GuC-backed GGTT invalidation.
- `395bdee`: reverted the GuC-backed invalidation experiment.
- `43633f8`, `6320862`, `3f80cca`: traced deferred invalidation, overlapping
  update ranges, and GGTT packet semantics.
- `a05e5be`, `eaf6b5d`: added comparable i915 GGTT lifecycle/packet tracing.
- `74549de`: resanitized VF resources before FLR finish.
- `1d297d7`: trimmed MTL GGTT validation scaffolding.

What this tested:

- MMIO bootstrap versus relay transport.
- Literal PTE updates versus coalesced updates.
- PF shadow tracking versus direct apply.
- Synchronous versus deferred PF apply.
- CPU apply versus bind-engine apply.
- Direct GSM/DSMBASE style GGTT access.
- GGTT invalidation method and timing.
- Packet semantics compared with i915.
- Readback/shadow verification and overlap tracing.

Current interpretation:

- A primary GGTT transport, packet shape, PTE apply ordering, or invalidation
  bug is now less likely because many independent variations did not alter the
  artifact shape.
- A shared invariant across all GGTT attempts could still be wrong, but it
  should not be the default next target unless logs show lost updates, wrong VF
  ownership bits, page faults, or stale shadow state during the exact repro.

### Display, Scanout, PAT, And Host-Side Dataflow Validation

Several branches investigated whether the issue was in host display scanout or
local PAT/flush handling.

Relevant commits:

- `01d3531`: surfaced pagetable WC policy at runtime.
- `a342f77`: honored scanout framebuffer alignment in GGTT pinning.
- `5a03129`: added validation logs for MTL display dataflow.
- `38100d9`: traced scanout PAT state across bind and madvise.
- `57eceee`: added a sysmem scanout flush hook.

What this tested:

- Whether host scanout alignment was wrong.
- Whether host scanout PAT state was visibly inconsistent.
- Whether flushing sysmem scanout changed the artifacts.
- Whether page-table WC policy was active as expected.

Current interpretation:

- These weaken a narrow host-scanout explanation.
- They do not fully test Windows guest DComp/video/WinUI shared-surface
  cache/PAT/MOCS/compression behavior, because those guest surfaces may never
  pass through the host scanout code that was instrumented.

### GuC Workaround Validation And MTL RCS/CCS WA Import

The GuC workaround path was investigated directly.

Relevant commits:

- `d4005e1`: logged MTL workaround validation state.
- `0526c5a`: added the xe MTL RCS/CCS workaround path matching the notable
  i915-specific MTL GuC WA difference.

What this tested:

- Whether xe was missing the i915 MTL `GUC_WA_RCS_CCS_SWITCHOUT` environment.
- Whether the two i915 ADS workaround KLVs
  `GUC_WORKAROUND_KLV_SERIALIZED_RA_MODE` and
  `GUC_WORKAROUND_KLV_AVOID_GFX_CLEAR_WHILE_ACTIVE` matter for the glitch.

Current interpretation:

- This was one of the strongest clean i915-vs-xe deltas.
- If the `0526c5a` branch was tested with the exact repro and the KLVs were
  confirmed active, this exact missing-WA theory is mostly eliminated.
- Broader GuC ADS/workaround differences can still be compared, but not as a
  single missing RCS/CCS WA guess.

### VF CCS Metadata And Migration Logging

The CCS metadata path was also touched.

Relevant commits:

- `0424d6d`: logged VF CCS metadata flow.
- `1ef7555`: included SR-IOV printk helpers in the migration path.

What this tested:

- Whether VF CCS metadata migration/logging showed an obvious issue.

Current interpretation:

- For MTL specifically, flat CCS appears likely inactive because the MTL device
  descriptor does not set `has_flat_ccs`, and VF flat-CCS probing exits early
  for SR-IOV VF.
- This makes the specific flat-CCS/VF-CCS-migration path a weak lead unless logs
  prove it is active.
- General compression/cache/coherency remains a separate question.

### Documentation And Study Branches

There are documentation commits that record the cleaned state and map prior
experiments.

Relevant commits:

- `f60dff2`: summarized MTL cleanpath delta versus upstream.
- `02f12bd`: added MTL/ARL SR-IOV study pack.
- `336d049`: mapped MTL i915 deficiencies to local experiment commits.

Current interpretation:

- These docs are useful context, but the remaining investigation should stay
  centered on the exact working i915 versus failing xe contract differences.

## Paths Left To Debug Further

Based on the branch history and the i915-vs-xe comparison, the remaining work
should be narrower than "try another GGTT fix".

### 1. VF Guest Surface Cache/PAT/MOCS/Compression Contract

This is the strongest remaining path.

Why it remains:

- The visible artifacts are small, stable, and composition/video related.
- GGTT transport and runtime-register paths have been heavily varied.
- Host scanout instrumentation does not prove anything about Windows guest
  DComp/video/WinUI shared surfaces.
- i915 has an object-level coherency model that is not obviously equivalent to
  xe's BO/PTE/PAT model for VF-owned guest surfaces.

Next debug:

- Capture the actual PAT/cache/MOCS/PTE attributes for VF-owned surfaces during
  the Firefox and WinUI3 repros.
- Identify whether the affected surfaces are system memory, TT, GGTT-mapped,
  compressed, or crossing render/media/copy engines.
- Build one deliberately conservative diagnostic branch that forces VF-visible
  user/present-like system/TT surfaces to the safest cache/PAT/compression
  policy available.
- If the artifact changes, narrow from cache/PAT versus compression versus
  cross-engine ownership.

### 2. Windows Capability Selection Under i915 PF Versus xe PF

This is the next most important path because the Windows driver may be choosing
a different present/composition path under xe.

Why it remains:

- i915 works in the same repo and same platform.
- Linux render-node tests do not exercise WDDM/DWM/DirectComposition behavior.
- Firefox video and WinUI3 ContentIslands are both capability-sensitive.

Next debug:

- Compare Windows-reported graphics capabilities under working i915 SR-IOV and
  failing xe SR-IOV.
- Collect Firefox `about:support`, Edge/Chrome `chrome://gpu`, DxDiag, WDDM
  feature level, overlay/MPO support, media decode, DComp, and D3D11 video
  status.
- Prefer negative experiments that hide or disable feature buckets from xe VF:
  media decode, overlay/MPO, compression, copy-heavy paths, or advanced present
  paths.
- Treat any change in artifact shape as a strong signal about the chosen Windows
  path.

### 3. Final GuC VF Config KLV Byte Comparison

This path is less likely than coherency, but it is concrete and still cheap to
verify.

Why it remains:

- i915 and xe encode mostly the same VF configuration, but not byte-for-byte in
  code structure.
- xe has media-GT GGTT sourcing logic and conditional begin context/doorbell
  emission.
- Scheduling thresholds, quantum, or media-GT config shape could affect
  composition/present timing without causing boot failure.

Next debug:

- Dump the final GuC VF config KLV stream for the same VF under i915 and xe.
- Compare GGTT start/size, context range, doorbell range, exec quantum, preempt
  timeout, thresholds, tile/media-GT handling, and any omitted tags.
- If they differ, test the smallest possible xe change that makes the KLV stream
  match i915's behavior.

### 4. Late MMIO Relay Misses During Exact Repro

This is not a leading theory anymore, but it is still a useful sanity check.

Why it remains:

- `1a4aa7b` and `90befe5` weaken the missing-runtime-register theory.
- They do not prove there are no late relay misses during the exact Firefox and
  WinUI3 failure windows unless those repros were logged narrowly.

Next debug:

- Log only unsupported opcodes, unsupported offsets, failed replies, relay
  errors, and timeouts during the exact repro.
- Avoid high-volume tracing.
- If the log is quiet while the artifact appears, stop chasing relay/runtime.

### 5. Full GuC ADS/WA Diff, But Only After Confirming The RCS/CCS Import

This is a secondary path.

Why it remains:

- The exact i915 MTL RCS/CCS WA delta appears to have been imported by
  `0526c5a`.
- If that branch did not change anything, a single missing GuC WA is less
  likely.
- The full ADS/workaround environment may still differ in aggregate.

Next debug:

- First confirm the `0526c5a` KLVs and flags were actually emitted with the GuC
  version used in testing.
- If confirmed, compare the full ADS/WA state between working i915 and failing
  xe.
- Do this after the surface policy and capability-selection work, not before.

### 6. Return To GGTT Only On New Hard Evidence

GGTT should not be the default next area.

Return to GGTT only if one of these appears during the exact repro:

- Dropped or failed VF GGTT update.
- Wrong VF ownership bits.
- GGTT shadow/readback mismatch.
- Page fault tied to the artifact.
- GuC CT failure or relay timeout.
- Difference between i915 and xe final PTE value for the same guest mapping.

## Suggested Next Debug Plan

### Step 1: Establish A Minimal Windows-Side Feature Matrix

For Firefox:

- Hardware video decode on/off.
- WebRender on/off.
- DirectComposition on/off if available.
- D3D11 video path on/off if available.

For Windows:

- MPO/overlay disabled if possible.
- Compare right-click menu and WinUI3 ContentIslands after each change.

Goal:

- Find whether Firefox video and WinUI3 glitches share one feature dependency.

### Step 2: Compare Working i915 And Failing xe At The Capability Level

Collect from the Windows guest:

- Firefox `about:support`.
- Chrome/Edge `chrome://gpu`.
- DX diagnostics or equivalent capability reports.
- Any Intel driver panel or WDDM feature report that exposes media, overlay,
  decode, and presentation capability differences.

Goal:

- Identify what Windows believes differs between i915 SR-IOV and xe SR-IOV.

### Step 3: Run One Brutal Conservative xe Experiment

Make xe intentionally less capable for VF:

- Disable or avoid CCS/compression for VF surfaces.
- Force conservative cache/PAT for VF-visible surfaces.
- Optionally restrict media/copy paths if practical.

Goal:

- Determine whether this is a coherency/compression/sync class bug.

This experiment should be judged only by whether the visual failure shape
changes. It does not need to be performant or architecturally final.

### Step 4: Only Then Narrow Mechanically

If the conservative experiment changes the failure:

- Re-enable one feature bucket at a time.
- Separate cache/PAT from compression/CCS.
- Separate media/copy/render synchronization from pure render.

If the conservative experiment does not change the failure:

- Move back to capability exposure and late relay/MMIO requests.
- Compare i915 and xe GuC ADS/workaround state more completely.

## Working Theory

The current best theory is:

> xe MTL SR-IOV is functionally close enough to boot Windows and render normally,
> but differs from i915 in the policy environment used by Windows composition,
> video-present, or shared-surface paths. The remaining glitches are more likely
> due to cache/compression/cross-engine synchronization or VF capability
> selection than GGTT transport or boot-time runtime register exposure.

This theory fits the current evidence:

- i915 works on the same platform.
- xe graphics mostly works.
- The failures are small and reproducible.
- Linux render-node use does not reproduce them.
- GGTT and runtime-register experiments did not change the failure shape.
