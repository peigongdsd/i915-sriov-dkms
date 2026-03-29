# `i915` Versus `xe` For MTL / ARL SR-IOV

## 1. Comparison Method

This comparison is intentionally phase-based.

It does not ask:

- "which driver is better?"

It asks:

- "for the same SR-IOV phase, what does `i915` do, what does `xe` do, and what
  is platform-specific about MTL/ARL in each one?"

## 2. Phase-By-Phase Comparison

| Phase | `i915` | `xe` | MTL / ARL significance |
|---|---|---|---|
| mode detection | old `i915` SR-IOV world is explicit but more spread between driver and GT setup | `xe_sriov_probe_early()` explicitly decides PF/VF and disables accidental PCI exposure if platform support is off | `xe` is stricter about platform gatekeeping at probe |
| early PF/VF init | `intel_iov_init_early()` fans out to provisioning/service/state/ggtt/relay | `xe_sriov_init()` dispatches PF/VF init and creates shared workqueue | both stage early init, but `i915` has a more centralized IOV object model |
| MMIO bootstrap | VF resets GuC state, handshakes ABI, queries config/runtime | VF/PF bootstrap exists, but the public structure is more distributed across VF/PF helpers | both rely on early GuC/MMIO sequencing |
| runtime register sharing | PF explicitly exposes TGL or MTL register sets; MTL set is expanded | PF exposes graphics-version buckets; local `ver_1270` is smaller than `i915` MTL set | this is one of the clearest concrete mismatches |
| GGTT virtualization | VF ballooning, optional binder/shadow, explicit VF2PF relay WA on MTL | VF bootstrap sender + PF bootstrap apply + PF relay apply on MTL | conceptually aligned; both say MTL wants PF-mediated GGTT handling |
| migration / recovery | documented end-to-end in `i915_sriov.c`; RESFIX_DONE is core protocol | migration code exists but may be disabled by GuC version gate; VF CCS path documented separately | `i915` is more operationally mature here |
| VF feature shaping | older `i915` path expresses limits through service/query/contracts | `xe` centrally masks features in `vf_update_device_info()` | `xe` is more aggressive and explicit about VF personality reduction |
| display / compression interplay | many MTL-specific workarounds live in i915 display and GuC code | `xe` picks up display PM, DSB coherency, flat-CCS handling, VF feature disables incrementally | `xe` is still converging on a stable MTL/ARL policy surface |

## 3. Places Where `xe` Clearly Follows The `i915` Worldview

### 3.1 PF Owns Critical Runtime State

Both drivers assume:

- VFs do not see or control all relevant registers directly,
- PF must expose or proxy part of the runtime contract.

### 3.2 MTL GGTT Needs PF Mediation

This is the strongest continuity point.

Old `i915`:

- explicit MTL workaround for VF GGTT updates via VF2PF relay

Current `xe` tree:

- explicit MTL PF bootstrap update path
- explicit MTL PF relay update path
- explicit VF bootstrap sender path

This is not accidental similarity. It is the same platform lesson expressed in
different code.

### 3.3 MTL / ARL Need More Than Generic Feature Tables

Both sides kept adding:

- firmware-specific handling,
- feature gating,
- platform-ID cleanup,
- display/coherency fixes.

That means neither driver treats MTL/ARL as fully solved by a generic platform
descriptor alone.

## 4. Places Where `xe` Clearly Differs From Old `i915`

### 4.1 Runtime Register Exposure Is Narrower In Local `xe`

`i915` MTL runtime service exposes a hand-expanded MTL list.

Local `xe`:

- uses `ver_1270_runtime_regs[]`
- does not expose the same larger MTL set

This is a direct structural difference, not a matter of naming.

### 4.2 VF Personality Shaping Is More Centralized In `xe`

`xe` does all of the following in one VF device-info update:

- disable display probing,
- disable CSC/GSCFI capability,
- skip GuC power control,
- skip pcode,
- disable late bind.

Old `i915` spreads equivalent capability assumptions more across service,
runtime, and platform-specific code.

### 4.3 Migration Maturity Is Different

Old `i915`:

- documents migration and post-migration recovery as a first-class flow.

Local `xe`:

- has migration code,
- but can entirely disable it based on GuC version,
- and separates VF CCS save/restore into a dedicated subsystem.

This is not just "same design rewritten". It is a different maturity point.

### 4.4 ARL Identity Is Cleaner Upstream Than In This Local `xe` Tree

Upstream Intel work already separated ARL and MTL PCI-ID macros.

Local tree still shows:

- `INTEL_ARL_IDS(..., &mtl_desc)`
- `INTEL_MTL_IDS(..., &mtl_desc)`

So current local code is closer to the earlier "ARL is MTL-like" stage than to
the later "identity must be fully separate" stage.

## 5. What The Comparison Says About Platform Assumptions

### 5.1 On MTL, `i915` Is More Opinionated About Memory Paths

`i915` makes platform assumptions explicit in core code:

- direct stolen access only under strict conditions,
- BAR distrust,
- binder requirement,
- ATS-related WC fallback,
- expanded MTL runtime exposure.

`xe` contains some of the same lessons, but they are more fragmented:

- PAT table setup,
- GGTT relay service,
- VF feature masking,
- display PM/coherency fixes.

### 5.2 On ARL, Both Drivers Move From Grouping To Separation

The broad pattern is:

- early grouping with MTL,
- later explicit PCI-ID and firmware-policy separation.

That suggests ARL should be read as:

- platform-adjacent to MTL,
- but increasingly too different to hide under MTL IDs forever.

## 6. What This Comparison Definitely Says

The code and commit messages justify these claims:

1. MTL-specific SR-IOV handling in old `i915` was real, explicit, and tied to
   GGTT relay plus runtime-register exposure.
2. `xe` inherited the PF-mediated GGTT worldview, but not the same exact
   runtime-service contract.
3. `xe` relies more heavily on VF feature masking and later display/coherency
   fixes to shape safe behavior.
4. ARL support evolved from shared treatment with MTL toward clearer identity
   separation.

## 7. What This Comparison Does Not Prove

It does not, by itself, prove:

- that any one local bug is caused by the runtime-register difference,
- that any one `i915` workaround must be copied mechanically into `xe`,
- or that every MTL/ARL issue is "really a display problem" or "really a GGTT
  problem".

What it does provide is a trustworthy map of:

- which assumptions Intel explicitly made in each driver,
- where those assumptions line up,
- and where the current local `xe` tree is still meaningfully different from
  the older `i915` SR-IOV design.
