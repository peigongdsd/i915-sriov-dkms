# MTL / ARL SR-IOV Source Study

This directory is a source-driven study of Intel's Meteor Lake (MTL) and Arrow
Lake (ARL) handling across the two relevant upstream lines:

- `i915` in Intel's old SR-IOV development lane (`intel/linux-intel-lts`)
- `xe` in the newer upstreaming lane (`drm-xe-next` / Intel mainline-tracking)

The goal is not to guess a fix. The goal is to record what Intel's code and
commit messages actually say about:

1. what is special about MTL and ARL,
2. how SR-IOV flows through `i915`,
3. how SR-IOV flows through `xe`,
4. where the two code paths are equivalent, and where they are not.

## Reading Order

- `01-platform-properties.md`
  - Platform-level assumptions and special treatment for MTL/ARL.
- `02-i915-sriov-codeflow.md`
  - End-to-end SR-IOV codeflow in `i915`.
- `03-xe-codeflow.md`
  - End-to-end SR-IOV codeflow in `xe`.
- `04-i915-vs-xe-comparison.md`
  - Direct phase-by-phase comparison and mismatches.
- `05-upstream-commit-ledger.md`
  - Commit-message digest: what Intel's own messages say, mapped back to code.
- `06-local-experiment-branch-ledger.md`
  - Local branch-by-branch experiment ledger for the `peigongdsd` investigation
    lines.
- `90-source-index-and-existing-notes.md`
  - Source map, commit index, and how older local notes were folded in.

## Scope

This set is deliberately biased toward:

- code paths that materially affect MTL/ARL SR-IOV bring-up or runtime behavior,
- comments and kernel-doc blocks that explain intent,
- commit messages that explicitly describe Intel's platform assumptions,
- places where `xe` is clearly following, simplifying, or diverging from
  `i915`.

It is not a complete history of either driver.

## Top-Level Takeaways

The study supports four high-level statements:

1. Intel's old `i915` SR-IOV line treats MTL as a platform that needs explicit
   early-runtime exposure, explicit VF-to-PF GGTT relay handling, and a fairly
   mature migration/fixup story.
2. Upstream `i915` non-SR-IOV code also treats MTL as unusual in stolen-memory
   access, DMA/page-table caching, firmware pairing, and display timing.
3. `xe` inherited part of that worldview, but not as one single "MTL policy"
   block. Instead, the relevant behavior is split across PCI IDs, PAT setup,
   VF feature masking, PF/VF GGTT service, migration gating, and display/PM
   fixes.
4. The cleanest technical comparison is not "i915 versus xe overall", but
   "phase X in i915 SR-IOV versus phase X in xe SR-IOV". The biggest
   mismatches show up in runtime-register exposure, migration maturity,
   platform feature masking, and how MTL/ARL identity is represented.
