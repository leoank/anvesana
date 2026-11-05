# NixOS live USB for native-Linux benchmarks on the NVIDIA RTX Spark (N1X)
# laptops, built for bbaum-pc-7 (MSI Prestige N16 Flip AI+). See
# docs/rtx-spark-replication.md for why each piece is here.
#
# Boot entries (one image, chosen in the boot menu):
#   default     stock firmware ACPI tables
#   osi         acpi_osi="!Windows 2022": Linux stops claiming Windows 2022, so
#               every device hidden from it appears (SVP0, SSPM, HFRP, NH1X, NMAP)
#   sspm        DSDT override that exposes only SSPM (NVDA8400); built only when
#               ANVESANA_ACPI_OVERRIDE names a cpio from scripts/acpi-hidden-devices.py
#               (it holds MSI's tables, so it never enters git) and --impure is passed
#   simpledrm   stock ACPI, display on the firmware framebuffer instead of nvidia-drm
#               (fallback if the patched nvidia-drm gives no picture on this panel)
# All entries but simpledrm drive the display with nvidia-drm, as a desktop would.
#
# Persistent data lives on a second USB drive labelled SPARKDATA (exFAT):
#   models/   GGUF files (scripts/llm-fetch.py; same layout on every OS)
#   results/  the anvesana results store, so runs survive the live session
#   ssh/authorized_keys   optional; enables SSH login as root
{ config, lib, pkgs, modulesPath, anvesanaSrc, ... }:

let
  llamaCpp = pkgs.callPackage ./llama-cpp-bin.nix { };
  acpiOverride = builtins.getEnv "ANVESANA_ACPI_OVERRIDE";
  python = pkgs.python312.withPackages (ps: [ ps.psutil ps.numpy ps.nvidia-ml-py ]);
  bench = pkgs.writeShellScriptBin "bench" ''
    export PYTHONPATH=/root/anvesana/src
    exec ${python}/bin/python3 -m anvesana "$@"
  '';
in
{
  # Kernel, NVIDIA (with nvidia-drm and the ProArt display fixes), CPU init,
  # initrd modules and sleep policy are in n1x.nix, shared with an installed system.
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
    ./n1x.nix
  ];

  nixpkgs.hostPlatform = "aarch64-linux";
  isoImage.volumeID = "ANV_SPARK";
  networking.hostName = "bbaum-pc-7";   # matches machines/bbaum-pc-7.toml
  boot.supportedFilesystems = lib.mkForce [ "vfat" "exfat" "ext4" "iso9660" "squashfs" "overlay" ];
  boot.kernelParams = [ "console=tty0" "loglevel=7" ];

  # ------------------------------------------------------------------ boot entries
  specialisation = {
    osi.configuration = {
      boot.kernelParams = [ ''acpi_osi="!Windows 2022"'' ];
      environment.etc."anvesana-boot-entry".text = "osi\n";
    };
    # Display fallback: if nvidia-drm gives no picture, this entry keeps the firmware framebuffer.
    simpledrm.configuration = {
      n1x.nvidiaDisplay = false;
      environment.etc."anvesana-boot-entry".text = "simpledrm\n";
    };
  } // lib.optionalAttrs (acpiOverride != "") {
    sspm.configuration = {
      boot.initrd.prepend = [ "${builtins.path { path = acpiOverride; name = "acpi-override.cpio"; }}" ];
      environment.etc."anvesana-boot-entry".text = "sspm\n";
    };
  };
  environment.etc."anvesana-boot-entry".text = lib.mkDefault "default\n";

  # ------------------------------------------------------------------ data drive
  fileSystems."/mnt/sparkdata" = {
    device = "/dev/disk/by-label/SPARKDATA";
    fsType = "exfat";
    options = [ "nofail" "x-systemd.device-timeout=10s" "uid=0" "gid=0" "fmask=0022" "dmask=0022" ];
  };
  environment.variables = {
    ANVESANA_MODELS_DIR = "/mnt/sparkdata/models";
    ANVESANA_RESULTS_DIR = "/mnt/sparkdata/results";
    ANVESANA_LLAMA_BENCH = "${llamaCpp}/bin/llama-bench";
  };

  # ------------------------------------------------------------------ tools
  # nix-ld runs the prebuilt llama.cpp and uv-managed Python (vLLM, optional).
  programs.nix-ld = {
    enable = true;
    libraries = with pkgs; [ stdenv.cc.cc.lib zlib openssl curl config.hardware.nvidia.package ];
  };
  environment.systemPackages = with pkgs; [
    bench python llamaCpp uv
    pciutils usbutils dmidecode acpica-tools lshw nvtopPackages.nvidia
    git tmux htop iw ethtool exfatprogs
  ];

  # The repo at the commit the image was built from, copied writable at boot.
  environment.etc."anvesana-src".source = anvesanaSrc;
  systemd.services.anvesana-checkout = {
    description = "Writable copy of the anvesana repo in /root/anvesana";
    wantedBy = [ "multi-user.target" ];
    serviceConfig.Type = "oneshot";
    script = ''
      if [ ! -d /root/anvesana ]; then
        cp -r --no-preserve=mode,ownership /etc/anvesana-src /root/anvesana
      fi
    '';
  };

  # ------------------------------------------------------------------ access
  networking.networkmanager.enable = true;
  networking.wireless.enable = lib.mkForce false;
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

  system.stateVersion = "26.05";
}
