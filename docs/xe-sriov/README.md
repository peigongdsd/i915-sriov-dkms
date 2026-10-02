# ADL-P Xe SR-IOV work

The first implementation target is Linux Xe on ADL-P. This branch starts from current DKMS upstream and adds one accepted Xe correction; MTL/ARL implementation remains a later phase.

| Branch / change | Identity |
|---|---|
| Clean upstream snapshot: `codex/upstream-sync-2026-10-02` | strongtz master `f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88` |
| ADL-P work: `codex/xe-adlp-2026-10-02` | The snapshot plus the correction and these research records |
| Driver correction | `32d16259df98d7153daaa9b8c461c2eaa0d24394`, unmodified backport of upstream `38631a7bce195b88814b93bf2b6d3e48c827fef2` |

The patch fixes duplicate emission of XeLP timestamp workaround `Wa_16010904313`. Render/compute engines retain it in the indirect context; copy/video engines retain it in the post-restore batch. Both Linux PF and Linux VF context construction use this code. A Windows VF constructs its own contexts, so a host-only change has different coverage.

**Validation:** the full Xe module and compatibility module build and link successfully against Linux 7.2.8 headers with GCC 16.2.0. MODPOST completed. The headers-only environment lacked `vmlinux`, so BTF generation was skipped. The modules were not loaded and hardware resolution of the reported failed vGPU is not yet established.

- [ADL-P hardware test plan](patches/adlp/TESTING.md)
- [Build record](patches/adlp/build-verification.json) and [complete build log](patches/adlp/build-7.2.8.log)
- [Independent patch review](adlp-timestamp-review.md)
- [Detailed research report](RESEARCH-REPORT.md)
- [Windows analysis and reproducibility](windows/README.md)

After testing, preserve separate host and Linux guest captures with the [read-only collector](collect-adlp-debug.sh). Replace the example BDFs with the host PF and the VF address shown inside the guest, and choose fresh output paths:

```sh
sudo bash docs/xe-sriov/collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-host-failed
sudo bash docs/xe-sriov/collect-adlp-debug.sh guest 0000:00:08.0 /tmp/adlp-guest-failed
```

Run the second command inside the Linux guest. Each run creates an output directory and a `.tar.gz` archive; `collection-status.txt` records missing files and timed-out reads. The collector preserves logs even when VF probe fails and does not configure the GPU. Capture immediately after the first failure, before rebooting. See the [test plan](patches/adlp/TESTING.md) for baseline comparisons and per-engine execution tests.

The study obtained the authoritative Xe project's full advertised branch/tag histories and recorded [their identities](xe-full-official-refs.txt). Commit review was targeted to the relevant platforms, SR-IOV and context paths; it was not a manual review of every kernel commit. The complete local Git history and downloaded driver binaries are not embedded in this repository.

No new MTL relay protocol or MTL driver changes are introduced here. Future work should first reuse Xe's existing interfaces and establish hardware requirements before importing any legacy implementation.

To repeat the compile check, use prepared headers for the intended supported kernel and the normal DKMS build prerequisites. From the repository root:

```sh
make -j8 -C /path/to/prepared/kernel/build M="$PWD" \
    compat/intel_sriov_compat.ko drivers/gpu/drm/xe/xe.ko
```

An optional [Nix build environment](patches/adlp/build-env.nix) supplies compiler and header dependencies. This is a build check only; it does not install or activate the resulting modules.
