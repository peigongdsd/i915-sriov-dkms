# Upstream Commit Ledger: What Intel's Messages Actually Say

This file is the commit-message companion to the codeflow chapters.

The rule here is:

- first summarize what Intel's own message says,
- then state what code it maps to,
- then say why it matters for MTL / ARL SR-IOV reasoning.

## 1. `i915` In The Old Intel SR-IOV Lane

### 1.1 `drm/i915/gt: SR-IOV feature enablement`

Known Intel LTS SHA:

- `7f2edf7ea216980d5aaeaa0d16c892f6bd1f6334`

What the message means in practice:

- Intel was not adding a cosmetic flag.
- It was introducing the GT-level virtualization feature set as a coordinated
  design: provisioning, service, state tracking, GuC-facing VF/PF control, and
  GT integration.

Where it shows up in code:

- `drivers/gpu/drm/i915/gt/iov/*`
- `drivers/gpu/drm/i915/gt/intel_gt.c`

Why it matters:

- this is the "root of the old SR-IOV worldview" for `i915`.
- later MTL-specific changes are layered on top of this architecture, not
  separate from it.

### 1.2 `drm/i915/iov: Expose early runtime registers for MTL`

Known Intel LTS SHA:

- `c031d1a2aaea6d9804a6a12af67b424642171836`

What the message is saying:

- TGL-like runtime exposure was not sufficient for MTL.
- the VF needed additional runtime registers to bootstrap correctly on MTL.

Where it shows up in code:

- `drivers/gpu/drm/i915/gt/iov/intel_iov_service.c`
- `mtl_runtime_regs[]`

Why it matters:

- Intel treated MTL VF bootstrap as needing a different runtime contract, not
  just a different device ID.
- this is one of the strongest "MTL is different inside SR-IOV" signals.

### 1.3 `drm/i915/gt/iov: Add MTL WA for update VF GGTT via VF2PF relay`

Known Intel LTS SHA:

- `bcf6f14318c852a7319cf3ebeb0978432e314c0e`

What the message is saying:

- direct VF GGTT update on MTL was not the path Intel wanted to rely on.
- the workaround is to relay GGTT updates from VF to PF.

Where it shows up in code:

- `drivers/gpu/drm/i915/gt/intel_ggtt.c`
- `drivers/gpu/drm/i915/gt/iov/intel_iov.c`
- `i915_ggtt_require_binder()`

Why it matters:

- this is the clearest bridge from old `i915` SR-IOV to the later local `xe`
  MTL cleanpath.
- if you want one old `i915` idea that definitely carried forward, it is this
  PF-mediated GGTT model.

## 2. `i915` MTL / ARL Platform Work Outside The SR-IOV Directory

### 2.1 `drm/i915: Bypass LMEMBAR/GTTMMADR for MTL stolen memory access`

Mail thread:

- `https://www.spinics.net/lists/intel-gfx/msg342210.html`

What the message says:

- MTL stolen memory is "special" and "apparently broken".
- the series is trying to clean up that mess.

Where it maps:

- `drivers/gpu/drm/i915/i915_utils.c`
- `drivers/gpu/drm/i915/gem/i915_gem_stolen.c`
- `drivers/gpu/drm/i915/gt/intel_ggtt.c`

Why it matters:

- if MTL non-SR-IOV memory access is already treated this cautiously, any
  MTL SR-IOV design should be read in that context.

### 2.2 `drm/i915/gt: Temporarily disable CPU caching into DMA for MTL`

What the message says:

- Intel suspected ATS/IOMMU involvement in CAT errors on MTL workloads.
- the driver should force a safer CPU mapping mode until the deeper issue is
  solved.

Where it maps:

- comments and logic in `drivers/gpu/drm/i915/gt/intel_gtt.c`

Why it matters:

- MTL is not assumed to be naturally coherent in all GT/page-table paths.

### 2.3 `drm/i915/huc: check HuC and GuC version compatibility on MTL`

Mail thread:

- `https://www.spinics.net/lists/intel-gfx/msg330584.html`

What the message says:

- on MTL, HuC and GuC version pairings matter enough that compatibility checks
  should be enforced.

