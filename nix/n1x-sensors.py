"""n1x-sensors: what the sensor hub reports in each posture (for auto-rotate and tablet mode).

Run by hand: `sudo n1x-sensors`. It walks through four postures (laptop, screen flat, tent,
tablet), about 8 s each, and records every second:
- each IIO accelerometer (name, label, location, mount matrix; samples in m/s^2),
- each HID custom sensor (HID-SENSOR-2000e1.*: probably hinge / lid angle): its input fields
  (name, units, size), decoded from the samples it streams.
Results go to SPARKDATA under bootlogs/<host>/sensors-<time>/ and a summary to stdout.

The hub (MSFW1111) never answers GET_INPUT_REPORT, so sysfs value reads (in_accel_x_raw,
input-*-value) cannot work: everything is read from the streams instead, the IIO buffer
(/dev/iio:deviceN) and the custom sensors' /dev/HID-SENSOR-2000e1.* devices. Only one reader
can hold a stream, so iio-sensor-proxy is stopped for the run and started again afterwards.
Changes put back at the end: buffer enable, trigger, scan elements, enable_sensor.
"""
import datetime
import glob
import os
import re
import socket
import struct
import subprocess
import sys
import time

POSES = [
    ("laptop", "normal laptop use, screen open about 110 degrees"),
    ("flat", "screen opened flat, about 180 degrees"),
    ("tent", "tent: folded past 270 degrees, standing on both edges"),
    ("tablet", "tablet: folded fully back, 360 degrees, held upright in landscape"),
]
SECONDS = 8
IIO = "/sys/bus/iio/devices"


