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
#               (without the ProArt tuple's vblank=1: on bbaum-pc-7 it stalls every page flip)
#   audio       NVIDIA's MT8901 SoundWire UCM profiles (alsa-ucm-conf PR 862, not yet released);
#               bbaum-pc-7 is 2x RT1320 + RT712, which they cover
#   CPU         CPPC autonomous frequency selection, as Windows does
#   initrd      NVMe, the MediaTek xHCI and the I2C/USB input drivers
#   sleep       lid / suspend keys ignored: suspend is not qualified on N1X Linux
{ config, lib, pkgs, ... }:

let
  cfg = config.n1x;
  # kernelPatches = [ ]: callPackage would otherwise fill it with pkgs.kernelPatches (a set).
  kernel = pkgs.callPackage ./kernel.nix { kernelPatches = [ ]; };
  # Linux 7.0 maps __FILE__ only under $(srcroot), which for an out-of-tree module is the
  # module's own tree: the NVIDIA .ko files keep kernel-header paths into kernel.dev (in
  # WARN strings), which nixpkgs' disallowedReferences rejects. Blank those store hashes.
  withCleanOpen = drv: drv.overrideAttrs (old: {
    passthru = old.passthru // {
      open = old.passthru.open.overrideAttrs (o: {
        nativeBuildInputs = (o.nativeBuildInputs or [ ]) ++ [ pkgs.removeReferencesTo ];
        postFixup = (o.postFixup or "") + ''
          find $out/lib/modules -name '*.ko' -exec \
            remove-references-to -t ${config.boot.kernelPackages.kernel.dev} {} +
        '';
      });
    };
  });
  # alsa-lib finds no profile for the `mt8901-soundwir` card in alsa-ucm-conf 1.2.15.3, so
  # PipeWire only offers a dummy output and the kernel logs "no backend DAIs enabled for DL0_FE"
  # (bbaum-pc-7, 2026-11-07). NVIDIA's profiles from alsa-ucm-conf PR 862 (open, head 7d3555a)
  # pick a file by SoundWire topology; bbaum-pc-7 enumerates 2x RT1320 (uid 0, 1) on link 0 and
  # an RT712 on link 1, i.e. HiFi-rt1320x2-rt712.conf. Added beside the released set and
  # selected with ALSA_CONFIG_UCM2, so nothing that links alsa-lib is rebuilt.
  mt8901Ucm = pkgs.fetchFromGitHub {
    owner = "dcemin-nv";
    repo = "alsa-ucm-conf";
    rev = "7d3555a754936ce073ce5fe3d623294d81dd5c66";
    hash = "sha256-nW4hIa/0cogeuxf3nrhRUugpQQvmW3LFq8UBff351II=";
  };
  ucm2 = pkgs.runCommand "alsa-ucm-conf-n1x" { } ''
    mkdir -p $out/share/alsa
    cp -r --no-preserve=mode ${pkgs.alsa-ucm-conf}/share/alsa/ucm2 $out/share/alsa/ucm2
    cp -r --no-preserve=mode ${mt8901Ucm}/ucm2/MediaTek/mt8901-soundwir $out/share/alsa/ucm2/MediaTek/
    mkdir -p $out/share/alsa/ucm2/conf.d/mt8901-soundwir
    ln -s ../../MediaTek/mt8901-soundwir/mt8901-soundwir.conf \
      $out/share/alsa/ucm2/conf.d/mt8901-soundwir/mt8901-soundwir.conf
  '';
  # The Speakers (DSP) client's whole config (see the audio section): the modules a filter-chain
  # client needs, as in pipewire's own filter-chain.conf, then the graph.
  speakerDspConf = pkgs.writeText "n1x-speaker-dsp.conf" (builtins.toJSON {
    "context.properties" = { "log.level" = 3; };
    "context.spa-libs" = {
      "audio.convert.*" = "audioconvert/libspa-audioconvert";
      "support.*" = "support/libspa-support";
    };
    "context.modules" = [
      { name = "libpipewire-module-rt"; args = { }; flags = [ "ifexists" "nofail" ]; }
      { name = "libpipewire-module-protocol-native"; }
      { name = "libpipewire-module-client-node"; }
      { name = "libpipewire-module-adapter"; }
      { name = "libpipewire-module-filter-chain"; args = {
          "node.description" = "Speakers (DSP)";
          "media.name" = "Speakers (DSP)";
          "filter.graph" = {
            nodes = [
              { type = "lv2"; plugin = "https://chadmed.au/bankstown"; name = "bassex";
                control = { bypass = 0; amt = 1.2; sat_second = 1.3; sat_third = 1.5; blend = 1.0;
                            ceil = 200.0; floor = 20.0; final_hp = 120.0; }; }
              { type = "lv2"; plugin = "http://lsp-plug.in/plugins/lv2/loud_comp_mono"; name = "ell";
                control = { enabled = 1; input = 1.0; fft = 2; }; }
              { type = "lv2"; plugin = "http://lsp-plug.in/plugins/lv2/loud_comp_mono"; name = "elr";
                control = { enabled = 1; input = 1.0; fft = 2; }; }
              { type = "lv2"; plugin = "http://lsp-plug.in/plugins/lv2/compressor_stereo"; name = "lim";
                control = { sla = 5.0; al = 1.0; at = 1.0; rt = 100.0; cr = 15.0; kn = 0.5; }; }
            ];
            links = [
              { output = "bassex:out_l"; input = "ell:in"; }
              { output = "bassex:out_r"; input = "elr:in"; }
              { output = "ell:out"; input = "lim:in_l"; }
              { output = "elr:out"; input = "lim:in_r"; }
            ];
            inputs = [ "bassex:in_l" "bassex:in_r" ];
            outputs = [ "lim:out_l" "lim:out_r" ];
            "capture.volumes" = [
              { control = "ell:volume"; min = -47.5; max = 0.0; scale = "cubic"; }
              { control = "elr:volume"; min = -47.5; max = 0.0; scale = "cubic"; }
            ];
          };
          "capture.props" = {
            "node.name" = "audio_effect.n1x-speakers";
            "media.class" = "Audio/Sink";
            "audio.channels" = 2;
            "audio.position" = [ "FL" "FR" ];
            "priority.session" = 500;          # below the ALSA sinks: opt-in, not the default
            "state.default-volume" = 0.343;
            "device.icon-name" = "audio-speakers";
          };
          "playback.props" = {
            "node.name" = "effect_output.n1x-speakers";
            "target.object" = "alsa_output.platform-mtk_sdw_mc.HiFi__Speaker__sink";
            "node.dont-fallback" = true;
            "node.passive" = true;
            "audio.channels" = 2;
            "audio.position" = [ "FL" "FR" ];
          };
        }; }
    ];
  });
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
    nvidiaVblank = lib.mkOption {
      type = lib.types.bool;
      # Off: on bbaum-pc-7 GNOME on nvidia-drm lagged by minutes with vblank=1 and ran
      # smoothly without it (A/B boots 2026-11-07, only /sys/module/nvidia_drm/parameters/vblank
      # differed). The ASUS ProArt's qualified tuple sets it. Retested under mutter 50.5
      # (2026-11-09, boot ac218860): still does not work.
      default = false;
      description = "Pass the ProArt tuple's `nvidia_drm vblank=1` (only with nvidiaDisplay).";
    };
    speakerDsp = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Add a "Speakers (DSP)" output in the style of Asahi Linux's asahi-audio: Bankstown bass
        enhancement, LSP loudness compensation and a limiter in a PipeWire filter-chain before the
        speaker sink. No speaker-specific EQ (that needs measurements of these speakers); tuned
        conservatively by ear. Low priority, so the plain speaker output stays the default.
      '';
    };
    lps0 = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Load n1x-lps0, which calls the firmware's Microsoft LPS0 _DSM around suspend-to-idle as
        Windows does (Linux does it only on x86). On bbaum-pc-7 function 7/8 set and clear bit 1
        of EC byte 0xEC: the EC's "in standby" state (keyboard backlight off). An EC write by
        firmware, so opt-in (ADR-0008; the author agreed to try it on 2026-11-09).
      '';
    };
    alsaUcm2 = lib.mkOption {
      type = lib.types.str;
      readOnly = true;
      default = "${ucm2}/share/alsa/ucm2";
      description = "ALSA UCM2 directory with the MT8901 SoundWire profiles (for ALSA_CONFIG_UCM2).";
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
    # HID over SPI (not in Linux 7.0): the sensor hub (accelerometer, ambient light) is MSFW1111 /
    # PNP0C51 on SPI3. spi-hid-acpi matches it by ACPI ID; loaded explicitly as well, since it is
    # new on this platform and its absence should show in the logs. See nix/spi-hid/README.md.
    boot.extraModulePackages = [
      (config.boot.kernelPackages.callPackage ./spi-hid.nix { })
      (config.boot.kernelPackages.callPackage ./n1x-lps0.nix { })   # loaded only with n1x.lps0
    ];
    boot.kernelModules = [ "spi-hid-acpi" ] ++ lib.optional cfg.lps0 "n1x-lps0";
    # Suspend: the firmware offers "deep" (PSCI system suspend) and Linux picks it by default, but
    # Windows on this machine only uses Modern Standby (s2idle-like), so deep is the untested path.
    # The first suspend on Linux, in deep, never resumed (2026-11-09).
    boot.kernelParams = [ "mem_sleep_default=s2idle" ];

    # ---------------------------------------------------------------- NVIDIA
    services.xserver.videoDrivers = [ "nvidia" ];   # selects hardware.nvidia; enables no X server by itself
    hardware.graphics.enable = true;
    hardware.nvidia = {
      open = true;
      modesetting.enable = cfg.nvidiaDisplay;       # nvidia_drm modeset=1 fbdev=1
      nvidiaSettings = false;
      powerManagement.enable = false;
      package = withCleanOpen (config.boot.kernelPackages.nvidiaPackages.mkDriver {
        version = "615.78.08";
        sha256_aarch64 = "5076011350181e81a031f0fd012fe35fe4be37c7820d651fb7aaa894af447a37";
        # mkDriver requires the x86_64 hash too; it is only fetched on x86_64.
        sha256_64bit = lib.fakeHash;
        # NAR hash of NVIDIA/open-gpu-kernel-modules at tag 615.78.08 (printed by
        # the first build in WSL, 2026-11-06).
        openSha256 = "sha256-HBINiOjL0ZJLIAJeNIBYHBnwgUXtNwPPtnFpAI1YwF4=";
        patchesOpen = [
          ./patches/nvidia-open-drm-aarch64-mappings.patch
          ./patches/nvidia-open-pr1368-semsurf-leak.patch
        ];
        useSettings = false;
        usePersistenced = false;
      });
    };
    # The ProArt's qualified tuple also sets vblank=1 (h7607a-nvidia.conf); off by default here.
    boot.extraModprobeConfig = lib.mkIf (cfg.nvidiaDisplay && cfg.nvidiaVblank) "options nvidia_drm vblank=1";

    # VA-API on NVDEC (Firefox found no hardware decoder, 2026-11-07). NVD_BACKEND=direct is the
    # driver's backend for current NVIDIA drivers (its README).
    hardware.graphics.extraPackages = [ pkgs.nvidia-vaapi-driver ];
    environment.sessionVariables = lib.mkMerge [
      (lib.mkIf cfg.nvidiaDisplay { LIBVA_DRIVER_NAME = "nvidia"; NVD_BACKEND = "direct"; })
      { ALSA_CONFIG_UCM2 = cfg.alsaUcm2; }       # audio, below
    ];

    # ---------------------------------------------------------------- audio
    # Optional speaker DSP (n1x.speakerDsp), modelled on asahi-audio's graphs (firs/*/graph.json,
    # github.com/AsahiLinux/asahi-audio): bassex -> per-channel loudness (carries the volume) ->
    # limiter (asahi's woofer_lim settings). Bankstown's final_hp keeps sub-120 Hz content off
    # the microspeakers. The RT1320s run on their ROM defaults on Linux (MSI's tuning is in an
    # obfuscated Realtek container on Windows), so the limiter is a software safety net.
    #
    # It runs as its own PipeWire client (n1x-speaker-dsp.service, like pipewire's filter-chain
    # service) with a config given by path, not as a drop-in of the main daemon: on the laptop the
    # daemon never loaded the drop-in and logged nothing (2026-11-08/09), although the same file
    # loads in a test daemon. Its own unit also puts any error in its own journal.
    systemd.user.services.n1x-speaker-dsp = lib.mkIf cfg.speakerDsp {
      description = "Speakers (DSP) filter-chain for the N1X laptop speakers";
      wantedBy = [ "pipewire.service" ];
      after = [ "pipewire.service" ];
      bindsTo = [ "pipewire.service" ];
      environment = {
        LV2_PATH = lib.makeSearchPath "lib/lv2" [ pkgs.bankstown-lv2 pkgs.lsp-plugins ];
        PIPEWIRE_DEBUG = "3";                    # info: plugin loading shows in the journal
      };
      serviceConfig = {
        # The filter's output has a fixed target and no fallback, and the filter-chain module
        # unloads itself ("defined target not found") if the speaker sink is not there yet:
        # it started 3 s before WirePlumber made the sink (2026-11-10, boot 263fd165). So wait
        # for the sink first; failing after 60 s lets Restart try again.
        ExecStartPre = pkgs.writeShellScript "n1x-wait-speaker-sink" ''
          for _ in $(${pkgs.coreutils}/bin/seq 60); do
            ${config.services.pipewire.package}/bin/pw-cli ls Node 2>/dev/null \
              | ${pkgs.gnugrep}/bin/grep -q 'node.name = "alsa_output.platform-mtk_sdw_mc.HiFi__Speaker__sink"' && exit 0
            ${pkgs.coreutils}/bin/sleep 1
          done
          echo "speaker sink did not appear in 60 s"; exit 1
        '';
        # The filter plays into the speaker sink, so that sink's own volume applied on top: with
        # it at 64 % the DSP output at full volume was about -12 dB, "half as loud" (2026-11-10,
        # boot 43467edb). While Speakers (DSP) is the default output the speaker sink is held at
        # 100 % (the DSP volume is then the only one) and its old volume is put back as soon as
        # another output is chosen; the events come from `pactl subscribe`, so there is no
        # moment at 100 % on the plain sink. A resume that re-creates the speaker sink unloads
        # the filter ("defined target not found", same boot, after a SoundWire bus clash) while
        # pipewire keeps running: exit then, so Restart brings it back after ExecStartPre.
        ExecStart = pkgs.writeShellScript "n1x-speaker-dsp" ''
          pw=${config.services.pipewire.package}/bin pactl=${pkgs.pulseaudio}/bin/pactl
          spk=alsa_output.platform-mtk_sdw_mc.HiFi__Speaker__sink dsp=audio_effect.n1x-speakers
          $pw/pipewire -c ${speakerDspConf} & pid=$!
          seen= saved=
          restore() {
            [ -n "$saved" ] || return 0
            $pactl set-sink-volume $spk "$saved" && echo "speaker sink back to $saved"; saved=
          }
          trap 'restore; kill $pid 2>/dev/null; wait $pid; exit 0' TERM INT
          check() {
            kill -0 $pid 2>/dev/null || { restore; echo "pipewire exited"; exit 1; }
            if $pw/pw-cli ls Node 2>/dev/null | ${pkgs.gnugrep}/bin/grep -q "node.name = \"$dsp\""; then
              seen=1
            elif [ -n "$seen" ]; then
              restore; echo "filter node gone (speaker sink re-created?); restarting"
              kill $pid; wait $pid; exit 1
            else
              return 0
            fi
            if [ "$($pactl get-default-sink 2>/dev/null)" = "$dsp" ]; then
              v=$($pactl get-sink-volume $spk 2>/dev/null | ${pkgs.gnugrep}/bin/grep -oE '[0-9]+%' | head -1)
              if [ -n "$v" ] && [ "$v" != 100% ]; then
                [ -n "$saved" ] || saved=$v
                $pactl set-sink-volume $spk 100% && echo "Speakers (DSP) is the default: speaker sink $v -> 100%"
              fi
            else
              restore
            fi
          }
          sleep 2; check
          # Process substitution, not a pipe: the loop stays in this shell, so the TERM trap
          # (logout, shutdown) still puts the speaker volume back.
          while read -r ev; do
            case $ev in *server*|*"on sink #"*) check ;; esac
          done < <($pactl subscribe 2>/dev/null)
          restore; echo "pactl subscribe ended"; kill $pid 2>/dev/null; wait $pid; exit 1
        '';
        Restart = "on-failure";
        RestartSec = 5;
      };
    };

    # (ALSA_CONFIG_UCM2 is in environment.sessionVariables above)
    systemd.user.services.pipewire.environment.ALSA_CONFIG_UCM2 = cfg.alsaUcm2;
    systemd.user.services.wireplumber.environment.ALSA_CONFIG_UCM2 = cfg.alsaUcm2;

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
