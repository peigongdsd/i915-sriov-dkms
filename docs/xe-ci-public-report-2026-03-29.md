# Public `drm/xe/ci` Report

Date: 2026-03-29  
Repository examined: `https://gitlab.freedesktop.org/drm/xe/ci`

## Scope

This report is about the **public** `drm/xe/ci` repository only.

That distinction matters because the repository itself says the full runner
image and the full pipeline definition are not public. So this report answers:

- what the public repo actually contains,
- what testing it clearly drives,
- what it strongly suggests about Intel's CI priorities,
- and what it does **not** let us conclude about the private hardware lab.

It does **not** pretend to reconstruct the internal board matrix from files that
are not public.

## Executive Summary

The public `drm/xe/ci` repository is not a complete "all hardware, all tests"
manifest. It is a shared CI support repo that exposes three main things:

1. a public merge-request GitLab pipeline for lint and kernel build,
2. a curated kernel-config system used for CI kernels,
3. a hook mechanism for extra premerge checks that run before hardware testing.

The repo makes two boundaries explicit:

- hardware testing exists downstream of these steps,
- but the actual runner image and Jenkins pipeline for that hardware testing are
  in an internal repo, not here.

So the public repo tells us a lot about **how Intel prepares kernels and
premerge checks** for xe, but only indirectly about **which exact machines and
test suites** are used in the full lab.

## 1. What Is Public In The Repository

Top-level layout:

- `README.md`
- `kernel/`
- `hooks/`
- `run-hooks.sh`
- `re-config.sh`
- `vendor/merge_config.sh`

What each part is for:

- `kernel/`
  - kernel config bases, fragments, and generated flavor configs
- `hooks/`
  - extra scripts that can fail the premerge pipeline before hardware testing
- `kernel/.gitlab-ci.yml`
  - the public GitLab MR pipeline
- `README.md`
  - explains how this public repo fits into the wider CI

## 2. The Public GitLab Pipeline

The public GitLab CI file is:

- `kernel/.gitlab-ci.yml`

It is small and very telling.

### 2.1 Trigger Model

The workflow only runs for:

- merge request pipelines

This already frames the public CI as:

- a premerge quality gate,
- not the whole internal validation universe.

### 2.2 Stages

Public stages are:

- `lint`
- `build`

No public stage here describes:

- IGT execution,
- hardware boot,
- suspend/resume loops,
- display farms,
- per-platform DUT allocation,
- fuzzing,
- piglit,
- VK/compute workloads,
- or perf benchmarks.

That absence is real. Those may exist privately, but they are not declared in
this repo.

### 2.3 Public Lint Jobs

Two public lint jobs exist:

- `lint-checkpatch-job`
- `lint-docs-job`

What they do:

- `checkpatch.pl` on the MR diff range
- `kernel-doc -Werror` on `drivers/gpu/drm/xe/`, excluding display and one
  compatibility header

Interpretation:

- Intel's public premerge gate expects xe patches to survive both style checks
  and API/documentation consistency checks.
- `kernel-doc` is treated as a first-class quality gate, not just a nicety.

### 2.4 Public Build Job

The public build job does two builds:

1. full x86_64 kernel build using the CI kconfig
2. `drivers/gpu/drm/xe` module build with `W=1`

Important details:

- CI clones the `drm/xe/ci` repo into `.ci`
- seeds `build64/.config` from `.ci/kernel/kconfig`
- builds the full kernel
- then disables `CONFIG_DRM_XE_DISPLAY` and builds `drivers/gpu/drm/xe` with
  `W=1`

The explicit comment says:

- `CONFIG_DRM_XE_DISPLAY currently breaks build with W=1. Just disable it for now`

That is a direct public insight into Intel's CI practice:

- they value a warnings-clean `W=1` build,
- but they scope it to the core xe module when display would otherwise block it.

This is a practical compromise, not an idealized one.

## 3. Hooks: The Public "Gate Before Hardware"

