# GNOME live image for trying NixOS as the daily driver on bbaum-pc-7 (MSI Prestige N16 Flip AI+,
# NVIDIA RTX Spark N1X). Nothing is installed; the point is to see which parts of the laptop work
# and to bring the evidence back: `anvesana-collect` (nix/anvesana-collect.sh) writes this boot's
# journal and a per-subsystem snapshot to the SPARKDATA drive, under bootlogs/.
#
# When it collects:
#   2 min after boot      full snapshot ("boot")
#   every 5 min           journal + dmesg only, so a hang still leaves recent logs on the drive
#   30 s after resume     full snapshot ("resume"), for suspend tests, at idle priority
#   at shutdown/reboot    journal + dmesg ("shutdown")
#   on demand             the "Collect logs" app, or `sudo anvesana-collect full <label>`
#
# Boot entries. Linux needs SSPM (NVDA8400) exposed or USB and the keyboard do not work:
#   default        the SSPM DSDT override when built with ANVESANA_ACPI_OVERRIDE (--impure; boot
#                  that image from a stick written directly, not Ventoy), else acpi_osi="!Windows 2022";
#                  in the override build also n1x-lps0 (the firmware's Modern Standby calls around
#                  suspend) and nvidia_ffa_ec.oem_msi_ec=1 so that they reach MSI's EC
#   vblank         as default, plus nvidia_drm vblank=1 (known to stall GNOME; kept to retest)
#   serial         only without the override (scripts/vm-test.sh): console also on ttyAMA0
# Specialisations inherit the default entry's settings, so each adds only its difference.
{ config, lib, pkgs, modulesPath, ... }:

let
  acpiOverride = builtins.getEnv "ANVESANA_ACPI_OVERRIDE";
  override = acpiOverride != "";
  defaultName = if override then "sspm" else "osi";

  collect = pkgs.writeShellApplication {
    name = "anvesana-collect";
    runtimeInputs = with pkgs; [
      coreutils util-linux systemd gnugrep gnused gawk procps kmod iproute2 iw networkmanager
      bluez pciutils usbutils libinput alsa-utils pulseaudio v4l-utils upower power-profiles-daemon
      iio-sensor-proxy mesa-demos vulkan-tools gnome-shell libva-utils pipewire jq drm_info mutter glib
      tuned
    ] ++ [ (config.hardware.nvidia.package.bin or config.hardware.nvidia.package) ];   # nvidia-smi
    # The N1X UCM profiles (nix/n1x.nix); system services do not get session variables.
    runtimeEnv.ALSA_CONFIG_UCM2 = config.n1x.alsaUcm2;
    # Best-effort probes: no `set -e` (the script sets -u itself); shellcheck stays advisory.
    bashOptions = [ ];
    checkPhase = "";
    text = builtins.readFile ./anvesana-collect.sh;
  };
  # n1x-scp-peek and n1x-hub-test (EXP-20261110-q6a1yn, -rwymta) are no longer in the image:
  # the sensor hub works (boot 110078bc), and re-probing it hung on unbind. Their scripts stay
  # in nix/ for the run pages. n1x-sensors and n1x-pen come with nix/n1x-desktop.nix.
  # The launcher's command lives in a script: desktop-file Exec lines may not hold shell syntax.
  collectInteractive = pkgs.writeShellScriptBin "anvesana-collect-app" ''
    sudo ${collect}/bin/anvesana-collect full manual
    echo; read -r -p "Done. Press Enter to close. " _
  '';
  collectApp = pkgs.makeDesktopItem {
    name = "anvesana-collect";
    desktopName = "Collect logs";
    comment = "Save this boot's logs and a hardware snapshot to the SPARKDATA drive";
    icon = "utilities-system-monitor";
    terminal = true;
    exec = "${collectInteractive}/bin/anvesana-collect-app";
    categories = [ "System" ];
  };

