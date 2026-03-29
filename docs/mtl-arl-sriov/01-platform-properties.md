# Platform Properties: What Intel Says Is Special About MTL / ARL

## 1. Repository Lanes and Why They Matter

For this study, the relevant Intel source lanes are different:

- `i915` SR-IOV history lives in Intel's old LTS development line,
  especially `intel/linux-intel-lts`.
- `xe` history is spread across upstream `drm-xe-next`, Intel's
  mainline-tracking integration, and the Intel mailing lists.

That split matters because Intel did not move one complete SR-IOV design from
`i915` into `xe`. It moved platform support incrementally, often under
different abstractions.

## 2. MTL Is Not Treated As "Just Another Gen12 Variant"

The strongest message from Intel-side code and commit traffic is that MTL is
not handled as a routine continuation of older integrated GPUs.

### 2.1 Stolen Memory Access Is Distrusted On MTL

The clearest upstream `i915` statement is the MTL stolen-memory series:

- `drm/i915: Bypass LMEMBAR/GTTMMADR for MTL stolen memory access`
- commit family from Ville Syrjälä's stolen-memory series
- source thread:
  `https://www.spinics.net/lists/intel-gfx/msg342210.html`

That thread says the quiet part out loud:

> Attempt to fix the mess around stolen memory, especially on MTL
> with it's special (and apparenly broken) not-actually-lmem stolen.

The current `i915` code matches that message:

- `drivers/gpu/drm/i915/i915_utils.c`
  - `i915_direct_stolen_access()`
- `drivers/gpu/drm/i915/gem/i915_gem_stolen.c`
- `drivers/gpu/drm/i915/gt/intel_ggtt.c`

The policy is:

- MTL does not blindly trust BAR-backed access to stolen memory.
- `i915` prefers direct GSM/DSM access when firmware explicitly allows it.
- the policy is disabled for guests and SR-IOV VFs.

This is not an SR-IOV quirk. It is a platform statement: MTL stolen access is
special enough that the driver chooses a different mechanism.

### 2.2 MTL Gets A GGTT "Binder" Story, Not Generic VF PTE Writes

Current `i915` expresses this through `i915_ggtt_require_binder()` in
`drivers/gpu/drm/i915/gt/intel_gtt.c`.

The rule is:

- if direct stolen access is not available,
- and the platform is MTL-class media version `13.0`,
- `i915` requires the binder / VF2PF update path instead of normal VF GGTT
  programming.

That becomes visible in several places:

- `drivers/gpu/drm/i915/gt/iov/intel_iov.c`
  - PF-side GGTT shadow init for the workaround
- `drivers/gpu/drm/i915/gt/intel_ggtt.c`
  - VF-side GGTT insertion switches to relay/buffered update path
- Intel commit:
  `drm/i915/gt/iov: Add MTL WA for update VF GGTT via VF2PF relay`
  (`bcf6f14318c852a7319cf3ebeb0978432e314c0e`)

The practical platform assumption is simple:

- on MTL, VF direct GGTT update is not the normal path to trust.
- relay through PF is the safer path Intel chose.

### 2.3 MTL Has A Real ATS / DMA / Page-Table Caching Warning

The `i915` code in `drivers/gpu/drm/i915/gt/intel_gtt.c` carries a very direct
warning:

- suspected ATS issue on the IOMMU
- CAT errors on some MTL workloads
- write barriers did not help
- force CPU WC mappings temporarily for MTL page-table DMA

This corresponds to the upstream commit:

- `drm/i915/gt: Temporarily disable CPU caching into DMA for MTL`

That is a strong platform statement. It says:

- MTL cannot be assumed to behave correctly under the same DMA/page-table cache
  model as nearby platforms.
- Intel was willing to carry an MTL-only workaround in a core memory path.

### 2.4 MTL Firmware Pairing Is Part Of The Platform Contract

The MTL HuC/GuC compatibility patch says the same thing from the firmware side:

- `drm/i915/huc: check HuC and GuC version compatibility on MTL`
- thread:
  `https://www.spinics.net/lists/intel-gfx/msg330584.html`

The message explains the reasoning:

- MTL changed the authentication flow,
- new HuC requires new GuC,
- old/new mixes should fail loudly rather than half-work.

The current code in:

- `drivers/gpu/drm/i915/gt/uc/intel_uc_fw.c`
- `drivers/gpu/drm/i915/gt/uc/intel_gsc_fw.c`

continues that theme:

- MTL and ARL share firmware families in some cases,
- but ARL may require newer firmware even when the filename family is shared.

### 2.5 MTL Display Is Treated As Fragile Enough To Need Dedicated Workarounds

The non-SR-IOV display side is also noisy in a meaningful way.

Examples:

- `drm/i915: Bypass LMEMBAR/GTTMMADR for MTL stolen memory access`
  was part of a series that also said:
  - fix initial display plane readout for MTL
  - relocate BIOS framebuffer lower in GGTT to leave room for GuC setup
