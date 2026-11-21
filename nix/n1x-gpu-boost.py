"""n1x-gpu-boost: give the GPU the CPU's share of the N1X's shared power budget while it is busy.

The N1X's GPU and CPU share one SoC power limit (PL1 80 W on curiosity, constant under load).
Under a pure GPU load the SoC runs on that limit and the GPU gets what the CPU leaves: with the
CPUs' energy/performance preference (EPP) at the balanced profile's 127 the CPU side took about
27 W and the GPU about 50 W; at 255 the CPU side took about 20 W and the GPU about 58 W, 3-5 %
faster (RUN-20261121-e9w72k). NVIDIA's Dynamic Boost (nvidia-powerd) shifts power this way on
Windows but creates no worker on Linux here (RUN-20261120-g7hznd).

So while the GPU is busy (NVML utilization at or above BUSY_PCT for BUSY_FOR seconds), this sets
every CPU policy's EPP to 255, and when it has been below IDLE_PCT for IDLE_FOR seconds it puts
back the active TuneD profile's value. The profile-to-EPP table is the TuneD profiles' own,
passed as JSON in argv[1]. Nothing is boosted under a profile whose value is 0 (performance: the
user asked for CPU speed) or 255 (power-saver). A profile switch while boosted is followed:
TuneD writes the new value, and this writes 255 over it again unless the new value is 0. Every
change is logged.
"""
import ctypes
import glob
import json
import signal
import sys
import time

BUSY_PCT, BUSY_FOR = 60, 3     # percent, seconds
IDLE_PCT, IDLE_FOR = 30, 10
BOOST_EPP = 255
POLICIES = "/sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference_val"
NVML = "/run/opengl-driver/lib/libnvidia-ml.so.1"
ACTIVE = "/etc/tuned/active_profile"


def log(msg):
    print(msg, flush=True)


class Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


def nvml_gpu():
    lib = ctypes.CDLL(NVML)
    if lib.nvmlInit_v2() != 0:
        raise OSError("nvmlInit failed")
    handle = ctypes.c_void_p()
    if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
        raise OSError("no GPU 0")
    util = Utilization()

    def busy_pct():
        if lib.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(util)) != 0:
            return None
        return util.gpu
    return busy_pct


def profile_epp(table):
    """The active TuneD profile's EPP, or None for a profile not in the table."""
    try:
        with open(ACTIVE) as f:
            return table.get(f.read().strip())
    except OSError:
        return None


def read_epp():
    out = set()
    for p in glob.glob(POLICIES):
        with open(p) as f:
            out.add(int(f.read()))
    return out


def write_epp(value):
    for p in glob.glob(POLICIES):
        with open(p, "w") as f:
            f.write(str(value))


def main():
    table = json.loads(sys.argv[1])
    for _ in range(30):              # the driver can come up after this service starts
        try:
            busy_pct = nvml_gpu()
            break
        except OSError:
            time.sleep(2)
    else:
        sys.exit("NVML not available")
    log(f"boost to EPP {BOOST_EPP} at GPU >= {BUSY_PCT} % for {BUSY_FOR} s, "
        f"back below {IDLE_PCT} % for {IDLE_FOR} s; profiles {table}")

    boosted = False
    busy_since = idle_since = None

    def stop(*_):
        epp = profile_epp(table)
        if boosted and epp is not None:
            write_epp(epp)
            log(f"stopped; EPP back to {epp}")
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while True:
        now, pct, epp = time.monotonic(), busy_pct(), profile_epp(table)
        boostable = epp is not None and 0 < epp < BOOST_EPP
        if pct is None:
            pass
        elif not boosted:
            if pct >= BUSY_PCT and boostable:
                busy_since = busy_since or now
                if now - busy_since >= BUSY_FOR:
                    write_epp(BOOST_EPP)
                    boosted, busy_since = True, None
                    log(f"GPU busy ({pct} %): EPP {epp} -> {BOOST_EPP}")
            else:
                busy_since = None
        elif not boostable:          # switched to performance or power-saver while boosted
            boosted, idle_since = False, None
            log(f"profile now at EPP {epp}; boost ended")
        else:
            if read_epp() != {BOOST_EPP}:   # TuneD wrote a new profile's value
                write_epp(BOOST_EPP)
                log(f"profile changed while boosted; EPP {epp} -> {BOOST_EPP}")
            if pct < IDLE_PCT:
                idle_since = idle_since or now
                if now - idle_since >= IDLE_FOR:
                    write_epp(epp)
                    boosted, idle_since = False, None
                    log(f"GPU idle ({pct} %): EPP back to {epp}")
            else:
                idle_since = None
        time.sleep(1)


if __name__ == "__main__":
    main()
