"""n1x-scp-peek: a read-only look at the N1X sensor coprocessor (\\_SB.SCP0, NVDA8200).

For EXP-20261110-q6a1yn (notes/experiments/). Run by hand: `sudo n1x-scp-peek`. Nothing is
written to the hardware or to firmware variables; it only reads:

- the UEFI variables nvSCP.sys (Windows) sends to SCP0 at start: SCPCaliResult and
  NvSCPVar_0..9 (efivarfs; their presence, size and contents);
- the two mailboxes' status registers (resources 3 and 4, offsets 0x100 and 0x104 only: not
  the clear registers at 0x108/0x10C) and the first words of resource 2 (the hub's doorbell
  page: SENH._RST writes 0x1AB20008);
- SCP0's 512 KB SRAM (resource 1), twice, a few seconds apart, to see whether the coprocessor
  is running, plus the text strings in it (nvSCP has a log timer, so SCP0 probably logs there).

All MMIO is read 32 bits at a time from an uncached /dev/mem mapping (the kernel has
CONFIG_IO_STRICT_DEVMEM off, and no Linux driver claims SCP0). Results go to SPARKDATA, under
bootlogs/<host>/scp-peek-<time>/, and a summary to stdout.
"""
import datetime
import hashlib
import mmap
import os
import socket
import struct
import sys
import time

SRAM = (0x1A800000, 0x80000)
DOORBELL = (0x1AB20000, 0x1000)
MBOX = {"mbox-a (0x1AAA0000)": 0x1AAA0000, "mbox-b (0x1AAB0000)": 0x1AAB0000}
EFIVARS = "/sys/firmware/efi/efivars"
VARS = [
    ("SCPCaliResult", "da86db63-0b44-45a4-ad9a-254393010385"),
    ("NvSCPVar_0", "39e6129f-9146-47fc-a1c1-198aea0e3830"),
    ("NvSCPVar_1", "a827d506-835a-4f4e-b773-a2ea7588dc6e"),
    ("NvSCPVar_2", "eb700aec-f4be-4029-852c-d4e17c0b2322"),
    ("NvSCPVar_3", "81338e63-d2ca-495b-9815-7251e309c44c"),
    ("NvSCPVar_4", "ea478c40-8608-4cc5-a0ed-bf23d7502548"),
    ("NvSCPVar_5", "469d2efa-3f30-4d33-a6db-43fee9a38756"),
    ("NvSCPVar_6", "6d2137a0-03d7-46c8-87ef-5c0bd22e088b"),
    ("NvSCPVar_7", "3203478b-ec2e-4c09-9f54-baf1fabc2102"),
    ("NvSCPVar_8", "7a75ecfa-5892-4e1c-b817-a0946573819d"),
    ("NvSCPVar_9", "d8eb2f8f-d5f9-4436-a1d2-d333f3c1ea09"),
]


def read_words(base, length, offsets=None):
    """32-bit reads from physical memory; offsets default to the whole range."""
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        m = mmap.mmap(fd, length, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    finally:
        os.close(fd)
    words = memoryview(m).cast("I")
    try:
        if offsets is None:
            return [words[i] for i in range(length // 4)]
        return {off: words[off // 4] for off in offsets}
    finally:
        words.release()        # the mmap cannot close while a view of it exists
        m.close()


def strings(data, minlen=6):
    out, cur = [], bytearray()
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
            continue
        if len(cur) >= minlen:
            out.append(cur.decode())
        cur = bytearray()
    if len(cur) >= minlen:
        out.append(cur.decode())
    return out


def main():
    if os.geteuid() != 0:
        sys.exit("run as root: sudo n1x-scp-peek")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = "/mnt/sparkdata/bootlogs" if os.path.ismount("/mnt/sparkdata") else "/tmp"
    out = os.path.join(root, socket.gethostname(), f"scp-peek-{stamp}")
    os.makedirs(out, exist_ok=True)
    summary = []

    def say(line=""):
        print(line)
        summary.append(line)

    say(f"n1x-scp-peek {stamp} -> {out}")
    say(f"kernel {os.uname().release}; cmdline {open('/proc/cmdline').read().strip()}")
    say()
    say("== UEFI variables nvSCP sends to SCP0")
    for name, guid in VARS:
        path = os.path.join(EFIVARS, f"{name}-{guid}")
        if not os.path.exists(path):
            say(f"{name:14} absent")
            continue
        raw = open(path, "rb").read()
        attrs, data = struct.unpack("<I", raw[:4])[0], raw[4:]
        open(os.path.join(out, f"efivar-{name}.bin"), "wb").write(data)
        head = data[:16].hex(" ")
        say(f"{name:14} {len(data):6} bytes attrs=0x{attrs:x} sha256={hashlib.sha256(data).hexdigest()[:16]} head: {head}")
    others = sorted(n for n in os.listdir(EFIVARS) if "scp" in n.lower() or "cali" in n.lower()
                    or "manufact" in n.lower())
    say(f"other efivars matching scp/cali/manufact: {', '.join(others) if others else 'none'}")
    say()

    say("== mailbox status registers (0x100 in, 0x104 out)")
    for label, base in MBOX.items():
        regs = read_words(base, 0x1000, [0x100, 0x104])
        say(f"{label}: in=0x{regs[0x100]:08x} out=0x{regs[0x104]:08x}")
    db = read_words(DOORBELL[0], DOORBELL[1], [0x0, 0x4, 0x8, 0xC, 0x10, 0x14, 0x18, 0x1C])
    say("doorbell page 0x1AB20000: " + " ".join(f"+{o:02x}=0x{v:08x}" for o, v in db.items()))
    say()

    say("== SRAM 0x1A800000 (512 KB), two reads 5 s apart")
    first = read_words(*SRAM)
    time.sleep(5)
    second = read_words(*SRAM)
    a = struct.pack(f"<{len(first)}I", *first)
    b = struct.pack(f"<{len(second)}I", *second)
    open(os.path.join(out, "sram-1.bin"), "wb").write(a)
    open(os.path.join(out, "sram-2.bin"), "wb").write(b)
    changed = [i * 4 for i, (x, y) in enumerate(zip(first, second)) if x != y]
    nonzero = sum(1 for w in second if w not in (0, 0xFFFFFFFF))
    say(f"words not 0/0xffffffff: {nonzero} of {len(second)}; changed between reads: {len(changed)}")
    if changed:
        say("changed offsets (first 32): " + " ".join(f"0x{o:05x}" for o in changed[:32]))
    cali = second[0x71000 // 4: 0x71000 // 4 + 2]
    say(f"calibration slot +0x71000: 0x{cali[0]:08x} 0x{cali[1]:08x}")
    text = strings(b)
    open(os.path.join(out, "sram-strings.txt"), "w").write("\n".join(text) + "\n")
    say(f"text strings (>= 6 chars): {len(text)}; first 40:")
    for s in text[:40]:
        say(f"  {s[:120]}")
    open(os.path.join(out, "summary.txt"), "w").write("\n".join(summary) + "\n")
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
