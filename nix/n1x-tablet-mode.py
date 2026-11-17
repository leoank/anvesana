"""n1x-tablet-mode: SW_TABLET_MODE from the hinge angle, for GNOME on curiosity (N1X convertible).

Linux has no tablet-mode switch on this machine. The sensor hub's two accelerometers give the
hinge angle (EXP-20261117-sm6c0e, RUN-20261117-sm7bfn): 200073.36 in the lid, 200073.39 in the
base, the hinge along x, and
    hinge = (180 + atan2(lid_y, lid_z) - atan2(base_y, base_z)) mod 360.
Closed (0) and folded back (360) read the same; the lid switch tells them apart.

Only one reader can hold an IIO buffer, and iio-sensor-proxy would hold the lid's whenever GNOME
wants the orientation, which is in tablet mode. So this daemon reads both buffers and creates
two uinput devices:
- "N1X tablet mode switch": SW_TABLET_MODE, on above 200 degrees, off below 160, after the
  angle has stayed there 1 s. libinput then disables the internal keyboard and touchpad and
  mutter enters touch mode (auto-rotate, on-screen keyboard).
- "N1X lid accelerometer": the lid's samples as ABS_X/Y/Z in 1/256 g (the scale
  iio-sensor-proxy's input-accel driver assumes), for auto-rotate. A udev rule hides the hub's
  IIO accelerometers from iio-sensor-proxy, so it uses this one.
Every switch change and lid switch change is logged with the angle.
"""
import fcntl
import glob
import math
import os
import re
import select
import signal
import struct
import sys
import time

LID, BASE = "HID-SENSOR-200073.36", "HID-SENSOR-200073.39"
LID_STATE = "/proc/acpi/button/lid/LID0/state"
ON_ABOVE, OFF_BELOW, HOLD = 200.0, 160.0, 1.0   # degrees, degrees, seconds
G = 9.80665

# uinput (linux/uinput.h, linux/input-event-codes.h)
def _iow(nr, size):
    return (1 << 30) | (size << 16) | (ord("U") << 8) | nr
UI_SET_EVBIT, UI_SET_ABSBIT, UI_SET_SWBIT, UI_SET_PROPBIT = (_iow(n, 4) for n in (100, 103, 109, 110))
UI_DEV_SETUP, UI_ABS_SETUP = _iow(3, 92), _iow(4, 28)
UI_DEV_CREATE, UI_DEV_DESTROY = (ord("U") << 8) | 1, (ord("U") << 8) | 2
EV_SYN, EV_ABS, EV_SW = 0, 3, 5
SW_TABLET_MODE, INPUT_PROP_ACCELEROMETER, BUS_VIRTUAL = 1, 6, 6
EVENT = struct.Struct("llHHi")


def log(msg):
    print(msg, flush=True)


