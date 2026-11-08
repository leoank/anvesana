# HID over SPI transport (spi-hid v4, not yet in mainline) as an out-of-tree module for the
# N1X kernel: the sensor hub of bbaum-pc-7 sits behind it. See nix/spi-hid/README.md.
{ lib, stdenv, kernel }:

stdenv.mkDerivation {
  pname = "spi-hid";
  version = "v4-20260609-${kernel.version}";
  src = ./spi-hid;

  nativeBuildInputs = kernel.moduleBuildDependencies;
  # commonMakeFlags: toolchain and ARCH only (makeFlags carries O= and targets for the kernel build)
  makeFlags = kernel.commonMakeFlags ++ [
    "-C" "${kernel.dev}/lib/modules/${kernel.modDirVersion}/build"
    "M=$(PWD)"
    "CONFIG_SPI_HID_CORE=m"
    "CONFIG_SPI_HID_ACPI=m"
  ];
  buildFlags = [ "modules" ];
  installPhase = ''
    runHook preInstall
    install -Dm444 -t $out/lib/modules/${kernel.modDirVersion}/extra spi-hid.ko spi-hid-acpi.ko
    runHook postInstall
  '';

  meta = {
    description = "HID over SPI transport driver (spi-hid v4 series)";
    license = lib.licenses.gpl2Only;
    platforms = lib.platforms.linux;
  };
}
