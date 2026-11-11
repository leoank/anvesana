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

    # nix build .#rtx-spark-desktop         GNOME live image for daily-driver testing, with
    #   log collection to SPARKDATA (nix/desktop-live.nix); same ANVESANA_ACPI_OVERRIDE rule.
    # scripts/vm-test.sh boots it in QEMU and checks the collected logs.
    nixosConfigurations.rtx-spark-desktop = nixpkgs.lib.nixosSystem {
      specialArgs.anvesanaSrc = self;
      modules = [ ./nix/desktop-live.nix ];
    };
    packages.aarch64-linux.rtx-spark-desktop = self.nixosConfigurations.rtx-spark-desktop.config.system.build.isoImage;

    # Hardware support for an installed NixOS on an N1X laptop: kernel, NVIDIA
    # (display included), CPU frequency init, initrd modules, sleep policy.
    nixosModules.n1x = ./nix/n1x.nix;
    # The GNOME desktop parts tested on the live desktop image (refresh rate by power source,
    # power profiles, lid/suspend, LPS0 standby calls, pen screen, n1x-pen, speaker DSP); use
    # with `n1x` and a GNOME desktop. Findings: docs/n1x-linux.md.
    nixosModules.n1x-desktop = ./nix/n1x-desktop.nix;
  };
}