def rd(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def wr(path, value):
    with open(path, "w") as f:
        f.write(str(value))


class Uinput:
    def __init__(self, name, evbits, setup):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for ev in evbits:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        setup(self.fd)
        fcntl.ioctl(self.fd, UI_DEV_SETUP,
                    struct.pack("HHHH80sI", BUS_VIRTUAL, 0, 0, 1, name.encode(), 0))
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def emit(self, *events):
        os.write(self.fd, b"".join(EVENT.pack(0, 0, t, c, v) for t, c, v in events)
                 + EVENT.pack(0, 0, EV_SYN, 0, 0))

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


def switch_device():
    return Uinput("N1X tablet mode switch", [EV_SW],
                  lambda fd: fcntl.ioctl(fd, UI_SET_SWBIT, SW_TABLET_MODE))


def accel_device():
    def setup(fd):
        fcntl.ioctl(fd, UI_SET_PROPBIT, INPUT_PROP_ACCELEROMETER)
        for code in range(3):
            fcntl.ioctl(fd, UI_SET_ABSBIT, code)
            # code, value, min, max, fuzz, flat, resolution (units per g)
            fcntl.ioctl(fd, UI_ABS_SETUP, struct.pack("Hxxiiiiii", code, 0, -2048, 2048, 0, 0, 256))
    return Uinput("N1X lid accelerometer", [EV_ABS], setup)


class Accel:
    """An IIO accelerometer of the hub, read through its buffer, samples in m/s^2."""

    def __init__(self, platform):
        found = glob.glob(f"/sys/bus/platform/devices/{platform}.auto/iio:device*")
        if not found:
            raise FileNotFoundError(platform)
        self.d = found[0]
        self.dev = os.path.basename(self.d)
        self.scale = float(rd(f"{self.d}/in_accel_scale", "1"))
        self.fd, self.rest = None, b""

    def start(self, freq=None):
        d = self.d
        wr(f"{d}/buffer/enable", 0)
        wr(f"{d}/trigger/current_trigger", f"{rd(f'{d}/name')}-dev{self.dev[len('iio:device'):]}")
        wr(f"{d}/buffer/length", 64)
        for en in glob.glob(f"{d}/scan_elements/*_en"):
            wr(en, 1 if re.search(r"in_accel_[xyz]_en$", en) else 0)
        self.chans, off = [], 0
        for en in sorted(glob.glob(f"{d}/scan_elements/in_accel_[xyz]_en"),
                         key=lambda e: int(rd(e[:-3] + "_index"))):
            m = re.match(r"(le|be):([su])(\d+)/(\d+)>>(\d+)", rd(en[:-3] + "_type"))
            size = int(m.group(4)) // 8
            off = (off + size - 1) // size * size
            self.chans.append((off, size, m.group(2) == "s", int(m.group(3)), int(m.group(5)),
                               "big" if m.group(1) == "be" else "little"))
            off += size
        self.size = off
        self.fd = os.open(f"/dev/{self.dev}", os.O_RDONLY | os.O_NONBLOCK)
        wr(f"{d}/buffer/enable", 1)
        if freq:
            try:
                wr(f"{d}/in_accel_sampling_frequency", freq)
            except OSError as e:
                log(f"{self.dev}: sampling frequency {freq} refused ({e})")

    def read(self):
        try:
            data = self.rest + os.read(self.fd, 4096)
        except BlockingIOError:
            return []
        n = len(data) // self.size
        self.rest = data[n * self.size:]
        out = []
        for i in range(n):
            rec = data[i * self.size:(i + 1) * self.size]
            v = []
            for off, size, signed, bits, shift, order in self.chans:
                x = (int.from_bytes(rec[off:off + size], order) >> shift) & ((1 << bits) - 1)
                if signed and x >> (bits - 1):
                    x -= 1 << bits
                v.append(x * self.scale)
            out.append(v)
        return out

    def stop(self):
        try:
            wr(f"{self.d}/buffer/enable", 0)
        except OSError:
            pass
        if self.fd is not None:
            os.close(self.fd)


def mean(samples):
    return [sum(s[i] for s in samples) / len(samples) for i in range(3)]


def hinge(lid, base, lid_closed):
    """Hinge angle in degrees, 0-375, or None while it cannot be told (moving, hinge vertical)."""
    if not 0.85 * G < math.hypot(*lid) < 1.15 * G:
        return None
    for v in (lid, base):            # the base reads 4 g (its unit is misstated): use ratios
        if math.hypot(v[1], v[2]) < 0.5 * math.hypot(*v):
            return None
    h = (180 + math.degrees(math.atan2(lid[1], lid[2]) - math.atan2(base[1], base[2]))) % 360
    if h < 15 and not lid_closed:    # folded back past 360, not closed
        h += 360
    return h


def main():
    for _ in range(60):              # the hub's devices can come after this service starts
        try:
            lid, base = Accel(LID), Accel(BASE)
            break
        except FileNotFoundError:
            time.sleep(2)
    else:
        sys.exit("sensor hub accelerometers not found")
    lid.start(freq=10)
    base.start()
    sw, acc = switch_device(), accel_device()
    log(f"lid {lid.dev}, base {base.dev}; tablet mode on above {ON_ABOVE:.0f}, "
        f"off below {OFF_BELOW:.0f} degrees")

    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)

    state, candidate, since = None, None, 0.0
    lid_closed = None
    window = {"lid": [], "base": []}
    next_eval = time.monotonic() + 0.5
    try:
        while True:
            select.select([lid.fd, base.fd], [], [], max(0.0, next_eval - time.monotonic()))
            for s in lid.read():
                window["lid"].append(s)
                acc.emit(*((EV_ABS, i, round(s[i] / G * 256)) for i in range(3)))
            window["base"].extend(base.read())
            now = time.monotonic()
            if now < next_eval:
                continue
            next_eval = now + 0.5
            closed = "closed" in rd(LID_STATE)
            if not window["lid"] or not window["base"]:
                continue
            h = hinge(mean(window["lid"]), mean(window["base"]), closed)
            window = {"lid": window["lid"][-1:], "base": window["base"][-1:]}
            if closed != lid_closed:
                log(f"lid switch {'closed' if closed else 'open'}, hinge "
                    f"{'?' if h is None else f'{h:.0f}'}")
                lid_closed = closed
            if h is None:
                continue
            want = True if h > ON_ABOVE else False if h < OFF_BELOW else state
            if want is None:
                want = h > 180
            if want == state:
                candidate = None
                continue
            if want != candidate:
                candidate, since = want, now
            if state is None or now - since >= HOLD:
                sw.emit((EV_SW, SW_TABLET_MODE, int(want)))
                log(f"tablet mode {'on' if want else 'off'} at hinge {h:.0f}")
                state, candidate = want, None
    finally:
        lid.stop()
        base.stop()
        sw.close()
        acc.close()


if __name__ == "__main__":
    main()
