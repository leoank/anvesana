#!/usr/bin/env bash
# Set up the WSL2 Ubuntu 24.04 instance on bbaum-pc-7 for the RTX Spark replication
# (docs/rtx-spark-replication.md). Run inside WSL from the repo checkout:
#
#   bash scripts/wsl-setup.sh            # uv, anvesana, llama.cpp (Ubuntu ARM64 CUDA build)
#   bash scripts/wsl-setup.sh --nix      # + multi-user Nix, to build the NixOS live image
#   bash scripts/wsl-setup.sh --vllm     # + vLLM 0.33.0 in its own venv (~10 GB with torch)
#
# Changes only this WSL instance. Windows' GPU driver provides CUDA inside WSL
# (/usr/lib/wsl/lib/libcuda.so); do not install an NVIDIA driver here.
set -euo pipefail

VLLM_VERSION=0.33.0
NIX_VERSION=2.31.2
want_nix=0; want_vllm=0
for a in "$@"; do
  case "$a" in
    --nix) want_nix=1 ;;
    --vllm) want_vllm=1 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done

repo=$(cd "$(dirname "$0")/.." && pwd)
case "$repo" in
  /mnt/*) echo "Clone the repo inside WSL (e.g. ~/anvesana), not under /mnt: uv and Nix are slow and break on 9p."; exit 1 ;;
esac

[ "$(uname -m)" = aarch64 ] || { echo "expected an aarch64 WSL instance, got $(uname -m)"; exit 1; }
[ -e /usr/lib/wsl/lib/libcuda.so ] || echo "warning: /usr/lib/wsl/lib/libcuda.so missing: is the Windows NVIDIA driver installed?"
systemctl is-system-running >/dev/null 2>&1 || echo "note: systemd not running; the Nix daemon needs [boot] systemd=true in /etc/wsl.conf"

sudo apt-get update -qq
sudo apt-get install -y -qq curl ca-certificates git xz-utils build-essential pciutils python3.12-dev

if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
cd "$repo"
uv sync --extra nvidia
uv run python scripts/llm-fetch.py llama-cpp --os linux
uv run bench check || true

if [ "$want_nix" = 1 ] && ! command -v nix >/dev/null; then
  curl -L "https://releases.nixos.org/nix/nix-${NIX_VERSION}/install" -o /tmp/nix-install
  sh /tmp/nix-install --daemon --yes
  echo "experimental-features = nix-command flakes" | sudo tee -a /etc/nix/nix.conf
  sudo systemctl restart nix-daemon
  echo "Nix installed: open a new shell, then see docs/rtx-spark-replication.md, 'Build the live image'."
fi

if [ "$want_vllm" = 1 ]; then
  venv="$HOME/.cache/anvesana/vllm-$VLLM_VERSION"
  uv venv --python 3.12 "$venv"
  VIRTUAL_ENV="$venv" uv pip install "vllm==$VLLM_VERSION"
  # FlashInfer JIT-compiles its sampling and attention kernels on first use. Its compiler must
  # match torch's CUDA 13.0 runtime headers: the wheels vLLM pulls in are 13.5 (nvcc, crt, nvvm),
  # which fail with "CUDA compiler and CUDA toolkit headers are incompatible" / ptxas errors.
  VIRTUAL_ENV="$venv" uv pip install ninja "nvidia-cuda-nvcc==13.0.*" "nvidia-cuda-crt==13.0.*" "nvidia-nvvm==13.0.*"
  cu="$venv/lib/python3.12/site-packages/nvidia/cu13"
  link="$HOME/.cache/anvesana/cuda-link"   # unversioned names for the JIT's -lcuda -lcudart
  mkdir -p "$link"
  ln -sf /usr/lib/wsl/lib/libcuda.so.1 "$link/libcuda.so"
  ln -sf "$cu/lib/libcudart.so.13" "$link/libcudart.so"
  cat > "$venv/bin/vllm-env" <<ENV
export CUDA_HOME=$cu PATH=$venv/bin:$cu/bin:\$PATH LIBRARY_PATH=$link
ENV
  echo "vLLM in $venv; see docs/rtx-spark-replication.md (step 2) for the serve command."
fi
