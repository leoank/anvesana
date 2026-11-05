# ADR-0013: Measure LLM inference with one pinned llama.cpp build, the same binary in WSL and on native Linux

Status: accepted
Date: 2026-11-04

## Context
Checking the report that RTX Spark inference on Linux runs at a third of its Windows speed
(docs/rtx-spark-replication.md) needs an inference benchmark on three platforms: Windows,
WSL2 and native Linux. The article used LM Studio and vLLM without versions or flags.

Alternatives considered (the author chose the pinned llama.cpp build):
- **LM Studio with its `lms` CLI.** Matches the article, but the engine version and flags
  are LM Studio's, and it is a desktop application to script.
- **vLLM everywhere.** No Windows build; it stays for the 8-client test only, in WSL and Linux.
- **Build llama.cpp from source per OS.** Possible, but a native-Linux vs WSL difference
  could then come from the compiler or CUDA version.

## Decision
`bench llm` runs `llama-bench` from llama.cpp `b12119` (commit `6f1e654`), using the official
CUDA 13.4 ARM64 release builds: the Windows build on Windows, and the Ubuntu build both in WSL
and on NixOS (through nix-ld).

Models are GPT-OSS 20B and 120B MXFP4 GGUFs pinned by Hugging Face revision, size and sha256.
Prefill (pp512) and decode (tg128) are separate calls, each with its own GPU power, clock and
throttle-bit sampling. The pins live in `src/anvesana/suite/llm.py`, and
`scripts/llm-fetch.py` reads them from there.

## Consequences
- WSL and native Linux run byte-identical binaries, so a gap between them is the platform.
- The engine is a prebuilt binary, so the benchmark has no build step. Changing the pin is a
  methodology change and bumps `VERSION`.
- The article's LM Studio numbers are compared by ratio, not absolute value.
