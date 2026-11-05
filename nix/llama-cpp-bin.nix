# The same prebuilt llama.cpp the WSL runs use (Ubuntu ARM64, CUDA 13.4), so
# the native-Linux and WSL numbers come from identical binaries. It runs on
# NixOS through nix-ld; libcuda comes from the NVIDIA driver in
# /run/opengl-driver/lib. Pins match src/anvesana/suite/llm.py.
{ lib, stdenvNoCC, fetchurl, makeWrapper }:

let
  build = "b12119";
  base = "https://github.com/ggml-org/llama.cpp/releases/download/${build}";
in
stdenvNoCC.mkDerivation {
  pname = "llama-cpp-bin";
  version = build;
  srcs = [
    (fetchurl {
      url = "${base}/llama-${build}-bin-ubuntu-cuda-13.4-arm64.tar.gz";
      sha256 = "1d31d13d8ac781385e7d5738a645c73a2ef5a375f8ac07e0ed4cd098f4ac97dd";
    })
    (fetchurl {
      url = "${base}/cudart-llama-${build}-bin-ubuntu-cuda-13.4-arm64.tar.gz";
      sha256 = "9b8410a2bc5f10e1c8e27906fa6438bcb9b63b081f95075aed191d78342dbc2c";
    })
  ];
  nativeBuildInputs = [ makeWrapper ];
  dontConfigure = true;
  dontBuild = true;
  dontPatchELF = true;
  dontStrip = true;
  unpackPhase = ''
    mkdir -p unpacked
    for s in $srcs; do tar -xzf "$s" -C unpacked; done
  '';
  installPhase = ''
    mkdir -p $out/lib/llama.cpp $out/bin
    cp -a unpacked/. $out/lib/llama.cpp/
    libdirs=$(find $out/lib/llama.cpp -name '*.so*' -printf '%h\n' | sort -u | tr '\n' ':')
    for tool in llama-bench llama-server llama-cli; do
      exe=$(find $out/lib/llama.cpp -name "$tool" -type f | head -1)
      [ -n "$exe" ] || { echo "$tool not found in the release archive"; exit 1; }
      chmod +x "$exe"
      makeWrapper "$exe" "$out/bin/$tool" \
        --prefix LD_LIBRARY_PATH : "$libdirs/run/opengl-driver/lib"
    done
  '';
  meta = {
    description = "llama.cpp ${build} official Ubuntu ARM64 CUDA 13.4 build";
    platforms = [ "aarch64-linux" ];
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
  };
}
