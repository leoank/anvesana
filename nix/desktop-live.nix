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
#                  that image from a stick written directly, not Ventoy), else acpi_osi="!Windows 2022"
#   osi            acpi_osi="!Windows 2022", all five hidden devices (only in an override build)
#   safe-graphics  as default, but the firmware framebuffer (simpledrm) instead of nvidia-drm
#   standby-notify as default, plus n1x-lps0: the firmware's Modern Standby calls around suspend,
#                  and nvidia_ffa_ec.oem_msi_ec=1 so that they reach MSI's EC
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

  # Refresh rate by power source: 120 Hz on AC, 60 Hz on battery, each as the variable refresh
  # rate mode ("…+vrr", panel Adaptive Sync 30-120 Hz) when mutter offers one, else fixed. GNOME
  # has no such switch itself; Windows runs this panel at 60 Hz on battery. `vrr=off` in
  # ~/.config/n1x-display-power keeps the fixed modes. Only with the built-in panel alone: a
  # `gdctl set` naming one monitor would turn every other one off.
  # mutter re-applies its own default (fixed 120 Hz) when the lid opens and after resume, so the
  # mode is checked again on each of mutter's MonitorsChanged signals too, against the current one.
  displayPower = pkgs.writeShellScript "n1x-display-power" ''
    conf=''${XDG_CONFIG_HOME:-$HOME/.config}/n1x-display-power
    last_set= last_time=0
    apply() {
      local show conns conn scale res hz modes mode cur vrr=on
      show=$(gdctl show --modes 2>&1) || { echo "gdctl show failed: $show"; return 1; }
      conns=$(printf '%s\n' "$show" | grep -oE '\b(eDP|DP|HDMI|DVI|VGA)-[0-9]+' | sort -u)
      if [ "$(printf '%s\n' "$conns" | grep -c .)" != 1 ]; then
        echo "monitors: $(echo $conns); leaving the configuration alone"; return 0
      fi
      cur=$(gdctl show 2>/dev/null | awk '/Current mode/ {getline; if (match($0, /[0-9]+x[0-9]+@[0-9.]+(\+vrr)?/)) print substr($0, RSTART, RLENGTH); exit}')
      conn=$conns
      scale=$(printf '%s\n' "$show" | grep -m1 -oE 'Scale: [0-9.]+' | grep -oE '[0-9.]+$')
      modes=$(printf '%s\n' "$show" | grep -oE '[0-9]+x[0-9]+@[0-9.]+(\+vrr)?' | sort -u)
      res=$(printf '%s\n' "$modes" | awk -F'[x@]' '{print $1*$2, $1 "x" $2}' | sort -n | tail -1 | cut -d' ' -f2)
      if [ "$(gdbus call --system --dest org.freedesktop.UPower --object-path /org/freedesktop/UPower \
          --method org.freedesktop.DBus.Properties.Get org.freedesktop.UPower OnBattery 2>/dev/null)" = "(<true>,)" ]; then
        hz=60; else hz=120; fi
      grep -qx 'vrr=off' "$conf" 2>/dev/null && vrr=off
      pick() { printf '%s\n' "$modes" | grep -E "^$res@" | grep $1 -E '\+vrr$' \
        | awk -F'[@+]' -v hz="$hz" '{d = $2 - hz; if (d < 0) d = -d; if (d < 0.5) print}' | head -1; }
      mode=
      [ "$vrr" = on ] && mode=$(pick "")
      [ -n "$mode" ] || mode=$(pick -v)
      [ -n "$mode" ] || { echo "no $res mode near $hz Hz in: $(echo $modes)"; return 0; }
      [ "$mode" = "$cur" ] && return 0
      # The same mode again within 30 s means it did not stick (or reads back under another
      # name): stop rather than loop on our own MonitorsChanged.
      if [ "$mode" = "$last_set" ] && [ $(( $(date +%s) - last_time )) -lt 30 ]; then
        echo "$conn: $mode set $(( $(date +%s) - last_time )) s ago but current is ''${cur:-?}; not retrying"
        return 0
      fi
      # --persistent stores it in monitors.xml, so mutter restores this mode itself on resume
      # and lid open instead of its fixed 120 Hz default, which this script then had to replace
      # with a second modeset ~3 s after each wake (2026-11-10, boot 43467edb).
      if gdctl set --persistent --logical-monitor --primary ''${scale:+--scale "$scale"} --monitor "$conn" --mode "$mode"; then
        last_set=$mode; last_time=$(date +%s)
        echo "$conn: ''${cur:-?} -> $mode (scale ''${scale:-preferred}; $([ "$hz" = 60 ] && echo battery || echo AC); vrr $vrr)"
      else
        # Not counted as set: with the lid closed mutter refuses ("Refusing to activate a closed
        # laptop panel"), and counting it blocked the retry after the lid opened.
        echo "gdctl set $conn $mode failed"
      fi
    }
    for _ in $(seq 30); do gdctl show >/dev/null 2>&1 && break; sleep 1; done
    apply
    # Power source changes (UPower OnBattery) and mutter's own reconfigurations (lid, resume,
    # hotplug: MonitorsChanged), one event stream; our own change raises one more, a no-op.
    { gdbus monitor --system --dest org.freedesktop.UPower --object-path /org/freedesktop/UPower &
      gdbus monitor --session --dest org.gnome.Mutter.DisplayConfig --object-path /org/gnome/Mutter/DisplayConfig
    } | while read -r line; do
      case $line in *OnBattery*|*MonitorsChanged*) sleep 1; apply ;; esac
    done
  '';
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
    standby-notify.configuration = {
      n1x.lps0 = true;
      # The Modern Standby functions reach MSI's EC over FF-A (nix/kernel.nix, patch 0003).
      boot.kernelParams = [ "nvidia_ffa_ec.oem_msi_ec=1" ];
      environment.etc."anvesana-boot-entry".text = lib.mkForce "${defaultName}-standby-notify\n";
      isoImage.appendToMenuLabel = lib.mkForce " - ${defaultName}, tell firmware about standby (LPS0)";
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
  # The ELAN pen screen (ELAN9024, i2c 04f3:4516) is not in libwacom 2.18, so Settings > Wacom
  # Tablet called it "Unknown device". Same form as libwacom's other ELAN entries; size from
  # libinput (343 x 214 mm, in inches).
  environment.etc."libwacom/elan-4516.tablet".text = ''
    [Device]
    Name=ELAN 4516
    ModelName=
    DeviceMatch=i2c|04f3|4516
    Class=ISDV4
    Width=14
    Height=8
    IntegratedIn=Display;System

    [Features]
    Stylus=true
    Touch=true
  '';
  # OLED: dark pixels draw less power, so dark by default (Settings > Appearance changes it).
  services.desktopManager.gnome.extraGSettingsOverrides = ''
    [org.gnome.desktop.interface]
    color-scheme='prefer-dark'
  '';
  # Power profiles (GNOME quick settings): power-profiles-daemon has no driver for this CPU
  # (cppc_cpufreq; it showed only balanced and power-saver, "placeholder"), so TuneD serves the
  # same D-Bus API (tuned-ppd) with all three. The CPUs run in autonomous mode (n1x-cppc-init:
  # auto_select=1), where the firmware picks clocks and the energy/performance preference
  # (0 = performance … 255 = energy) is the knob; balanced keeps the firmware's 127, on battery
  # it leans to energy. Nothing caps clocks.
  services.tuned = {
    enable = true;
    ppdSettings = {
      main.default = "balanced";
      profiles = { power-saver = "n1x-power-saver"; balanced = "n1x-balanced"; performance = "n1x-performance"; };
      battery = { balanced = "n1x-balanced-battery"; };
    };
    profiles = lib.mapAttrs (name: epp: {
      main.summary = "N1X: energy/performance preference ${toString epp} (0 performance, 255 energy)";
      cpu_epp = { type = "sysfs"; "/sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference_val" = epp; };
    }) { n1x-performance = 0; n1x-balanced = 127; n1x-balanced-battery = 192; n1x-power-saver = 255; };
  };
  systemd.services.tuned.after = [ "n1x-cppc-init.service" ];
  systemd.user.services.n1x-display-power = {
    description = "Refresh rate by power source (120 Hz AC, 60 Hz battery, VRR when offered)";
    wantedBy = [ "graphical-session.target" ];
    partOf = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];
    path = [ pkgs.mutter pkgs.glib pkgs.coreutils pkgs.gnugrep pkgs.gawk ];
    serviceConfig = { ExecStart = displayPower; Restart = "on-failure"; RestartSec = 10; };
  };
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
  # n1x.nix ignores the lid (the benchmark image must not sleep mid-run); a laptop desktop should
  # suspend on lid close, on battery and on AC.
  # logind ignores the lid for HoldoffTimeoutSec after boot and after each resume (default 30 s),
  # so a lid closed soon after waking did nothing (2026-11-10 boot 263fd165: closed 7 s after).
  services.logind.settings.Login = {
    HandleLidSwitch = lib.mkForce "suspend";
    HandleLidSwitchExternalPower = lib.mkForce "suspend";
    HoldoffTimeoutSec = "5s";
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
