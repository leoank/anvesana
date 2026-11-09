# n1x-lps0: the Microsoft LPS0 _DSM calls around suspend-to-idle that Linux makes only on x86
# (on bbaum-pc-7 they tell the EC the laptop is in standby). See nix/n1x-lps0/n1x-lps0.c.
{ lib, stdenv, kernel }:

stdenv.mkDerivation {
  pname = "n1x-lps0";
  version = "0.1-${kernel.version}";
  src = ./n1x-lps0;

  nativeBuildInputs = kernel.moduleBuildDependencies;
  makeFlags = kernel.commonMakeFlags ++ [
    "-C" "${kernel.dev}/lib/modules/${kernel.modDirVersion}/build"
    "M=$(PWD)"
  ];
  buildFlags = [ "modules" ];
  installPhase = ''
    runHook preInstall
    install -Dm444 -t $out/lib/modules/${kernel.modDirVersion}/extra n1x-lps0.ko
    runHook postInstall
  '';

  meta = {
    description = "Microsoft LPS0 _DSM calls around suspend-to-idle on NVIDIA N1X laptops";
    license = lib.licenses.gpl2Only;
    platforms = lib.platforms.linux;
  };
}
