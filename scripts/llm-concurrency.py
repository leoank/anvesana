"""Aggregate decode throughput with N concurrent clients against an OpenAI-compatible server.

    uv run python scripts/llm-concurrency.py --url http://127.0.0.1:8000 --model openai/gpt-oss-20b \
        --clients 8 --tokens 256 --label wsl-vllm

Reproduces the article's "vLLM, eight concurrent clients" number (127 tok/s in
WSL vs 39.5 on native Linux). Works the same with vLLM (`vllm serve`) and
llama.cpp (`llama-server -np 8`). Each client sends the same fixed prompt with
temperature 0 and ignore_eos, so every request generates exactly --tokens
tokens; aggregate tok/s = all completion tokens / wall time of the batch. GPU
clock, power and NVML throttle reasons are sampled during the batch (if NVML is
available here) and written with the result to --out (default: the results store).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

PROMPT = ("Write a detailed, factual history of the printing press, from movable type in East Asia "
          "to Gutenberg and the spread of print across Europe.")


def one_request(url: str, model: str, tokens: int) -> dict:
    body = json.dumps({
        "model": model, "prompt": PROMPT, "max_tokens": tokens, "temperature": 0,
        "ignore_eos": True, "stream": False,
    }).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/completions", body, {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=3600) as r:
        data = json.load(r)
    return {"seconds": time.perf_counter() - t0, "completion_tokens": data["usage"]["completion_tokens"]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--model", required=True, help="model name the server expects")
    p.add_argument("--clients", type=int, default=8)
    p.add_argument("--tokens", type=int, default=256)
    p.add_argument("--rounds", type=int, default=3, help="batches; the first is a warm-up and not reported")
    p.add_argument("--label", required=True, help="e.g. wsl-vllm, nixos-default-vllm")
    p.add_argument("--out", type=Path, help="JSON output path")
    args = p.parse_args(argv)

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from anvesana.hw.telemetry import GpuSampler as sampler_cls
    except Exception:
        sampler_cls = None

    rounds = []
    for i in range(args.rounds):
        sampler = sampler_cls(interval_s=0.2) if sampler_cls else None
        if sampler:
            sampler.__enter__()
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(args.clients) as pool:
            results = list(pool.map(lambda _: one_request(args.url, args.model, args.tokens), range(args.clients)))
        wall = time.perf_counter() - t0
        if sampler:
            sampler.__exit__(None, None, None)
        total = sum(r["completion_tokens"] for r in results)
        row = {"round": i, "wall_s": round(wall, 3), "completion_tokens": total, "tok_per_s": round(total / wall, 2),
               "avg_power_w": sampler.avg("power_w") if sampler else None,
               "avg_sm_clock_mhz": sampler.avg("sm_clock_mhz") if sampler else None}
        clock = f", {row['avg_sm_clock_mhz']:.0f} MHz SM" if row["avg_sm_clock_mhz"] else ""
        print(f"round {i}{' (warm-up)' if i == 0 else ''}: {total} tokens in {wall:.1f} s = {total / wall:.1f} tok/s{clock}")
        rounds.append(row)

    measured = rounds[1:] or rounds
    result = {
        "label": args.label, "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "url": args.url, "model": args.model, "clients": args.clients, "tokens": args.tokens,
        "tok_per_s_median": sorted(r["tok_per_s"] for r in measured)[len(measured) // 2], "rounds": rounds,
    }
    out = args.out
    if out is None:
        store = Path(os.environ.get("ANVESANA_RESULTS_DIR", Path.home() / "anvesana-results"))
        out = store / "concurrency" / f"{args.label}_{datetime.datetime.now():%Y-%m-%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"median {result['tok_per_s_median']} tok/s; written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
