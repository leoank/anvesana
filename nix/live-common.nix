# What every anvesana live image for bbaum-pc-7 (MSI Prestige N16 Flip AI+, NVIDIA RTX Spark N1X)
# shares: N1X hardware support, the SPARKDATA data drive, the repo checkout with `bench`, and the
# initrd diagnostics that print the power_wrap / SSPM state when a boot fails before USB works.
# Imported by nix/live.nix (benchmark image) and nix/desktop-live.nix (GNOME daily-driver test).
{ config, lib, pkgs, anvesanaSrc, ... }:

let
  python = pkgs.python312.withPackages (ps: [ ps.psutil ps.numpy ps.nvidia-ml-py ]);
  bench = pkgs.writeShellScriptBin "bench" ''
    export PYTHONPATH=/root/anvesana/src
    exec ${python}/bin/python3 -m anvesana "$@"
  '';
in
{
  # Kernel, NVIDIA (with nvidia-drm and the ProArt display fixes), CPU init,
  # initrd modules and sleep policy are in n1x.nix, shared with an installed system.
  imports = [ ./n1x.nix ];

  nixpkgs.hostPlatform = "aarch64-linux";
  # No HTML docs: python3.12's doc output is not cached and its Sphinx build fails in
  # nixos-26.05 (docutils 0.22 TypeError in parse_enumerator, 2026-11-06).
  documentation.doc.enable = false;
  # The installation-CD profiles list generic initrd drivers (e.g. pata_pcmcia) that Ubuntu's
  # arm64 nvidia config does not build; let the initrd's module closure skip those.
  nixpkgs.overlays = [
    (final: prev: {
      makeModulesClosure = args: prev.makeModulesClosure (args // { allowMissing = true; });
    })
  ];
  networking.hostName = "bbaum-pc-7";   # matches machines/bbaum-pc-7.toml
  boot.supportedFilesystems = lib.mkForce [ "vfat" "exfat" "ext4" "iso9660" "squashfs" "overlay" ];
  boot.kernelParams = [ "console=tty0" ];
  # Every kernel message on screen during boot. A `loglevel=7` kernel parameter does not do it:
  # NixOS appends its own loglevel (boot.consoleLogLevel, default 4) later on the command line.
  boot.consoleLogLevel = 7;

  # ------------------------------------------------------------------ failed-boot diagnostics
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

  # ------------------------------------------------------------------ data drive
  fileSystems."/mnt/sparkdata" = {
    device = "/dev/disk/by-label/SPARKDATA";
    fsType = "exfat";
    # Mounted on first access: USB comes up late on N1X (after power_wrap/SSPM), and a plain
    # mount with a 10 s device timeout gave up before the drive appeared (2026-11-07).
    options = [ "nofail" "x-systemd.automount" "uid=0" "gid=0" "fmask=0022" "dmask=0022" ];
  };
  environment.variables.ANVESANA_RESULTS_DIR = "/mnt/sparkdata/results";

  # ------------------------------------------------------------------ repo and bench
  environment.systemPackages = [ bench python ];
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

  # NetworkManager turns on networking.wireless itself (wpa_supplicant under D-Bus control); forcing
  # it off left NetworkManager unable to start wpa_supplicant: no Wi-Fi (laptop, 2026-11-07).
  networking.networkmanager.enable = true;
  system.stateVersion = "26.05";
}
