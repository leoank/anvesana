import os, sys, time, numpy as np
n = 4096; rng = np.random.default_rng(0); a, b = rng.random((n, n)), rng.random((n, n)); c = a @ b
t0, it = time.perf_counter(), 0
while time.perf_counter() - t0 < 8: np.matmul(a, b, out=c); it += 1
print(f"{os.environ.get('OPENBLAS_NUM_THREADS','all'):>4} threads on {sys.argv[1]:>14}: {2*n**3*it/(time.perf_counter()-t0)/1e9:6.1f} GFLOPS")
