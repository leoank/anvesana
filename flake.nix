{
  description = "anvesana: NixOS live image for native-Linux benchmarks on NVIDIA RTX Spark (N1X) laptops";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }: {
    # nix build .#rtx-spark-live            (stock + osi boot entries)
    # ANVESANA_ACPI_OVERRIDE=$PWD/nix/local/acpi/acpi-override.cpio \
    #   nix build --impure .#rtx-spark-live (adds the sspm boot entry)
    nixosConfigurations.rtx-spark-live = nixpkgs.lib.nixosSystem {
      specialArgs.anvesanaSrc = self;
      modules = [ ./nix/live.nix ];
    };
    packages.aarch64-linux.rtx-spark-live = self.nixosConfigurations.rtx-spark-live.config.system.build.isoImage;

    # Hardware support for an installed NixOS on an N1X laptop: kernel, NVIDIA
    # (display included), CPU frequency init, initrd modules, sleep policy.
    nixosModules.n1x = ./nix/n1x.nix;
  };
}