- `drivers/gpu/drm/i915/display/intel_plane_initial.c`
  explicitly describes MTL GOP framebuffers being placed too high in GGTT.
- `drivers/gpu/drm/i915/display/intel_display_irq.c`
  and related headers have MTL-specific plane and PIPEDMC ATS fault handling.
- additional MTL display commits in the earlier note set cover:
  - fast wake timing,
  - DSS clock gating,
  - longer settle windows.

The pattern is clear:

- Intel did not treat MTL display as "works unless proven otherwise".
- It treated MTL as a platform where memory path, initial framebuffer handoff,
  power/timing, and fault handling all needed extra attention.

## 3. ARL Is Usually "MTL-Like, But Newer", Not A New Model

ARL is often introduced by splitting IDs or tightening firmware checks, not by
rewriting the architectural assumptions from scratch.

Examples:

- `drm/i915: ARL requires a newer GSC firmware`
- `drm/i915/gsc: ARL-H and ARL-U need a newer GSC FW`
- `drm/i915/pciids: separate ARL and MTL PCI IDs`
  - message:
    `https://www.spinics.net/lists/intel-gfx/msg355440.html`
  - rationale:
    "Avoid including PCI IDs for one platform to the PCI IDs of another."

That split is about identity and firmware policy. It is not a declaration that
ARL has a radically different memory model.

The practical takeaway is:

- ARL is close enough to MTL that Intel initially grouped them,
- then had to split them where the differences became operationally important,
  especially firmware requirements and explicit PCI-ID handling.

## 4. What `xe` Says About MTL / ARL

`xe` expresses similar concerns, but not in one central policy block.

### 4.1 ARL And MTL Identity In `xe`

Current local `xe` code in `drivers/gpu/drm/xe/xe_pci.c` still shows:

- `INTEL_ARL_IDS(..., &mtl_desc)`
- `INTEL_MTL_IDS(..., &mtl_desc)`

So in this tree:

- ARL and MTL are still described by the same base descriptor,
- even though upstream work later separated the PCI-ID macros.

Relevant upstream xe-side messages:

- `drm/xe/pciids: separate ARL and MTL PCI IDs`
- called out in the 2024-10-10 `drm-xe-next` pull:
  `https://www.spinics.net/lists/intel-gfx/msg358184.html`

This is a good example of Intel's migration path:

- first treat ARL as MTL-like,
- later split identifiers once that becomes operationally useful.

### 4.2 `xe` Platform Work Is Often About Feature Gating

Two examples matter for MTL/ARL class devices:

- `drm/xe: Cleanup has_flat_ccs handling`
- `drm/xe: Update runtime detection of has_flat_ccs`

Both are explicitly called out in the same 6.13 pull summary:

- `https://www.spinics.net/lists/intel-gfx/msg358184.html`

And Ville Syrjälä's later review message gives the design nuance:

- `https://www.spinics.net/lists/intel-gfx/msg377804.html`
- he explains that `has_flat_ccs` is not only "can hardware compress right
  now", but also distinguishes the AUX/flat-CCS display path that the display
  stack should take.

That matters because MTL/ARL treatment in `xe` is often implemented as:

- better runtime detection,
- better feature masking,
- better display-path selection,

not just "MTL if/else" blocks.

### 4.3 `xe` Also Has To Turn Features Off For VFs

One concrete VF-facing example is:

- `drm/xe/vf: Disable CSC support on VF`
- stable message:
  `https://www.spinics.net/lists/stable/msg866934.html`

The message is simple:

- CSC is not accessible by VF drivers,
- so `xe` must stop advertising it on VFs.

That is exactly the kind of platform/virtualization rule that matters for
MTL/ARL too:

- not every feature visible on PF or bare metal is valid on VF,
- and `xe` has been learning those exclusions incrementally.

### 4.4 `xe` Display Support Around MTL/ARL Keeps Picking Up Coherency Fixes

One useful example is:

- `drm/xe: Fix DSB buffer coherency`
- stable record:
  `https://www.spinics.net/lists/stable-commits/msg422166.html`

The message says:

- add the scanout flag to force WC caching,
- add the memory barrier where needed.

That is not SR-IOV-specific, but it is the same broad theme:

- cache/coherency and display buffer handling matter,
- and Intel keeps adjusting them on the `xe` side.

## 5. Platform-Level Conclusion

Across both drivers, the common platform truth is:

- MTL is treated as special in memory access, GGTT handling, firmware
  compatibility, and display behavior.
- ARL is usually introduced as "MTL-like with sharper edges", then split out
  when firmware or identity handling requires it.

The difference is in expression:

- `i915` says this with bigger explicit platform workarounds and mature SR-IOV
  code around them.
- `xe` says it by gradually tightening platform IDs, runtime feature detection,
  feature masking, coherency rules, and PF/VF service code.
