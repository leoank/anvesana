# Desktop support for an N1X laptop on GNOME (bbaum-pc-7, MSI Prestige N16 Flip AI+): what the
# live desktop image (nix/desktop-live.nix) tested, without the live-image parts (log
# collection, boot entries, ISO). Exported as `nixosModules.n1x-desktop`; use it together with
# `nixosModules.n1x` and a GNOME desktop. Findings behind each piece: docs/n1x-linux.md.
{ config, lib, pkgs, ... }:

let
  # `sudo n1x-sensors`: the accelerometers and the hub's custom (hinge/lid angle) sensors in
  # four postures, for auto-rotate and a tablet-mode switch.
  sensorsTool = let
    py = pkgs.writeText "n1x-sensors.py" (builtins.readFile ./n1x-sensors.py);
  in pkgs.writeShellScriptBin "n1x-sensors" ''
    export PATH=${lib.makeBinPath [ pkgs.iio-sensor-proxy pkgs.systemd pkgs.coreutils ]}:$PATH
    exec ${pkgs.python3}/bin/python3 ${py} "$@"
  '';
  # `n1x-pen softer`, `n1x-pen range 0 40`, `n1x-pen save`: the pen's pressure range and curve.
  penTool = pkgs.writeShellApplication {
    name = "n1x-pen";
    runtimeInputs = with pkgs; [ dconf coreutils gnugrep gnused libinput util-linux ];
    bashOptions = [ ];          # the script sets -u itself; a failed dconf read is not fatal
    text = builtins.readFile ./n1x-pen.sh;
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
      # Not --persistent: GNOME Shell asks "Keep these display settings?" for every persistent
      # change, so it asked at each login and charger change (Ank, 2026-11-11). Without it mutter
      # brings back its own default on resume and this script switches again ~3 s later.
      if gdctl set --logical-monitor --primary ''${scale:+--scale "$scale"} --monitor "$conn" --mode "$mode"; then
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
  # Modern Standby: n1x-lps0 makes the firmware's LPS0 calls around suspend (2026-11-10, boots
  # c542daee and 72000af6: 0 failed, keyboard light off in standby), and they reach MSI's EC over
  # FF-A (nix/kernel.nix, patch 0003). mkDefault: a VM build turns it off (no LPS0 device there).
  n1x.lps0 = lib.mkDefault true;
  boot.kernelParams = [ "nvidia_ffa_ec.oem_msi_ec=1" ];

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
  # The pen's pressure feel saved with `n1x-pen save` (on SPARKDATA, since a live image forgets
  # dconf), applied at login and to a stylus GNOME first sees later on.
  systemd.user.services.n1x-pen = {
    description = "Apply the saved pen pressure setting (n1x-pen)";
    wantedBy = [ "graphical-session.target" ];
    partOf = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];
    serviceConfig = { ExecStart = "${penTool}/bin/n1x-pen apply"; Restart = "on-failure"; RestartSec = 10; };
  };
  # Firefox decodes video through VA-API (nvidia-vaapi-driver, nix/n1x.nix); its README asks for
  # these prefs and an unsandboxed RDD process.
  programs.firefox = {
    enable = lib.mkDefault true;
    preferences = {
      "media.ffmpeg.vaapi.enabled" = true;
      "media.hardware-video-decoding.force-enabled" = true;
      "widget.dmabuf.force-enabled" = true;
    };
  };
  environment.sessionVariables.MOZ_DISABLE_RDD_SANDBOX = "1";
  n1x.speakerDsp = lib.mkDefault true;           # "Speakers (DSP)" output, opt-in in the sound menu
  hardware.bluetooth.enable = lib.mkDefault true;
  hardware.sensor.iio.enable = lib.mkDefault true;
  services.fprintd.enable = lib.mkDefault false;
  environment.systemPackages = [ sensorsTool penTool ];

  # n1x.nix ignores the lid (the benchmark image must not sleep mid-run); a laptop desktop should
  # suspend on lid close, on battery and on AC.
  # logind ignores the lid for HoldoffTimeoutSec after boot and after each resume (default 30 s),
  # so a lid closed soon after waking did nothing (2026-11-10 boot 263fd165: closed 7 s after).
  services.logind.settings.Login = {
    HandleLidSwitch = lib.mkForce "suspend";
    HandleLidSwitchExternalPower = lib.mkForce "suspend";
    HoldoffTimeoutSec = "5s";
  };
}
