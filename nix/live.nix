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
#
# Persistent data lives on a second USB drive labelled SPARKDATA (exFAT):
#   models/   GGUF files (scripts/llm-fetch.py; same layout on every OS)
#   results/  the anvesana results store, so runs survive the live session
#   ssh/authorized_keys   optional; enables SSH login as root
{ config, lib, pkgs, modulesPath, anvesanaSrc, ... }:

let
  kernel = pkgs.callPackage ./kernel.nix { };
  llamaCpp = pkgs.callPackage ./llama-cpp-bin.nix { };
  acpiOverride = builtins.getEnv "ANVESANA_ACPI_OVERRIDE";
  python = pkgs.python312.withPackages (ps: [ ps.psutil ps.numpy ps.nvidia-ml-py ]);
  bench = pkgs.writeShellScriptBin "bench" ''
    export PYTHONPATH=/root/anvesana/src
    exec ${python}/bin/python3 -m anvesana "$@"
  '';
  # ProArt Arch build, 03-system/power/payload/assets/hardware/power/n1x-cppc-init.py:
  # restore each policy's full range, then let the firmware pick CPU clocks (CPPC
  # autonomous selection), as Windows does. Without it the CPU side is biased.
  cppcInit = pkgs.writeText "n1x-cppc-init.py" ''
    from pathlib import Path
    if any(Path('/sys/bus/acpi/devices').glob('NVDA0200:*')):
        for policy in Path('/sys/devices/system/cpu/cpufreq').glob('policy*'):
            driver, auto = policy / 'scaling_driver', policy / 'auto_select'
            if not driver.exists() or driver.read_text().strip() != 'cppc_cpufreq' or not auto.exists():
                continue
            low = int((policy / 'cpuinfo_min_freq').read_text())
            high = int((policy / 'cpuinfo_max_freq').read_text())
            if not 0 < low <= high:
                raise RuntimeError(f'Invalid frequency range in {policy}')
            auto.write_text('0\n')
            (policy / 'scaling_min_freq').write_text(f'{low}\n')
            (policy / 'scaling_max_freq').write_text(f'{high}\n')
            auto.write_text('1\n')
            print(f'{policy.name}: {low}..{high} kHz; autonomous selection enabled')
  '';
in
{
  imports = [ "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix" ];

  nixpkgs.hostPlatform = "aarch64-linux";
  nixpkgs.config.allowUnfreePredicate = pkg: builtins.elem (lib.getName pkg) [ "nvidia-x11" "nvidia-settings" ];
  isoImage.volumeID = "ANV_SPARK";
  networking.hostName = "bbaum-pc-7";   # matches machines/bbaum-pc-7.toml

  # ------------------------------------------------------------------ kernel
  boot.kernelPackages = pkgs.linuxPackagesFor kernel;
  boot.supportedFilesystems = lib.mkForce [ "vfat" "exfat" "ext4" "iso9660" "squashfs" "overlay" ];
  # ProArt initrd list without the ASUS-only drivers: NVMe, USB (incl. the
  # MediaTek xHCI) and the I2C/USB input devices, so the console has a keyboard.
  boot.initrd.availableKernelModules = [
    "nvme" "xhci_pci" "xhci_plat_hcd" "xhci_mtk_hcd" "usb_storage" "uas"
    "i2c_mt65xx" "i2c_hid_acpi" "usbhid" "hid_generic" "hid_multitouch"
  ];
  boot.kernelParams = [ "console=tty0" "loglevel=7" ];
  hardware.enableRedistributableFirmware = true;

  # ------------------------------------------------------------------ NVIDIA
  # 615.78.08 with the open kernel modules: the tuple that runs CUDA on the
  # ProArt P16. Display stays on simpledrm (nvidia-drm modeset off): this image
  # is a console for benchmarks, and the DRM fixes the ProArt needed for a
  # desktop are not needed here.
  services.xserver.videoDrivers = [ "nvidia" ];   # selects hardware.nvidia; no X server is enabled
  hardware.graphics.enable = true;
  hardware.nvidia = {
    open = true;
    modesetting.enable = false;
    nvidiaSettings = false;
    powerManagement.enable = false;
    package = config.boot.kernelPackages.nvidiaPackages.mkDriver {
      version = "615.78.08";
      sha256_aarch64 = "5076011350181e81a031f0fd012fe35fe4be37c7820d651fb7aaa894af447a37";
      # NAR hash of NVIDIA/open-gpu-kernel-modules at tag 615.78.08: not
      # computable without Nix; the first build prints it (see the docs).
      openSha256 = lib.fakeHash;
      useSettings = false;
      usePersistenced = false;
    };
  };

  # ------------------------------------------------------------------ boot entries
  specialisation = {
    osi.configuration = {
      boot.kernelParams = [ ''acpi_osi="!Windows 2022"'' ];
      environment.etc."anvesana-boot-entry".text = "osi\n";
    };
  } // lib.optionalAttrs (acpiOverride != "") {
    sspm.configuration = {
      boot.initrd.prepend = [ "${builtins.path { path = acpiOverride; name = "acpi-override.cpio"; }}" ];
      environment.etc."anvesana-boot-entry".text = "sspm\n";
    };
  };
  environment.etc."anvesana-boot-entry".text = lib.mkDefault "default\n";

  # ------------------------------------------------------------------ power
  systemd.services.n1x-cppc-init = {
    description = "Initialize NVIDIA N1X autonomous CPU frequency selection";
    wantedBy = [ "multi-user.target" ];
    unitConfig.ConditionPathExistsGlob = "/sys/bus/acpi/devices/NVDA0200:*";
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStartPre = "-${pkgs.kmod}/bin/modprobe cppc_cpufreq";
      ExecStart = "${pkgs.python3}/bin/python3 ${cppcInit}";
    };
  };
  # Suspend is not qualified on N1X Linux; never let a lid or idle timer end a run.
  services.logind.settings.Login = {
    IdleAction = "ignore";
    HandleLidSwitch = "ignore";
    HandleLidSwitchExternalPower = "ignore";
    HandleLidSwitchDocked = "ignore";
    HandleSuspendKey = "ignore";
    HandleHibernateKey = "ignore";
  };
  services.upower.enable = true;   # battery / AC state for psutil and the on_ac column

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
