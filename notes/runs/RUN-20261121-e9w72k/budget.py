#!/usr/bin/env python3
# Read-only sampler of the N1X SoC power-budget page at physical 0x1C238000, as found by HP
# OmniBook owners in their DSDT (NVIDIA/open-gpu-kernel-modules#1521): _PL1 +0x160, _PL2 +0x164,
# SPL1-4 +0x170..+0x17C (mW), EPL1 +0x800 (SoC power, ~8 s average, mW), ESP1 +0x80C (slower
# average), PTJK +0x818 and PGPU +0x830 (SoC and GPU temperature, deci-K), and +0x604
# (SPBM_BUDGET_GPU_INST per the ASUS report). Needs root (/dev/mem).
# Usage: budget.py SECONDS OUTFILE   (prints the first sample, then one line every 2 s)
import mmap, os, struct, sys, time
BASE = 0x1C238000
F = [("PL1", 0x160), ("PL2", 0x164), ("SPL1", 0x170), ("SPL2", 0x174), ("SPL3", 0x178),
     ("SPL4", 0x17C), ("GPUBUD", 0x604), ("EPL1", 0x800), ("ESP1", 0x80C), ("PTJK", 0x818),
     ("PGPU", 0x830)]
secs, out = float(sys.argv[1]), sys.argv[2]
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=BASE)
def row():
    return [struct.unpack_from("<I", m, o)[0] for _, o in F]
with open(out, "w") as f:
    f.write("time\t" + "\t".join(n for n, _ in F) + "\n")
    t0 = time.time(); first = True
    while time.time() - t0 < secs:
        r = row()
        line = time.strftime("%H:%M:%S") + "\t" + "\t".join(str(v) for v in r)
        f.write(line + "\n"); f.flush()
        if first:
            print("first sample:", dict(zip([n for n, _ in F], r)), flush=True); first = False
        time.sleep(2)
