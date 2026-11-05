# ADR-0014: Run native-Linux tests from a NixOS live USB with NVIDIA's N1X kernel and driver 615.78.08

Status: accepted; display choice amended by ADR-0017
Date: 2026-11-04

## Context
bbaum-pc-7 has never booted Linux, and its internal disk holds a BitLocker-encrypted Windows.
The native-Linux tests need a reproducible kernel, driver and toolset.

The ASUS ProArt P16 uses the same N1X SoC and runs Arch Linux ARM
(github.com/pfeifferj/archlinuxarm-proart-p16) with:
- Ubuntu's `linux-nvidia-7.0` 7.0.0-1022 kernel (NV-Kernels, Linux 7.0.14);
- NVIDIA 615.78.08 with the open kernel modules;
- a patch for the kernel's ACPI-override memory allocation.

Alternatives considered (the author chose the live USB, NixOS, NV-Kernels and 615.78.08):
- **Installed to an external SSD, or dual boot.** More state to keep, and dual boot touches
  the BitLocker disk.
- **Ubuntu, DGX OS or Omarchy.** Ubuntu and DGX OS are less declarative; Omarchy is a rolling
  release and hard to pin.
- **nixpkgs' mainline kernel or the newest driver.** That would mix N1X support gaps into the
  power result.

## Decision
A NixOS live image (`flake.nix`, `nix/live.nix`), built in WSL on the same laptop, with:
- **Kernel:** Ubuntu's orig tarball, delta and config, plus the ProArt allocation patch
  (`nix/kernel.nix`).
- **NVIDIA:** driver 615.78.08 with the open modules; the console stays on simpledrm.
- **CPU and sleep:** the CPPC-autonomous CPU init and the no-sleep policy from the ProArt build.
- **Data:** models and the results store on a second USB drive labelled `SPARKDATA` (exFAT,
  readable by Windows, WSL and NixOS).

## Consequences
- Nothing is installed on the laptop's NVMe, and results survive the live session.
- The image is a pinned closure, but it is unverified until its first build (the open
  modules' NAR hash is a deliberate fake hash).
- It needs Secure Boot off, which is gated by ADR-0016.