The README is extremely clear about hooks:

- hooks run only on the public Xe kernel premerge pipeline,
- hooks run after the kernel is built,
- hooks run after software-only tests are done,
- hooks run just before actual hardware testing,
- if any hook fails, hardware testing does not start.

That means hooks are a strong gate:

- they are not post-processing,
- they are a checkpoint between software validation and lab usage.

### 3.1 Public Hook Scripts Present Today

The public hooks are:

- `00-showenv`
- `10-build-W1`
- `11-build-32b`
- `20-kernel-doc`

#### `00-showenv`

Purpose:

- dump CI-related environment variables

This is not a test itself. It is operational observability.

#### `10-build-W1`

Purpose:

- build the xe driver with `W=1`

This reinforces the point from the GitLab build job:

- warning-clean xe build coverage is a standing CI concern.

#### `11-build-32b`

Purpose:

- do an `ARCH=i386` defconfig-based build,
- merge in `kernel/fragments/10-xe.fragment`,
- build again

This is a valuable signal. Even if Intel is not testing 32-bit hardware as a
real deployment target, they are spending CI budget on:

- cross-architecture build correctness,
- config integration correctness,
- not accidentally breaking 32-bit compilation paths.

#### `20-kernel-doc`

Purpose:

- run `kernel-doc -Werror` on xe sources and a few related DRM pagemap/SVM
  files

This hook goes beyond the GitLab lint job:

- it explicitly folds `drm_gpusvm` and `drm_pagemap` related docs into the
  kernel-doc gate.

That shows Intel sees xe as tied to broader DRM memory-management APIs, not as
  a completely isolated driver.

## 4. The Kernel Config System Intel Uses Publicly

The `kernel/` directory is a maintained configuration generator, not just one
  monolithic config blob.

It has:

- `kernel/base/`
  - imported distro or base configs
- `kernel/fragments/`
  - CI-specific overrides
- `kernel/flavors/`
  - flavor recipes composed from bases + fragments
- generated outputs such as:
  - `kernel/kconfig`
  - `kernel/debug.kconfig`
  - `kernel/nodebug.kconfig`
  - `kernel/kasan.kconfig`
  - `kernel/gcov.kconfig`

The helper script:

- `re-config.sh`

regenerates all flavor configs from those components.

### 4.1 What This Means Operationally

Intel is not treating the CI kernel as:

- "use whatever distro config the runner has".

Instead, the public repo shows a deliberate CI kernel policy:

- take a known distro or minimal base,
- apply CI-specific fragments,
- generate named flavors for different validation modes.

That is mature CI hygiene.

## 5. Public Kernel Flavors

Current flavors:

- `debug`
- `debug-full`
- `nodebug`
- `kasan`
- `gcov`
- `habana-debug`
- `habana-nodebug`
- `tinyconfig`

### 5.1 What The Flavor Set Tells Us

This is one of the most useful parts of the repo because it reveals the kinds
  of validation Intel considers worth maintaining.

#### `debug` / `debug-full`

These are the everyday CI kernels.

They include:

- CI support fragments
- xe fragment
- i915 fragment
- drm fragment

`debug-full` adds extra debug info / BTF support.

Meaning:

- Intel's baseline validation is not xe-only. The standard kernel flavors keep
  both xe and i915 enabled.
- This suggests they want ongoing regression visibility across both Intel DRM
  drivers in the same CI kernel.

#### `nodebug`

This removes several debug-heavy options while keeping the CI support shape.

Meaning:

- Intel wants a lower-noise or closer-to-production comparison kernel too,
  not only heavily debug-oriented builds.

#### `kasan`

Obvious purpose:

- memory safety bug surfacing

Meaning:

- memory corruption / invalid access detection is part of the public CI story.

#### `gcov`

Purpose:

- coverage-oriented builds

Meaning:

- at least some Intel CI consumers care about code coverage instrumentation.

#### `habana-*`