in
{
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-graphical-gnome.nix"
    ./live-common.nix
    ./n1x-desktop.nix        # the desktop parts an installed N1X system shares with this image
  ];

  isoImage.volumeID = "ANV_DESK";
  isoImage.edition = lib.mkForce "gnome-n1x";

  # ------------------------------------------------------------------ boot entries
  boot.initrd.prepend = lib.mkIf override [
    "${builtins.path { path = acpiOverride; name = "acpi-override.cpio"; }}"
  ];
  environment.etc."anvesana-boot-entry".text = lib.mkDefault "${defaultName}\n";
  isoImage.appendToMenuLabel = lib.mkDefault " - ${defaultName} (GNOME)";

  # n1x-desktop.nix turns on n1x-lps0 (Modern Standby calls) and nvidia_ffa_ec.oem_msi_ec=1;
  # on the laptop only: n1x-lps0 finds no LPS0 device in a VM.
  n1x.lps0 = override;
  boot.kernelParams = lib.optional (!override) ''acpi_osi="!Windows 2022"'';

  # The safe-graphics, standby-notify and osi entries are gone (Ank, 2026-11-10: keep the
  # working entry and vblank=1); git history has them.
  specialisation = {
    vblank.configuration = {
      # Kept to come back to: GNOME on nvidia-drm stalled with vblank=1 (2026-11-07 and under
      # mutter 50.5 on 2026-11-09); see n1x.nvidiaVblank in nix/n1x.nix.
      n1x.nvidiaVblank = true;
      environment.etc."anvesana-boot-entry".text = lib.mkForce "${defaultName}-vblank\n";
      isoImage.appendToMenuLabel = lib.mkForce " - ${defaultName}, nvidia_drm vblank=1";
    };
  } // lib.optionalAttrs (!override) {
    # Only in the build without the override (the one scripts/vm-test.sh boots, whose default
    # entry is this one): the console also on ttyAMA0, captured as serial.log. The last
    # console= gets /dev/console, so systemd's status lines reach the serial port too.
    serial.configuration = {
      boot.kernelParams = [ "console=ttyAMA0,115200" ];
      environment.etc."anvesana-boot-entry".text = lib.mkForce "${defaultName}-serial\n";
      isoImage.appendToMenuLabel = lib.mkForce " - ${defaultName}, serial console (ttyAMA0)";
    };
  };

  # ------------------------------------------------------------------ desktop
  # Boot messages stay on screen (no splash), so a hang shows where it stopped.
  boot.plymouth.enable = lib.mkForce false;
  # The graphical installer base turns on VM guest agents; this image is for the laptop.
  services.spice-vdagentd.enable = lib.mkForce false;
  services.qemuGuest.enable = lib.mkForce false;
  virtualisation.hypervGuest.enable = lib.mkForce false;
  services.desktopManager.gnome.favoriteAppsOverride = lib.mkForce ''
    [org.gnome.shell]
    favorite-apps=[ 'anvesana-collect.desktop', 'org.gnome.Console.desktop', 'firefox.desktop', 'org.gnome.Nautilus.desktop', 'org.gnome.Settings.desktop' ]
  '';
  # The installer's GDM autologin user is `nixos` (uid 1000, passwordless sudo).

  environment.systemPackages = (with pkgs; [
    gnome-tweaks mpv glmark2 mesa-demos vulkan-tools v4l-utils alsa-utils pulseaudio libva-utils
    libinput evtest brightnessctl iw pciutils usbutils lshw dmidecode acpica-tools
    git htop powertop exfatprogs
  ]) ++ [ collect collectApp ];

  # ------------------------------------------------------------------ log collection
  systemd.services.anvesana-collect-boot = {
    description = "Collect logs and a hardware snapshot to SPARKDATA (boot)";
    after = [ "graphical.target" ];
    serviceConfig = { Type = "oneshot"; StandardOutput = "journal+console"; StandardError = "journal+console"; ExecStart = "${collect}/bin/anvesana-collect full boot"; };
  };
  systemd.timers.anvesana-collect-boot = {
    wantedBy = [ "timers.target" ];
    timerConfig.OnBootSec = "2min";
  };
  systemd.services.anvesana-collect-journal = {
    description = "Copy this boot's journal to SPARKDATA";
    serviceConfig = { Type = "oneshot"; StandardOutput = "journal+console"; StandardError = "journal+console"; ExecStart = "${collect}/bin/anvesana-collect journal periodic"; };
  };
  systemd.timers.anvesana-collect-journal = {
    wantedBy = [ "timers.target" ];
    timerConfig = { OnBootSec = "1min"; OnUnitActiveSec = "5min"; };
  };
  # Started at boot and stopped at shutdown: the stop runs while /mnt/sparkdata is still mounted.
  systemd.services.anvesana-collect-shutdown = {
    description = "Copy this boot's journal to SPARKDATA at shutdown";
    wantedBy = [ "multi-user.target" ];
    after = [ "mnt-sparkdata.mount" "systemd-journald.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      StandardOutput = "journal+console";
      StandardError = "journal+console";
      ExecStart = "${pkgs.coreutils}/bin/true";
      ExecStop = "${collect}/bin/anvesana-collect journal shutdown";
      TimeoutStopSec = "90s";
    };
  };
  # Kernel messages go to the console at debug level during boot (boot.consoleLogLevel 7, so a
  # hang shows where it stopped); once booted, only warnings and worse, so the console that shows
  # briefly around suspend and resume is not filled with driver chatter. dmesg keeps everything.
  boot.kernel.sysctl."kernel.printk" = "4 4 1 7";
  # Not before suspend: copying the journal to SPARKDATA held every suspend up by ~6 s, and a
  # second power-key press in that time woke the laptop at once. Resume works, and the 5-minute
  # copies still leave a recent log if it ever hangs.
  # The resume snapshot runs detached, 30 s after the wake, at idle priority: run in the resume
  # hook it took 20-35 s with ~10 s of CPU (nvidia-smi, vulkaninfo, ...) right while GNOME woke
  # the panel, and a lid close in that time waited for it: 11 s from lid to suspend (2026-11-10,
  # boot 43467edb). A suspend before it starts just runs it later; one already queued is kept.
  powerManagement.resumeCommands = ''
    ${pkgs.systemd}/bin/systemd-run --no-block --quiet --collect --unit=anvesana-collect-resume \
      --on-active=30s --timer-property=RemainAfterElapse=no \
      --property=Nice=19 --property=IOSchedulingClass=idle \
      ${collect}/bin/anvesana-collect full resume || true
  '';
  # Per-device suspend and resume times in dmesg ("PM: ... returned 0 after N usecs" for slow
  # ones), to find what the ~2.2-3.1 s the kernel spends per suspend/resume cycle goes on.
  systemd.tmpfiles.rules = [ "w /sys/power/pm_print_times - - - - 1" ];

  # For scripts/vm-test.sh only: `anvesana.vmtest_poweroff=<seconds>` on the kernel command line
  # powers off cleanly after that long (GNOME catches the VM's power button and asks instead).
  # Without the parameter the unit does not run.
  systemd.services.anvesana-vmtest-poweroff = {
    description = "Power off after anvesana.vmtest_poweroff seconds (VM tests)";
    wantedBy = [ "multi-user.target" ];
    unitConfig.ConditionKernelCommandLine = "anvesana.vmtest_poweroff";
    script = ''
      secs=$(tr ' ' '\n' </proc/cmdline | sed -n 's/^anvesana.vmtest_poweroff=//p')
      sleep "''${secs:-600}"
      systemctl poweroff
    '';
  };

  services.getty.helpLine = lib.mkForce ''

    anvesana GNOME live image (boot entry: /etc/anvesana-boot-entry). Logs go to SPARKDATA,
    bootlogs/: automatically, or now with `sudo anvesana-collect full <label>`.
  '';
}
