# NixOS Xe SR-IOV VF Guest Harness

This harness boots a Linux/NixOS guest with VF1 (`0000:00:02.1`) passed through
so the xe VF path can be tested without the Windows driver as a black box.

It intentionally pins the guest to the same versions currently used by the host
configuration:

- `nixpkgs`: `134c6973427a26f0b8924e7bb1a2ce5a9249d903`
- `i915-sriov`: `2c46b49ffaa63db22654dd6067052ecaf05194c4`
- Linux kernel: `7.0.12`
- module package: `xe-sriov-module-2026.05.06-7.0.12`

The VM exposes:

- SSH on host port `2222` for the VF VM, user `root`, using the local
  `id_ed25519.pub`.
- SSH on host port `2223` for the no-VF smoke-test VM.
- Serial console on stdio.
- VF1 passthrough via QEMU `vfio-pci`.

Before starting the guest, stop any other VM using VF1, especially `win11`.

The harness deliberately uses the host Nix store mount path instead of
`virtualisation.useNixStoreImage`. The first attempt used a just-in-time EROFS
Nix store image and the host froze while the generated launcher was printing
`Creating Nix store image...`, before QEMU reached VFIO attach. That run is a
host/VM-launcher failure, not evidence about xe VF behavior.

Useful commands:

```sh
nix build ./tools/nixos-vf-guest#nixosConfigurations.xe-vf-guest.config.system.build.vm
run0 ./result/bin/run-xe-vf-guest-vm
ssh -p 2222 root@127.0.0.1
```

To smoke-test the NixOS VM path without touching VFIO first:

```sh
nix build ./tools/nixos-vf-guest#nixosConfigurations.xe-guest-novf.config.system.build.vm
run0 ./result/bin/run-xe-guest-novf-vm
ssh -p 2223 root@127.0.0.1
```

Inside the guest:

```sh
uname -a
lspci -nnk -s 00:02.0
lsmod | grep -E '(^xe|intel_sriov_compat)'
dmesg -T | grep -Ei 'xe|guc|sriov|vf|drm|gpu|fault|reset|wedg|hang|mcr'
modinfo xe | sed -n '1,40p'
```

The guest is not expected to reproduce Windows DWM behavior directly. It is for
checking whether the Linux VF stack sees a clean xe VF device, whether basic DRM
initialization works, and whether kernel-visible faults, MMIO errors, PAT/MOCS
oddities, or GGTT errors show up without Windows in the loop.