These flavors add:

- `CONFIG_DRM_XE_PRESI_PCI_DEVELOPMENT_MODE=y`

Meaning:

- the repo is not only for vanilla upstream xe laptop/desktop validation.
- It is also used to carry configuration for internal or adjacent accelerator /
  special development environments.

#### `tinyconfig`

Purpose:

- ultra-minimal build used for CI automation testing

The base README says it is:

- useless for real hardware,
- useful for testing CI automation and scripting,
- fast to build under QEMU/KVM.

Meaning:

- Intel uses this repo not only to validate kernels, but also to validate the
  CI plumbing itself.

## 6. The Public Fragments Tell Us What They Care About

The fragment set is more informative than it first looks.

### 6.1 `10-xe.fragment`

This is the core xe fragment:

- `CONFIG_DRM_XE=m`
- `CONFIG_DRM_XE_FORCE_PROBE="*"`
- `CONFIG_DRM_XE_WERROR=y`
- `CONFIG_DRM_XE_DEBUG=y`
- `CONFIG_DRM_XE_DEBUG_MEM=y`
- `CONFIG_DRM_XE_KUNIT_TEST=m`
- `CONFIG_DRM_KUNIT_TEST=m`

Meaning:

- public CI forces xe probing broadly,
- treats xe warnings as fatal,
- keeps debug paths on in main debug kernels,
- and enables both xe-specific and DRM KUnit support.

This is a strong statement of CI philosophy:

- maximize probe/build coverage,
- make warnings count,
- keep unit-test infrastructure available.

### 6.2 `20-i915.fragment`

This fragment keeps:

- `CONFIG_DRM_I915_FORCE_PROBE="*"`
- `CONFIG_DRM_I915_PXP=y`
- various i915 debug options

Meaning:

- even in the xe CI repo, Intel is not isolating xe from i915.
- Shared Intel DRM regression exposure is part of the public CI kernel shape.

### 6.3 `30-drm.fragment`

This fragment enables:

- `CONFIG_DRM_HEADER_TEST=y`
- build coverage for some non-Intel DRM drivers
- `CONFIG_TRACE_GPU_MEM=y`
- `CONFIG_MTD_INTEL_DG=m`

Meaning:

- Intel wants header/build compatibility checked in a broader DRM context,
- not only "does xe compile by itself".

### 6.4 `00-ci.fragment`

This is the broad CI environment policy.

Important points:

- lots of debug knobs are enabled,
- KUnit / fault injection / function error injection are enabled,
- console and logging options are enabled,
- MEI GSC / GSC proxy / CSC / LB modules are enabled,
- virtualization support is enabled:
  - `VFIO`
  - `VFIO_PCI`
  - `XE_VFIO_PCI`
  - `VIRTIO_MEM`
  - `VHOST_NET`
  - `VETH`

There are also comments that reveal real CI pain points:

- USB4 tunneling lockdep false positives
- PCIe hotplug lockdep false positives
- SPD5118 suspend/resume failures
- HDMI silent-stream power-management interference

These comments are valuable because they show:

- Intel tunes CI against real recurring lab failures and false positives,
- not just against abstract cleanliness.

### 6.5 Storage / Networking / Sound Fragments

These fragments are not "xe tests" in the narrow sense. They enable the system
  around xe testing.

They include support for:

- storage and filesystems needed to boot and to mount CI assets,
- NFS and 9p for internal asset sharing and QEMU use,
- common Intel/Broadcom/Realtek NICs used in lab machines,
- HDMI audio paths needed for i915/xe testing,
- selected SOF Intel audio stacks.

This is one of the clearest practical messages in the repo:

- Intel's xe CI kernel is built as a real lab/runner kernel,
- not as a stripped synthetic build-only artifact.

## 7. What Platforms Can Be Seen Publicly

This is where the public boundary becomes important.

### 7.1 What The Public Repo Clearly Shows

The repo clearly shows support plumbing for:

