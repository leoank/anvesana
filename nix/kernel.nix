# NVIDIA's N1X kernel, as Ubuntu ships it: linux-nvidia-7.0 7.0.0-1022.23~24.04.1
# (Linux 7.0.14 + NVIDIA/NV-Kernels), built from Ubuntu's orig tarball and delta
# with Ubuntu's own config, plus one patch so ACPI table overrides from the
# initrd (the SSPM boot entry) stay inside one EFI memory descriptor.
#
# Same sources, hashes and patch as the ASUS ProArt P16 Arch build
# (github.com/pfeifferj/archlinuxarm-proart-p16 @ 3484cc0, MIT;
# 01-platform/kernel/payload/provenance/hardware/backports/acpi/build.sh).
{ lib, fetchurl, linuxManualConfig }:

let
  orig = fetchurl {
    urls = [
      "https://ports.ubuntu.com/ubuntu-ports/pool/main/l/linux-nvidia-7.0/linux-nvidia-7.0_7.0.0.orig.tar.gz"
      "https://launchpad.net/ubuntu/+archive/primary/+files/linux-nvidia-7.0_7.0.0.orig.tar.gz"
    ];
    sha256 = "c6343795c8c7e4feff55f5b309365c8e0eaf49cd6abcb412e32315313f149536";
  };
  ubuntuDelta = fetchurl {
    urls = [
      "https://ports.ubuntu.com/ubuntu-ports/pool/main/l/linux-nvidia-7.0/linux-nvidia-7.0_7.0.0-1022.23~24.04.1.diff.gz"
      "https://launchpad.net/ubuntu/+archive/primary/+files/linux-nvidia-7.0_7.0.0-1022.23~24.04.1.diff.gz"
    ];
    sha256 = "6dbf6661592f7b6053253eea6b5411e21974627d9b76d4d3e105653c243d7718";
  };
in
linuxManualConfig {
  version = "7.0.14-1022-nvidia";
  modDirVersion = "7.0.14";
  src = orig;
  # Ubuntu's config for 7.0.0-1022-nvidia (/boot/config-7.0.0-1022-nvidia from
  # linux-modules-7.0.0-1022-nvidia_7.0.0-1022.23~24.04.1_arm64.deb).
  configfile = ./kernel/config-7.0.0-1022-nvidia;
  allowImportFromDerivation = true;
  kernelPatches = [
    # The delta also adds debian/canonical-certs.pem, which the config names
    # as CONFIG_SYSTEM_TRUSTED_KEYS.
    { name = "ubuntu-linux-nvidia-7.0-1022.23"; patch = ubuntuDelta; }
    { name = "arm64-bound-acpi-override-allocation"; patch = ./patches/0001-arm64-bound-acpi-override-allocation.patch; }
  ];
}
