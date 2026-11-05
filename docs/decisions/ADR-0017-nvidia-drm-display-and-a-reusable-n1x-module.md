# ADR-0017: Drive the display with patched nvidia-drm, and keep N1X hardware support in a reusable NixOS module

Status: accepted
Date: 2026-11-05
Amends: ADR-0014 (its NVIDIA display choice)

## Context
ADR-0014 kept the live image's console on simpledrm, which avoided the two NVIDIA patches the
ProArt P16 needed for a working nvidia-drm console and Wayland desktop. The author now
intends NixOS as the daily driver on bbaum-pc-7, so the display must run on nvidia-drm.

The patches are small and apply to NVIDIA's open-module source, which nixpkgs builds with
`mkDriver { patchesOpen = [ … ]; }`:
- **`drm.patch`** (ProArt build): on aarch64, maps RAM-backed GEM buffers as Normal-NC and
  PRIME buffers write-combined.
- **PR #1368** (NVIDIA/open-gpu-kernel-modules): frees a semaphore-surface callback record that
  otherwise leaks once per Wayland frame.

Alternatives considered:
- **Stay on simpledrm in the live image and solve the display later.** The benchmark entries
  would then differ from the eventual desktop in how the GPU drives the panel.
- **Keep all hardware settings in `live.nix`.** An installed system would then copy them, and
  the two would drift.

## Decision
- **Display:** `nix/n1x.nix` enables `hardware.nvidia.modesetting` (nvidia_drm modeset=1
  fbdev=1, plus the ProArt's vblank=1) and applies both patches.
- **Shared module:** `nix/n1x.nix` holds the kernel, NVIDIA, CPU init, initrd and sleep policy.
  The flake exports it as `nixosModules.n1x`, and the live image imports it.
- **Fallback:** a `simpledrm` boot entry (`n1x.nvidiaDisplay = false`) keeps the firmware
  framebuffer in case nvidia-drm shows nothing on the MSI panel.

## Consequences
- The benchmark boot entries run the same display stack an installed desktop will.
- An installed NixOS imports one module instead of copying settings.
- The patches are untested on the MSI panel, which is why the `simpledrm` entry exists.
- Daily-driver support needs more than this module: audio, keyboard backlight, Wi-Fi and suspend
  are separate work, and the ProArt's audio and keyboard parts are ASUS-specific.
