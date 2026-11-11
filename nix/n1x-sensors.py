"""n1x-sensors: what the sensor hub reports in each posture (for auto-rotate and tablet mode).

Run by hand: `sudo n1x-sensors`. It walks through four postures (laptop, screen flat, tent,
tablet), about 8 s each, and records every second:
- each IIO accelerometer (name, label, location, mount matrix, x/y/z in m/s^2),
- each HID custom sensor (HID-SENSOR-2000e1.*: probably hinge / lid angle): every input
  field's name, units and value, with the sensor enabled for the duration,
- iio-sensor-proxy's orientation (monitor-sensor).
Results go to SPARKDATA under bootlogs/<host>/sensors-<time>/ and a summary to stdout.
Only reads, apart from enable_sensor on the custom sensors, which is put back afterwards.
"""
import datetime
import glob
import os
import socket
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


def rd(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def accels():
    out = []
    for d in sorted(glob.glob("/sys/bus/iio/devices/iio:device*")):
        if not os.path.exists(f"{d}/in_accel_x_raw"):
            continue
        out.append(d)
    return out


def accel_info(d):
    return {
        "dev": os.path.basename(d), "name": rd(f"{d}/name"), "label": rd(f"{d}/label"),
        "location": rd(f"{d}/location"), "mount_matrix": rd(f"{d}/in_accel_mount_matrix"),
        "parent": os.path.basename(os.path.realpath(f"{d}/..")),
    }


def accel_read(d):
    scale = float(rd(f"{d}/in_accel_scale", "1") or 1)
    vals = []
    for ax in "xyz":
        raw = rd(f"{d}/in_accel_{ax}_raw", "nan")
        try:
            vals.append(round(float(raw) * scale, 2))
        except ValueError:
            vals.append(None)
    return vals


def customs():
    return sorted(glob.glob("/sys/bus/platform/devices/HID-SENSOR-2000e1.*"))


def custom_fields(c):
    """input fields as (prefix, name, units) e.g. ('input-0-200304', 'data-field-...')"""
    fields = []
    for p in sorted(glob.glob(f"{c}/input-*-name")):
        prefix = os.path.basename(p)[: -len("-name")]
        fields.append((prefix, rd(p), rd(f"{c}/{prefix}-units"), rd(f"{c}/{prefix}-unit-expo")))
    return fields


def custom_read(c, fields):
    return {prefix: rd(f"{c}/{prefix}-value", "?") for prefix, _, _, _ in fields}


def orientation():
    try:
        r = subprocess.run(["timeout", "1.5", "monitor-sensor", "--accel"], capture_output=True,
                           text=True)
        lines = [l for l in r.stdout.splitlines() if "orientation" in l.lower()]
        return lines[-1].strip() if lines else "?"
    except OSError:
        return "monitor-sensor missing"


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
        log.flush()                  # a hung sysfs read must not leave an empty summary

    acc = accels()
    cus = customs()
    say(f"n1x-sensors {stamp} -> {out}")
    say("accelerometers:")
    for d in acc:
        say("  " + " ".join(f"{k}={v}" for k, v in accel_info(d).items()))
        say("    udev: " + " ".join(
            l.split("=", 1)[0][3:] + "=" + l.split("=", 1)[1]
            for l in subprocess.run(["udevadm", "info", "-q", "property", "-p", d],
                                    capture_output=True, text=True).stdout.splitlines()
            if l.startswith("E: ACCEL") or l.startswith("E: IIO")))
    fields = {}
    enabled_before = {}
    for c in cus:
        fields[c] = custom_fields(c)
        enabled_before[c] = rd(f"{c}/enable_sensor", "0")
        say(f"custom sensor {os.path.basename(c)} (enable_sensor was {enabled_before[c]}):")
        for prefix, name, units, expo in fields[c]:
            say(f"  {prefix}: {name} units={units} expo={expo}")
    try:
        for c in cus:
            with open(f"{c}/enable_sensor", "w") as f:
                f.write("1")
        time.sleep(0.5)
        say()
        for pose, how in POSES:
            input(f"\n>>> {pose}: {how}. Put the laptop like that, then press Enter ")
            say(f"== {pose} ({how})")
            for i in range(SECONDS):
                parts = [f"t={i}"]
                for d in acc:
                    parts.append(f"{os.path.basename(d)}={accel_read(d)}")
                for c in cus:
                    vals = custom_read(c, fields[c])
                    parts.append(os.path.basename(c).split(".")[1] + "=" +
                                 ",".join(f"{p.split('-')[2]}:{v}" for p, v in vals.items()))
                if i in (0, SECONDS - 1):
                    parts.append(f"proxy: {orientation()}")
                say("  " + " ".join(parts))
                time.sleep(1)
    finally:
        for c in cus:
            try:
                with open(f"{c}/enable_sensor", "w") as f:
                    f.write(enabled_before[c] or "0")
            except OSError:
                pass
        log.close()
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