Where it maps:

- `drivers/gpu/drm/i915/gt/uc/intel_uc_fw.c`

Why it matters:

- MTL firmware is not a passive dependency. It is part of the platform
  contract.

### 2.4 `drm/i915: ARL requires a newer GSC firmware`

What the message says:

- ARL could no longer ride entirely on MTL's firmware assumptions.
- Intel had to split firmware validity policy even where families were shared.

Where it maps:

- `drivers/gpu/drm/i915/gt/uc/intel_gsc_fw.c`

Why it matters:

- ARL is near MTL, but not identical enough to keep all firmware rules shared.

## 3. `xe` In The Newer Upstreaming Lane

### 3.1 `drm/xe/pciids: separate ARL and MTL PCI IDs`

Public mention:

- `https://www.spinics.net/lists/intel-gfx/msg358184.html`
- older `i915` analogue:
  `https://www.spinics.net/lists/intel-gfx/msg355440.html`

What the message says:

- grouping ARL and MTL forever is not correct.
- PCI identity must reflect the platform split.

Where it maps:

- upstream xe PCI-ID cleanup
- contrast with local `xe_pci.c`, which still maps both to `mtl_desc`

Why it matters:

- it marks Intel's own move away from "ARL is just MTL with new IDs hidden in
  the same descriptor".

### 3.2 `drm/xe: Cleanup has_flat_ccs handling`

Pull summary:

- `https://www.spinics.net/lists/intel-gfx/msg358184.html`

What the message is saying:

- flat-CCS handling was not settled yet,
- and `xe` needed to clean up the platform/feature logic.

Where it maps:

- `drivers/gpu/drm/xe/xe_device.c`
- display paths that branch on flat CCS

Why it matters:

- MTL/ARL correctness in `xe` depends not only on SR-IOV code, but also on
  properly classifying compression/display capabilities.

### 3.3 `drm/xe: Update runtime detection of has_flat_ccs`

Pull summary:

- `https://www.spinics.net/lists/intel-gfx/msg358184.html`

What the message is saying:

- compile-time or descriptor-time assumptions were not enough,
- runtime probing needed to refine `has_flat_ccs`.

Where it maps:

- `probe_has_flat_ccs()` in `drivers/gpu/drm/xe/xe_device.c`

Why it matters:

- this is classic MTL/ARL-style Intel engineering: the platform is close
  enough to fit one broad family, but dynamic state still changes what is safe
  to advertise or use.

### 3.4 `drm/xe/vf: Disable CSC support on VF`

Stable message:

- `https://www.spinics.net/lists/stable/msg866934.html`

What the message says:

- if VF cannot access CSC, advertising CSC is wrong.

Where it maps:

- `vf_update_device_info()` in local `xe_device.c`

Why it matters:

- this is a concrete example of Intel tightening VF capability exposure after
  the initial feature landed.
- it shows the pattern to watch for with MTL/ARL: a feature may be valid on PF
  or bare metal but still invalid on VF.

### 3.5 `drm/xe: Fix DSB buffer coherency`

Stable message:

- `https://www.spinics.net/lists/stable-commits/msg422166.html`

What the message says:

- add the scanout flag to force WC caching,
- add the missing barrier for DSB coherency.

Where it maps:

- xe display side, not SR-IOV-specific

Why it matters:

- even after SR-IOV is enabled, MTL/ARL behavior can still hinge on display
  buffer coherency rules elsewhere in the driver.

## 4. How To Read These Messages Together

The combined Intel message stream is:

- old `i915` made MTL SR-IOV explicit through runtime-register expansion,
  GGTT relay, and mature migration/fixup documentation,
- while non-SR-IOV `i915` made MTL explicit through stolen-memory distrust,
  ATS/cache caution, firmware gating, and display workarounds,
- newer `xe` keeps moving toward the same operational caution, but does so by
  tightening platform IDs, runtime feature detection, VF capability masking,
  and selected coherency fixes.

That is the right way to read "Intel side" history:

- not as one perfect SR-IOV design moving intact from `i915` to `xe`,
- but as a set of platform lessons being re-expressed under new abstractions.
