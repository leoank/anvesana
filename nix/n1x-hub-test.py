"""n1x-hub-test: why does the sensor hub (MSFW1111, spi-hid) never interrupt on Linux?

For EXP-20261110-rwymta (notes/experiments/). Run by hand:
`sudo n1x-hub-test`. It re-probes the hub's driver (spi_hid_acpi) twice, which calls the
hub's _RST (the doorbell into the sensor coprocessor), and watches what comes back:

  A. as the driver normally does: reset first, then enable the interrupt;
  B. with spi_hid.irq_before_reset=1: interrupt enabled before the reset, as Windows does.

Both with spi_hid.poll_after_reset_ms=1500: if no reset response by then, the driver reads
the hub once over SPI without the interrupt and logs the header bytes (dmesg).

During each probe it samples EINT 190's bit in the EINT controller (block 3 at 0x1C54A000,
index 9: status, mask, sensitivity, polarity, domain enable) every 20 ms for 3 s, read-only
through /dev/mem, and the IRQ 232 count. Writes nothing to hardware itself; the driver's
probe does what it always does (the _RST doorbell and SPI reads). Results go to SPARKDATA
under bootlogs/<host>/hub-test-<time>/ and a summary to stdout. Leaves both parameters at 0.
"""
import datetime
import mmap
import os
import socket
import subprocess
import sys
import time

EINT_BASE, EINT_BIT = 0x1C54A000, 9          # EINT 190 = block 3, index 9 (spi-hid README)
REGS = {"stat": 0x000, "mask": 0x080, "sens": 0x140, "pol": 0x300, "dom_en": 0x400,
        "dbnc": 0x500 + (EINT_BIT // 4) * 4, "event": 0x800}
DEV = "spi-MSFW1111:00"
DRV = "/sys/bus/spi/drivers/spi_hid_acpi"
PARAMS = "/sys/module/spi_hid/parameters"


def eint_regs():
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=EINT_BASE)
    finally:
        os.close(fd)
    words = memoryview(m).cast("I")
    try:
        return {name: words[off // 4] for name, off in REGS.items()}
    finally:
        words.release()
        m.close()


def irq_count():
    for line in open("/proc/interrupts"):
        if "MSFW1111" in line:
            parts = line.split()
            return sum(int(p) for p in parts[1:] if p.isdigit()), line.strip()
    return None, "no MSFW1111 line in /proc/interrupts"


def setp(name, value):
    with open(os.path.join(PARAMS, name), "w") as f:
        f.write(str(value))


def dmesg_lines():
    out = subprocess.run(["dmesg"], capture_output=True, text=True).stdout.splitlines()
    return out


def bit(word):
    return (word >> EINT_BIT) & 1


def trial(label, irq_first, say, out):
    say(f"== trial {label}: irq_before_reset={int(irq_first)} poll_after_reset_ms=1500")
    setp("irq_before_reset", 1 if irq_first else 0)
    setp("poll_after_reset_ms", 1500)
    before_dmesg = len(dmesg_lines())
    if os.path.exists(os.path.join(DRV, DEV)):
        with open(os.path.join(DRV, "unbind"), "w") as f:
            f.write(DEV)
        time.sleep(0.5)
    r0 = eint_regs()
    c0, _ = irq_count()
    say("before bind: " + " ".join(f"{k}={bit(v)}" for k, v in r0.items())
        + f" (stat word 0x{r0['stat']:08x}); irq count {c0}")
    samples = []
    with open(os.path.join(DRV, "bind"), "w") as f:
        f.write(DEV)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 3.0:
        r = eint_regs()
        samples.append((time.monotonic() - t0, r))
        time.sleep(0.02)
    c1, line = irq_count()
    stat_hits = [f"{t:.2f}s" for t, r in samples if bit(r["stat"])]
    mask_vals = sorted({bit(r["mask"]) for _, r in samples})
    say(f"after bind: irq count {c1} ({line})")
    say(f"EINT 190 status bit set in {len(stat_hits)} of {len(samples)} samples"
        + (f", first at {stat_hits[0]}" if stat_hits else ""))
    say(f"EINT 190 mask bit values seen: {mask_vals} (1 = masked); last sample: "
        + " ".join(f"{k}={bit(v)}" for k, v in samples[-1][1].items()))
    new = dmesg_lines()[before_dmesg:]
    hits = [l for l in new if "spi_hid" in l or "MSFW1111" in l or "anvesana" in l]
    say(f"dmesg ({len(hits)} spi-hid lines):")
    for l in hits[:40]:
        say("  " + l)
    with open(os.path.join(out, f"trial-{label}.tsv"), "w") as f:
        f.write("t\t" + "\t".join(REGS) + "\n")
        for t, r in samples:
            f.write(f"{t:.3f}\t" + "\t".join(f"0x{r[k]:08x}" for k in REGS) + "\n")
    with open(os.path.join(out, f"trial-{label}-dmesg.txt"), "w") as f:
        f.write("\n".join(new) + "\n")
    say()


def main():
    if os.geteuid() != 0:
        sys.exit("run as root: sudo n1x-hub-test")
    for p in (DRV, PARAMS):
        if not os.path.isdir(p):
            sys.exit(f"{p} missing: is spi-hid loaded?")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = "/mnt/sparkdata/bootlogs" if os.path.ismount("/mnt/sparkdata") else "/tmp"
    out = os.path.join(root, socket.gethostname(), f"hub-test-{stamp}")
    os.makedirs(out, exist_ok=True)
    summary = []

    def say(line=""):
        print(line, flush=True)
        summary.append(line)

    say(f"n1x-hub-test {stamp} -> {out}")
    say(f"kernel {os.uname().release}")
    say()
    try:
        trial("A-reset-then-irq", False, say, out)
        trial("B-irq-then-reset", True, say, out)
    finally:
        setp("irq_before_reset", 0)
        setp("poll_after_reset_ms", 0)
        open(os.path.join(out, "summary.txt"), "w").write("\n".join(summary) + "\n")
    iio = [d for d in os.listdir("/sys/bus/iio/devices")] if os.path.isdir("/sys/bus/iio/devices") else []
    names = []
    for d in iio:
        try:
            names.append(open(f"/sys/bus/iio/devices/{d}/name").read().strip())
        except OSError:
            pass
    say(f"IIO devices now: {', '.join(names) if names else 'none'}")
    open(os.path.join(out, "summary.txt"), "w").write("\n".join(summary) + "\n")
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
