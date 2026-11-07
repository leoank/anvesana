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
  # No HTML docs on a benchmark image: python3.12's doc output is not cached and its Sphinx
  # build fails in nixos-26.05 (docutils 0.22 TypeError in parse_enumerator, 2026-11-06).
  documentation.doc.enable = false;
  # The installation-CD profile lists generic initrd drivers (e.g. pata_pcmcia) that Ubuntu's
  # arm64 nvidia config does not build; let the initrd's module closure skip those.
  nixpkgs.overlays = [
    (final: prev: {
      makeModulesClosure = args: prev.makeModulesClosure (args // { allowMissing = true; });
    })
  ];
  isoImage.volumeID = "ANV_SPARK";
  networking.hostName = "bbaum-pc-7";   # matches machines/bbaum-pc-7.toml
  boot.supportedFilesystems = lib.mkForce [ "vfat" "exfat" "ext4" "iso9660" "squashfs" "overlay" ];
  boot.kernelParams = [ "console=tty0" "loglevel=7" ];
  # A live image with no secrets: let the initrd's emergency shell open without a password, so a
  # failed boot (e.g. USB controllers not probing, 2026-11-06) can be inspected with dmesg.
  boot.initrd.systemd.emergencyAccess = true;
  # Without power_wrap neither USB nor the I2C keyboard works, so the shell cannot be used:
  # on emergency, print the kernel lines that explain it to the console, for a photo.
  boot.initrd.systemd.initrdBin = [ pkgs.gnugrep ];   # dmesg: the initrd's util-linux-minimal
  boot.initrd.systemd.contents."/etc/anvesana-diag.sh".text = ''
    sleep 2
    echo; echo "=== anvesana boot diagnostics ==="
    echo "cmdline: $(cat /proc/cmdline | grep -oE 'init=[^ ]*|acpi_osi=[^ ]*( [^ ]*)?' | tr '\n' ' ')"
    for d in NVDA8400:00 NVDA6210:00; do
      s=$(cat /sys/bus/acpi/devices/$d/status 2>/dev/null || echo absent)
      drv=$(basename "$(readlink /sys/bus/platform/devices/$d/driver 2>/dev/null)" 2>/dev/null)
      echo "$d: _STA=$s driver=''${drv:-none}"
    done
    dmesg | grep -iE 'Table Upgrade|ACPI: (DSDT|SSDT).*(Override|Upgrade|OEM)|override|_OSI|sspm|NVDA8400|SSPM_CI|mbox|power_wrap|NVDA6210|DPM config|DPMT|platform id|BestPerf|DVFSRC|USB4' \
      | grep -v 'mtk_pwrap_dev_probe' | head -n 30
    dmesg | grep -m2 'scmi ret'
    echo "=== end ==="
  '';
  boot.initrd.systemd.services.anvesana-boot-diag = {
    description = "Print power_wrap / SSPM probe messages to the console";
    wantedBy = [ "emergency.target" ];
    unitConfig.DefaultDependencies = false;
    serviceConfig = {
      Type = "oneshot";
      StandardOutput = "tty";
      TTYPath = "/dev/console";
      ExecStart = "/bin/sh /etc/anvesana-diag.sh";
    };
  };

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
    # No nvtop: nvtopPackages.nvidia builds against the unfree CUDA toolkit (cuda-merged).
    # nvidia-smi comes with the driver, and bench reads NVML directly.
    pciutils usbutils dmidecode acpica-tools lshw
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