def rd(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def wr(path, value):
    with open(path, "w") as f:
        f.write(str(value))


def drain(fd):
    data = b""
    while True:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return data
        if not chunk:
            return data
        data += chunk


class Accel:
    """An IIO accelerometer read through its buffer."""

    def __init__(self, d):
        self.d = d
        self.dev = os.path.basename(d)
        self.scale = float(rd(f"{d}/in_accel_scale", "1") or 1)
        self.fd = None
        self.rest = b""
        self.saved = {}

    def info(self):
        d = self.d
        return {
            "dev": self.dev, "name": rd(f"{d}/name"), "label": rd(f"{d}/label"),
            "location": rd(f"{d}/location"), "mount_matrix": rd(f"{d}/in_accel_mount_matrix"),
            "freq": rd(f"{d}/in_accel_sampling_frequency"),
            "hysteresis": rd(f"{d}/in_accel_hysteresis"),
            "parent": os.path.basename(os.path.realpath(f"{d}/..")),
        }

    def start(self):
        d = self.d
        wr(f"{d}/buffer/enable", 0)
        scan = [f"{d}/scan_elements/in_accel_{a}_en" for a in "xyz"]
        scan.append(f"{d}/scan_elements/in_timestamp_en")
        for p in [f"{d}/trigger/current_trigger", f"{d}/buffer/length"] + scan:
            self.saved[p] = rd(p)
        wr(f"{d}/trigger/current_trigger", f"{rd(f'{d}/name')}-dev{self.dev[len('iio:device'):]}")
        wr(f"{d}/buffer/length", 256)
        for p in scan:
            wr(p, 1)
        self.layout()
        note = enable_buffer(d)
        self.fd = os.open(f"/dev/{self.dev}", os.O_RDONLY | os.O_NONBLOCK)
        return note

    def layout(self):
        """(name, offset, bytes, signed, bits, shift, big-endian) per enabled channel."""
        chans = []
        for en in glob.glob(f"{self.d}/scan_elements/*_en"):
            if rd(en) != "1":
                continue
            base = en[:-len("_en")]
            m = re.match(r"(le|be):([su])(\d+)/(\d+)>>(\d+)", rd(f"{base}_type"))
            chans.append((int(rd(f"{base}_index")), os.path.basename(base), m))
        off, align, self.chans = 0, 1, []
        for _, name, m in sorted(chans):
            size = int(m.group(4)) // 8
            off = (off + size - 1) // size * size
            self.chans.append((name, off, size, m.group(2) == "s", int(m.group(3)),
                               int(m.group(5)), m.group(1) == "be"))
            off += size
            align = max(align, size)
        self.size = (off + align - 1) // align * align

    def read(self):
        """samples since the last call, as [x, y, z] in m/s^2"""
        data = self.rest + drain(self.fd)
        n = len(data) // self.size
        self.rest = data[n * self.size:]
        out = []
        for i in range(n):
            rec = data[i * self.size:(i + 1) * self.size]
            vals = {}
            for name, off, size, signed, bits, shift, be in self.chans:
                v = int.from_bytes(rec[off:off + size], "big" if be else "little") >> shift
                v &= (1 << bits) - 1
                if signed and v >> (bits - 1):
                    v -= 1 << bits
                vals[name] = v
            out.append([round(vals[f"in_accel_{a}"] * self.scale, 2) for a in "xyz"])
        return out

    def stop(self):
        if self.fd is not None:
            os.close(self.fd)
        try:
            wr(f"{self.d}/buffer/enable", 0)
            for p, v in self.saved.items():
                if v != "":
                    wr(p, v)
        except OSError:
            pass


def enable_buffer(d):
    """Enable an IIO buffer in a child process: on a kernel without patch 0004 the sensor's
    power-on sleeps ~49.7 days, and killing the writer is what ends that sleep."""
    p = subprocess.Popen([sys.executable, "-c",
                          f"open({f'{d}/buffer/enable'!r}, 'w').write('1')"])
    try:
        p.wait(5)
        note = "" if p.returncode == 0 else f"enable failed (rc {p.returncode})"
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        note = "power-on sleep cut short (kernel without patch 0004)"
    if rd(f"{d}/buffer/enable") != "1":
        note += " buffer not enabled"
    return note.strip()


class Custom:
    """A HID custom sensor read through /dev/HID-SENSOR-2000e1.*."""

    HEADER = struct.Struct("<IQI")  # usage_id, timestamp (ns), raw_len; packed

    def __init__(self, c):
        self.c = c
        self.name = os.path.basename(c)
        self.fields = []
        for d in glob.glob(f"{c}/input-*"):
            prefix = os.path.basename(d)
            idx = int(prefix.split("-")[1], 16)
            self.fields.append((idx, prefix, rd(f"{d}/{prefix}-name"), rd(f"{d}/{prefix}-units"),
                                rd(f"{d}/{prefix}-unit-expo"), int(rd(f"{d}/{prefix}-size", "0") or 0),
                                int(rd(f"{d}/{prefix}-minimum", "0") or 0)))
        self.fields.sort()
        self.enabled_before = rd(f"{c}/enable_sensor", "0")
        self.fd = None
        self.rest = b""

    def start(self):
        self.fd = os.open(f"/dev/{self.name}", os.O_RDONLY | os.O_NONBLOCK)
        wr(f"{self.c}/enable_sensor", 1)

    def read(self):
        """samples since the last call, each as {field prefix: value}"""
        data = self.rest + drain(self.fd)
        out = []
        while len(data) >= self.HEADER.size:
            _, _, raw_len = self.HEADER.unpack_from(data)
            if len(data) < self.HEADER.size + raw_len:
                break
            raw = data[self.HEADER.size:self.HEADER.size + raw_len]
            data = data[self.HEADER.size + raw_len:]
            vals, off = {}, 0
            for _, prefix, _, _, _, size, minimum in self.fields:
                vals[prefix] = int.from_bytes(raw[off:off + size], "little", signed=minimum < 0)
                off += size
            out.append(vals)
        self.rest = data
        return out

    def stop(self):
        try:
            wr(f"{self.c}/enable_sensor", self.enabled_before or "0")
        except OSError:
            pass
        if self.fd is not None:
            os.close(self.fd)


def orientation():
    try:
        r = subprocess.run(["timeout", "3", "monitor-sensor", "--accel"], capture_output=True,
                           text=True)
        lines = [l for l in r.stdout.splitlines() if "orientation" in l.lower()]
        return lines[-1].strip() if lines else "?"
    except OSError:
        return "monitor-sensor missing"


def mean(samples):
    return [round(sum(s[i] for s in samples) / len(samples), 2) for i in range(3)]


def main():
    if os.geteuid() != 0:
        sys.exit("run as root: sudo n1x-sensors")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = "/mnt/sparkdata/bootlogs" if os.path.ismount("/mnt/sparkdata") else "/tmp"
    out = os.path.join(root, socket.gethostname(), f"sensors-{stamp}")
    os.makedirs(out, exist_ok=True)
    log = open(os.path.join(out, "summary.txt"), "w")

    def say(line=""):
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    acc = [Accel(d) for d in sorted(glob.glob(f"{IIO}/iio:device*"))
           if os.path.exists(f"{d}/scan_elements/in_accel_x_en")]
    cus = [Custom(c) for c in sorted(glob.glob("/sys/bus/platform/devices/HID-SENSOR-2000e1.*"))]
    say(f"n1x-sensors {stamp} -> {out}")
    say("accelerometers:")
    for a in acc:
        say("  " + " ".join(f"{k}={v}" for k, v in a.info().items()))
        say("    udev: " + " ".join(
            l.split("=", 1)[0][3:] + "=" + l.split("=", 1)[1]
            for l in subprocess.run(["udevadm", "info", "-q", "property", "-p", a.d],
                                    capture_output=True, text=True).stdout.splitlines()
            if l.startswith("E: ACCEL") or l.startswith("E: IIO")))
    for c in cus:
        say(f"custom sensor {c.name} (enable_sensor was {c.enabled_before}):")
        for _, prefix, name, units, expo, size, minimum in c.fields:
            say(f"  {prefix}: {name} units={units} expo={expo} size={size} min={minimum}")

    proxy = subprocess.run(["systemctl", "is-active", "--quiet", "iio-sensor-proxy"]).returncode == 0
    if proxy:
        say("stopping iio-sensor-proxy for the run")
        subprocess.run(["systemctl", "stop", "iio-sensor-proxy"])
    try:
        for a in acc:
            note = a.start()
            if note:
                say(f"  {a.dev}: {note}")
        for c in cus:
            c.start()
        for pose, how in POSES:
            input(f"\n>>> {pose}: {how}. Put the laptop like that, then press Enter ")
            for s in acc + cus:
                s.read()                 # drop what arrived while moving
            say(f"== {pose} ({how})")
            for i in range(SECONDS):
                time.sleep(1)
                parts = [f"t={i}"]
                for a in acc:
                    smp = a.read()
                    parts.append(f"{a.dev}={mean(smp) if smp else None}/{len(smp)}")
                for c in cus:
                    smp = c.read()
                    last = ",".join(f"{p.split('-')[2]}:{v}" for p, v in smp[-1].items()) if smp else None
                    parts.append(f"{c.name.split('.')[1]}={last}/{len(smp)}")
                say("  " + " ".join(parts))
    finally:
        for s in acc + cus:
            s.stop()
        if proxy:
            subprocess.run(["systemctl", "start", "iio-sensor-proxy"])
            time.sleep(1)
            say(f"iio-sensor-proxy restarted; now: {orientation()}")
        log.close()
    print(f"\nwritten to {out}\n(per sensor: mean [x, y, z] m/s^2 or the last custom sample / "
          "samples in that second)")


if __name__ == "__main__":
    main()
