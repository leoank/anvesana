"""Per-operation cost of cpu_ram's math loop on one core, and the core's delivered clock."""
import os, sys, time, threading, numpy as np
core = int(sys.argv[1]); os.sched_setaffinity(0, {core})
N = int(sys.argv[2]) if len(sys.argv) > 2 else 8192
a = np.full(N, 1.000001); b = np.full(N, 0.999999); t = np.empty(N)
freqs = []
def sample():
    while not done:
        freqs.append(int(open(f"/sys/devices/system/cpu/cpu{core}/cpufreq/scaling_cur_freq").read()) / 1000)
        time.sleep(0.2)
done = False; th = threading.Thread(target=sample); th.start()
ops = {"multiply": lambda: np.multiply(a, b, out=t), "add": lambda: np.add(a, 1.5, out=t),
       "sqrt": lambda: np.sqrt(a, out=t), "sin": lambda: np.sin(a, out=t), "cos": lambda: np.cos(b, out=t)}
for name, f in ops.items():
    for _ in range(200): f()
    n, t0 = 0, time.perf_counter()
    while time.perf_counter() - t0 < 2: f(); n += 1
    print(f"core {core} {name:9} {(time.perf_counter() - t0) / n / N * 1e9:6.3f} ns/elem")
done = True; th.join()
print(f"core {core} clock {min(freqs):.0f}-{max(freqs):.0f} MHz (median {sorted(freqs)[len(freqs)//2]:.0f}); numpy {np.__version__}")
np.show_config() if len(sys.argv) > 3 else None
