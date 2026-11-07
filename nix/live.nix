# NixOS live USB for native-Linux benchmarks on the NVIDIA RTX Spark (N1X)
# laptops, built for bbaum-pc-7 (MSI Prestige N16 Flip AI+). See
# docs/rtx-spark-replication.md for why each piece is here. Console only, on purpose:
# no compositor shares the GPU with the benchmarks. The GNOME image is nix/desktop-live.nix.
#
# Boot entries (one image, chosen in the boot menu):
#   default     stock firmware ACPI tables (on bbaum-pc-7: no USB, so it cannot boot from USB)
#   osi         acpi_osi="!Windows 2022": Linux stops claiming Windows 2022, so
#               every device hidden from it appears (SVP0, SSPM, HFRP, NH1X, NMAP)
#   sspm        DSDT override that exposes only SSPM (NVDA8400); built only when
#               ANVESANA_ACPI_OVERRIDE names a cpio from scripts/acpi-hidden-devices.py
#               (it holds MSI's tables, so it never enters git) and --impure is passed.
#               Boot it from a stick written directly: Ventoy hides the override.
#   simpledrm   stock ACPI, display on the firmware framebuffer instead of nvidia-drm
#               (fallback if the patched nvidia-drm gives no picture on this panel)
# All entries but simpledrm drive the display with nvidia-drm, as a desktop would.
#
# Persistent data lives on a second USB drive labelled SPARKDATA (exFAT):
#   models/   GGUF files (scripts/llm-fetch.py; same layout on every OS)
#   results/  the anvesana results store, so runs survive the live session
#   ssh/authorized_keys   optional; enables SSH login as root
{ config, lib, pkgs, modulesPath, ... }:

let
  llamaCpp = pkgs.callPackage ./llama-cpp-bin.nix { };
  acpiOverride = builtins.getEnv "ANVESANA_ACPI_OVERRIDE";
in
{
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
    ./live-common.nix
  ];

  isoImage.volumeID = "ANV_SPARK";

  # ------------------------------------------------------------------ boot entries
  specialisation = {
    osi.configuration = {
      boot.kernelParams = [ ''acpi_osi="!Windows 2022"'' ];
      environment.etc."anvesana-boot-entry".text = "osi\n";
      isoImage.appendToMenuLabel = lib.mkForce " - osi (acpi_osi !Windows 2022)";
    };
    # Display fallback: if nvidia-drm gives no picture, this entry keeps the firmware framebuffer.
    simpledrm.configuration = {
      n1x.nvidiaDisplay = false;
      environment.etc."anvesana-boot-entry".text = "simpledrm\n";
      isoImage.appendToMenuLabel = lib.mkForce " - simpledrm (no nvidia-drm display)";
    };
  } // lib.optionalAttrs (acpiOverride != "") {
    sspm.configuration = {
      boot.initrd.prepend = [ "${builtins.path { path = acpiOverride; name = "acpi-override.cpio"; }}" ];
      environment.etc."anvesana-boot-entry".text = "sspm\n";
      isoImage.appendToMenuLabel = lib.mkForce " - sspm (ACPI override, SSPM exposed)";
    };
  };
  environment.etc."anvesana-boot-entry".text = lib.mkDefault "default\n";
  isoImage.appendToMenuLabel = lib.mkDefault " - default";

  environment.variables = {
    ANVESANA_MODELS_DIR = "/mnt/sparkdata/models";
    ANVESANA_LLAMA_BENCH = "${llamaCpp}/bin/llama-bench";
  };

  # ------------------------------------------------------------------ tools
  # nix-ld runs the prebuilt llama.cpp and uv-managed Python (vLLM, optional).
  programs.nix-ld = {
    enable = true;
    libraries = with pkgs; [ stdenv.cc.cc.lib zlib openssl curl config.hardware.nvidia.package ];
  };
  environment.systemPackages = with pkgs; [
    llamaCpp uv
    # No nvtop: nvtopPackages.nvidia builds against the unfree CUDA toolkit (cuda-merged).
    # nvidia-smi comes with the driver, and bench reads NVML directly.
    pciutils usbutils dmidecode acpica-tools lshw
    git tmux htop iw ethtool exfatprogs
  ];

  # ------------------------------------------------------------------ access
  services.openssh = {
    enable = true;
    settings.PasswordAuthentication = false;
    authorizedKeysFiles = [ "/mnt/sparkdata/ssh/authorized_keys" ];
  };
  services.getty.helpLine = lib.mkForce ''

    anvesana RTX Spark live image. Boot entry: see /etc/anvesana-boot-entry.
    Data drive (models, results): /mnt/sparkdata.   Start: docs/rtx-spark-replication.md
      bench inventory collect && bench run --only llm --tag nixos-$(cat /etc/anvesana-boot-entry)
  '';
}
