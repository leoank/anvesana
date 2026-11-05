# Hardware support for NVIDIA RTX Spark (N1X) laptops, written for bbaum-pc-7
# (MSI Prestige N16 Flip AI+). Shared by the live image (nix/live.nix) and,
# later, an installed system: import `anvesana.nixosModules.n1x`.
#
# Taken from the ASUS ProArt P16 Arch build (github.com/pfeifferj/archlinuxarm-proart-p16
# @ 3484cc0, MIT) minus its ASUS-only parts (hid-asus, ASUS audio/amp firmware):
#   kernel      Ubuntu linux-nvidia-7.0 7.0.0-1022 (Linux 7.0.14) + ACPI-override allocation fix
#   NVIDIA      615.78.08 open modules, nvidia-drm modeset + fbdev, with the aarch64 DRM
#               mapping fix and the PR #1368 leak fix; `n1x.nvidiaDisplay = false`
#               falls back to simpledrm
#   CPU         CPPC autonomous frequency selection, as Windows does
#   initrd      NVMe, the MediaTek xHCI and the I2C/USB input drivers
#   sleep       lid / suspend keys ignored: suspend is not qualified on N1X Linux
{ config, lib, pkgs, ... }:

let
  cfg = config.n1x;
  kernel = pkgs.callPackage ./kernel.nix { };
  # ProArt Arch build, 03-system/power/payload/assets/hardware/power/n1x-cppc-init.py:
  # restore each policy's full range, then let the firmware pick CPU clocks.
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
  options.n1x = {
    nvidiaDisplay = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Drive the display with nvidia-drm (modeset, fbdev). False keeps simpledrm.";
    };
  };

  config = {
    nixpkgs.config.allowUnfreePredicate = pkg: builtins.elem (lib.getName pkg) [ "nvidia-x11" "nvidia-settings" ];

    # ---------------------------------------------------------------- kernel
    boot.kernelPackages = pkgs.linuxPackagesFor kernel;
    boot.initrd.availableKernelModules = [
      "nvme" "xhci_pci" "xhci_plat_hcd" "xhci_mtk_hcd" "usb_storage" "uas"
      "i2c_mt65xx" "i2c_hid_acpi" "usbhid" "hid_generic" "hid_multitouch"
    ];
    hardware.enableRedistributableFirmware = true;

    # ---------------------------------------------------------------- NVIDIA
    services.xserver.videoDrivers = [ "nvidia" ];   # selects hardware.nvidia; enables no X server by itself
    hardware.graphics.enable = true;
    hardware.nvidia = {
      open = true;
      modesetting.enable = cfg.nvidiaDisplay;       # nvidia_drm modeset=1 fbdev=1
      nvidiaSettings = false;
      powerManagement.enable = false;
      package = config.boot.kernelPackages.nvidiaPackages.mkDriver {
        version = "615.78.08";
        sha256_aarch64 = "5076011350181e81a031f0fd012fe35fe4be37c7820d651fb7aaa894af447a37";
        # NAR hash of NVIDIA/open-gpu-kernel-modules at tag 615.78.08: not
        # computable without Nix; the first build prints it.
        openSha256 = lib.fakeHash;
        patchesOpen = [
          ./patches/nvidia-open-drm-aarch64-mappings.patch
          ./patches/nvidia-open-pr1368-semsurf-leak.patch
        ];
        useSettings = false;
        usePersistenced = false;
      };
    };
    # The ProArt's qualified tuple also sets vblank=1 (h7607a-nvidia.conf); an
    # unknown parameter is logged and ignored, so it is harmless if 615 lacks it.
    boot.extraModprobeConfig = lib.mkIf cfg.nvidiaDisplay "options nvidia_drm vblank=1";

    # ---------------------------------------------------------------- power
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
    services.logind.settings.Login = {
      IdleAction = "ignore";
      HandleLidSwitch = "ignore";
      HandleLidSwitchExternalPower = "ignore";
      HandleLidSwitchDocked = "ignore";
      HandleSuspendKey = "ignore";
      HandleHibernateKey = "ignore";
    };
    services.upower.enable = true;
  };
}
