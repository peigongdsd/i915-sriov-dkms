let
  pkgs = (builtins.getFlake "nixpkgs").legacyPackages.x86_64-linux;
in
pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    gnumake gcc bison flex bc perl python3 pkg-config
  ];
  buildInputs = with pkgs; [ elfutils openssl ];
  hardeningDisable = [ "all" ];
}
