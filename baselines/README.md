# Baselines

`<machine>/<os>.json` is a promoted `run.json`: the reference `bench health` compares every new
run of that machine against. It's committed so the expected performance of each node is reviewed
and versioned with the benchmark code that produced it.

- Promote only a complete, full-length run taken in known-good conditions: AC power, the profile's
  usual power plan, an otherwise idle machine.
  ```
  bench baseline promote bbaum-pc-7@latest
  ```
- Re-baseline in the same commit as any change that bumps a benchmark's `VERSION`, changes a
  profile's benchmark args, or moves the machine to a new OS, driver or CUDA major version.
- Raw monthly runs (`run.json`, `telemetry.csv`, `run.log`) stay in the results store
  (`$ANVESANA_RESULTS_DIR`), not here.
