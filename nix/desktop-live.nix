# GNOME live image for trying NixOS as the daily driver on bbaum-pc-7 (MSI Prestige N16 Flip AI+,
# NVIDIA RTX Spark N1X). Nothing is installed; the point is to see which parts of the laptop work
# and to bring the evidence back: `anvesana-collect` (nix/anvesana-collect.sh) writes this boot's
# journal and a per-subsystem snapshot to the SPARKDATA drive, under bootlogs/.
#
# When it collects:
#   2 min after boot      full snapshot ("boot")
#   every 5 min           journal + dmesg only, so a hang still leaves recent logs on the drive
#   before suspend        journal + dmesg ("suspend"), so a resume that hangs still leaves logs
#   after resume          full snapshot ("resume"), for suspend tests
#   at shutdown/reboot    journal + dmesg ("shutdown")
#   on demand             the "Collect logs" app, or `sudo anvesana-collect full <label>`
#
# Boot entries. Linux needs SSPM (NVDA8400) exposed or USB and the keyboard do not work:
#   default        the SSPM DSDT override when built with ANVESANA_ACPI_OVERRIDE (--impure; boot
#                  that image from a stick written directly, not Ventoy), else acpi_osi="!Windows 2022"
#   osi            acpi_osi="!Windows 2022", all five hidden devices (only in an override build)
#   safe-graphics  as default, but the firmware framebuffer (simpledrm) instead of nvidia-drm
#   serial         as default, with the console also on ttyAMA0 (QEMU, or a serial adapter)
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
      iio-sensor-proxy mesa-demos vulkan-tools gnome-shell libva-utils pipewire jq
    ] ++ [ (config.hardware.nvidia.package.bin or config.hardware.nvidia.package) ];   # nvidia-smi
    # The N1X UCM profiles (nix/n1x.nix); system services do not get session variables.
    runtimeEnv.ALSA_CONFIG_UCM2 = config.n1x.alsaUcm2;
    # Best-effort probes: no `set -e` (the script sets -u itself); shellcheck stays advisory.
    bashOptions = [ ];
    checkPhase = "";
    text = builtins.readFile ./anvesana-collect.sh;
  };
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
  ];

  isoImage.volumeID = "ANV_DESK";
  isoImage.edition = lib.mkForce "gnome-n1x";

  # ------------------------------------------------------------------ boot entries
  boot.initrd.prepend = lib.mkIf override [
    "${builtins.path { path = acpiOverride; name = "acpi-override.cpio"; }}"
  ];
  boot.kernelParams = lib.mkIf (!override) [ ''acpi_osi="!Windows 2022"'' ];
  environment.etc."anvesana-boot-entry".text = lib.mkDefault "${defaultName}\n";
  isoImage.appendToMenuLabel = lib.mkDefault " - ${defaultName} (GNOME)";

  specialisation = {
    safe-graphics.configuration = {
      n1x.nvidiaDisplay = false;
      environment.etc."anvesana-boot-entry".text = lib.mkForce "${defaultName}-safe-graphics\n";
      isoImage.appendToMenuLabel = lib.mkForce " - ${defaultName}, safe graphics (simpledrm)";
    };
    serial.configuration = {
      # The last console= gets /dev/console, so systemd's status lines reach the serial port too;
      # the kernel's own messages go to both.
      boot.kernelParams = [ "console=ttyAMA0,115200" ];
      environment.etc."anvesana-boot-entry".text = lib.mkForce "${defaultName}-serial\n";
      isoImage.appendToMenuLabel = lib.mkForce " - ${defaultName}, serial console (ttyAMA0)";
    };
  } // lib.optionalAttrs override {
    osi.configuration = {
      boot.initrd.prepend = lib.mkForce [ ];
      boot.kernelParams = [ ''acpi_osi="!Windows 2022"'' ];
      environment.etc."anvesana-boot-entry".text = lib.mkForce "osi\n";
      isoImage.appendToMenuLabel = lib.mkForce " - osi (acpi_osi !Windows 2022)";
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
  # Firefox decodes video through VA-API (nvidia-vaapi-driver, nix/n1x.nix); its README asks for
  # these prefs and an unsandboxed RDD process.
  programs.firefox = {
    enable = true;
    preferences = {
      "media.ffmpeg.vaapi.enabled" = true;
      "media.hardware-video-decoding.force-enabled" = true;
      "widget.dmabuf.force-enabled" = true;
    };
  };
  environment.sessionVariables.MOZ_DISABLE_RDD_SANDBOX = "1";
  n1x.speakerDsp = true;                          # "Speakers (DSP)" output to compare by ear
  hardware.bluetooth.enable = true;
  hardware.sensor.iio.enable = true;              # accelerometer: auto-rotate in tablet mode
  services.fprintd.enable = false;
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
  # Before each suspend too: a resume that never comes back still leaves the log up to the suspend.
  powerManagement.powerDownCommands = "${collect}/bin/anvesana-collect journal suspend || true";
  powerManagement.resumeCommands ="${collect}/bin/anvesana-collect full resume || true";

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
