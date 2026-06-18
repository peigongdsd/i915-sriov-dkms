{
  description = "Matched NixOS xe SR-IOV VF guest test harness";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/134c6973427a26f0b8924e7bb1a2ce5a9249d903";
    i915-sriov = {
      url = "github:peigongdsd/i915-sriov-dkms/2c46b49ffaa63db22654dd6067052ecaf05194c4";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      i915-sriov,
      ...
    }:
    let
      system = "x86_64-linux";
      pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAVNqzKr7X64A8bG0TRQYe0Rfc2/PN6Zlg6XOm6uvuIQ peigo@KruslPC";
      mkGuest =
        {
          name,
          hostPort,
          passthroughVf,
        }:
        nixpkgs.lib.nixosSystem {
          inherit system;
          modules = [
            i915-sriov.nixosModules.default
            (
              { pkgs, modulesPath, ... }:
              {
                imports = [
                  "${modulesPath}/profiles/qemu-guest.nix"
                  "${modulesPath}/virtualisation/qemu-vm.nix"
                ];

                system.stateVersion = "25.11";
                networking.hostName = name;

                nix.enable = false;
                documentation.enable = false;

                boot.kernelPackages = pkgs.linuxPackages_latest;
                boot.extraModulePackages = [ pkgs.xe-sriov ];
                boot.initrd.kernelModules = [ "xe" ];
                boot.kernelModules = [ "xe" ];
                boot.extraModprobeConfig = ''
                  options xe force_probe=7d55 enable_guc=3 wedged_mode=0
                  options i915 force_probe=!7d55
                '';
                boot.kernelParams = [
                  "console=ttyS0,115200n8"
                  "earlyprintk=serial,ttyS0,115200"
                  "drm.debug=0x1e"
                  "loglevel=7"
                ];

                services.openssh = {
                  enable = true;
                  settings = {
                    PermitRootLogin = "prohibit-password";
                    PasswordAuthentication = false;
                  };
                };
                users.users.root.openssh.authorizedKeys.keys = [ pubkey ];

                environment.systemPackages = with pkgs; [
                  pciutils
                  usbutils
                  kmod
                  libdrm
                  mesa-demos
                  intel-gpu-tools
                  jq
                ];

                hardware.graphics.enable = true;
                hardware.graphics.extraPackages = with pkgs; [
                  intel-media-driver
                  intel-vaapi-driver
                  intel-compute-runtime
                  level-zero
                ];

                virtualisation = {
                  memorySize = 4096;
                  cores = 4;
                  diskSize = 8192;
                  writableStore = true;
                  mountHostNixStore = true;
                  useNixStoreImage = false;
                  forwardPorts = [
                    {
                      from = "host";
                      host.port = hostPort;
                      guest.port = 22;
                    }
                  ];
                  qemu.options =
                    [
                      "-machine"
                      "q35,kernel-irqchip=split"
                    ]
                    ++ nixpkgs.lib.optionals passthroughVf [
                      "-device"
                      "pcie-root-port,id=rp1,bus=pcie.0,chassis=1,slot=1"
                      "-device"
                      "vfio-pci,host=0000:00:02.1,bus=rp1,addr=0x0,rombar=0"
                    ];
                };
              }
            )
          ];
        };
    in
    {
      nixosConfigurations.xe-vf-guest = mkGuest {
        name = "xe-vf-guest";
        hostPort = 2222;
        passthroughVf = true;
      };

      nixosConfigurations.xe-guest-novf = mkGuest {
        name = "xe-guest-novf";
        hostPort = 2223;
        passthroughVf = false;
      };
    };
}
