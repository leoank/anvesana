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

    # nix develop: the suite on a NixOS host (`uv run bench setup`, then `uv run bench run`).
    # uv installs the extras' wheels (CUDA, TensorRT, CUTLASS) into .venv on Nix's Python; the
    # wheels' native libraries find the driver's libcuda and NVML in /run/opengl-driver/lib and
    # libstdc++ / zlib through LD_LIBRARY_PATH, so no nix-ld is needed. The stdenv's g++ builds
    # CUTLASS's profiler.
    devShells.aarch64-linux.default = let
      pkgs = nixpkgs.legacyPackages.aarch64-linux;
    in pkgs.mkShell {
      packages = [ pkgs.uv pkgs.python312 ];
      env = {
        UV_PYTHON = "${pkgs.python312}/bin/python3.12";
        UV_PYTHON_DOWNLOADS = "never";
        LD_LIBRARY_PATH = "/run/opengl-driver/lib:${pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.zlib ]}";
      };
    };
  };
}