- xe in general,
- i915 in the same kernels,
- Intel audio stacks including lines relevant to:
  - TGL
  - MTL
  - LNL

It also carries general virtualization and lab infrastructure support.

### 7.2 What The Public Repo Does **Not** Show

The public repo does **not** provide a machine matrix such as:

- which DUTs are DG2,
- which are MTL,
- which are ARL,
- which are BMG or PTL,
- how many machines per platform,
- which test suites are mapped to which platform,
- which jobs are mandatory for which platform.

There are no public files here that define:

- per-platform farm inventory,
- per-platform IGT plans,
- display topology inventories,
- suspend/resume scenario tables,
- media/decode workload tables,
- or SR-IOV-specific lab routing.

So from this repo alone, we cannot honestly say:

- "Intel applies test X on all xe platforms Y and Z"

unless X is one of the public premerge build/lint/hooks described above.

## 8. What Testing Intel Is Publicly Applying

From the public repo alone, the defensible answer is:

### 8.1 Definitely Public And Active

- MR-triggered GitLab checkpatch lint
- MR-triggered GitLab kernel-doc lint
- MR-triggered x86_64 full kernel build using the xe CI config
- MR-triggered `W=1` xe-only build with display disabled for that pass
- premerge hook gate:
  - environment audit
  - another `W=1` xe build
  - 32-bit xe build
  - kernel-doc over xe plus related DRM pagemap/SVM files

### 8.2 Strongly Implied But Not Publicly Enumerated

The README explicitly says hooks run:

- after software-only tests,
- before actual hardware testing.

So there is definitely a downstream stage that includes:

- software-only tests beyond the visible GitLab jobs,
- hardware testing after hooks pass.

But the exact contents are not public here.

## 9. What The Recent CI Repo History Says About Intel Priorities

Recent visible commits are revealing:

- `config: Enable CONFIG_XE_VFIO_PCI`
- `config: Enable CONFIG_INTEL_MEI_CSC`
- `config: Enable CONFIG_INTEL_MEI_LB`
- `hooks/kernel-doc: add SVM & pagemap`
- `Enable TRACE_GPU_MEM`
- `Enable CONFIG_MTD_INTEL_DG`
- `Enable IOMMU back`
- `Drop CONFIG_SND_HDA_INTEL_HDMI_SILENT_STREAM`
- `Re-add I40E`

These are not random.

They show active CI concern for:

- VFIO / virtualization coverage,
- GSC / CSC / MEI-related firmware plumbing,
- SVM and pagemap documentation correctness,
- GPU memory tracing,
- DG non-volatile memory exposure,
- IOMMU-enabled environments,
- lab audio/power-management interactions,
- concrete NICs used in the test machines.

So while the hardware matrix is private, the **kind** of testing environment is
not mysterious:

- Intel is clearly validating xe in a realistic lab kernel with virtualization,
  firmware plumbing, networking, storage, audio, and debug infrastructure
  enabled.

## 10. Bottom Line

The public `drm/xe/ci` repo is best understood as:

- a public CI support toolkit for xe-related repositories,
- not the complete public record of Intel's full hardware farm.

It tells us with confidence that Intel publicly applies:

- style and kernel-doc lint,
- x86_64 build validation,
- `W=1` xe build validation,
- 32-bit xe build validation,
- curated CI kernel flavors with debug, nodebug, kasan, gcov, and tinyconfig
  variants,
- premerge hook gating before hardware testing.

It also tells us that Intel's CI kernels are configured for:

- xe and i915 together,
- virtualization and VFIO,
- GSC/CSC/MEI support,
- HDMI audio and lab power-management realism,
- storage/network/filesystem support needed for a real DUT environment.

What it does **not** tell us is the exact platform-by-platform internal test
matrix for all xe platforms. The README itself says that the full runner image
and Jenkins pipeline live in a separate internal repo, so that missing detail is
not an accident. It is outside the public boundary.
