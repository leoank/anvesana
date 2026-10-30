"""Drive the MSI "Mystic Light" keyboard RGB controller (USB HID 1462:1609) on Windows.

Protocol decoded from MSI Center S's API_MysticLight.dll and verified on bbaum-pc-7; see
docs/n1x-bringup-log.md. Every command is HID feature report 2 (64 bytes), then feature
report 1 is read back as the reply (it echoes the command).

This tool never sends save-to-flash (02 a0): changes last until MSI Center re-applies its
profile or the machine reboots. The backlight itself is switched with Fn + F8; while it is
off, commands are accepted but nothing lights up.

  python scripts/msi-mystic-light.py steady ff0000            all zones red
  python scripts/msi-mystic-light.py steady ff0000 --zones 0,3
  python scripts/msi-mystic-light.py zones ff0000 00ff00 0000ff ffffff   one colour per zone, left to right
  python scripts/msi-mystic-light.py breath ff0000 --speed slow
  python scripts/msi-mystic-light.py cycle [--random] --speed fast
  python scripts/msi-mystic-light.py wave --mode horizontal|vertical|circular [--outward]
  python scripts/msi-mystic-light.py off
  python scripts/msi-mystic-light.py demo                      zones, breath, cycle, wave (10 s each)
"""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import time

VID_PID = "vid_1462&pid_1609"
ZONES = 4
STYLES = {"off": 0, "steady": 1, "breath": 2, "cycle": 3, "wave": 4}
SPEEDS = {"slow": 8.0, "medium": 6.0, "fast": 4.0}  # seconds per period, as MSI Center uses
WAVE_MODES = {"circular": 0, "horizontal": 1, "vertical": 2}
RAINBOW = [(0, 255, 0, 0), (17, 255, 255, 0), (33, 0, 255, 0), (50, 0, 255, 255), (67, 0, 0, 255),
           (83, 255, 0, 255), (100, 255, 0, 0)]


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]


class _IFACE(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("guid", _GUID), ("flags", ctypes.c_uint32), ("reserved", ctypes.c_size_t)]


class Controller:
    def __init__(self, verbose: bool = False):
        if sys.platform != "win32":
            raise SystemExit("Windows only; on Linux use hidraw (HIDIOCSFEATURE / HIDIOCGFEATURE) with the same bytes")
        self.verbose = verbose
        self.hid, self.k32 = ctypes.WinDLL("hid"), ctypes.WinDLL("kernel32", use_last_error=True)
        self.k32.CreateFileW.restype = ctypes.c_void_p
        self.k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                         ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        self.k32.CloseHandle.argtypes = [ctypes.c_void_p]
        for fn in ("HidD_SetFeature", "HidD_GetFeature"):
            getattr(self.hid, fn).argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        self.handle = self.k32.CreateFileW(self._path(), 0xC0000000, 3, None, 3, 0, None)  # read/write, shared
        if self.handle in (None, ctypes.c_void_p(-1).value):
            raise SystemExit(f"cannot open the controller (Windows error {ctypes.get_last_error()})")

    def _path(self) -> str:
        setup = ctypes.WinDLL("setupapi")
        setup.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        setup.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
        setup.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                      ctypes.c_uint32, ctypes.c_void_p]
        setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                           ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
        setup.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        guid = _GUID()
        self.hid.HidD_GetHidGuid(ctypes.byref(guid))
        info = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)  # PRESENT | DEVICEINTERFACE
        try:
            for i in range(1024):
                iface = _IFACE(cbSize=ctypes.sizeof(_IFACE))
                if not setup.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), i, ctypes.byref(iface)):
                    break
                need = ctypes.c_uint32()
                setup.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), None, 0, ctypes.byref(need), None)
                buf = ctypes.create_string_buffer(need.value)
                struct.pack_into("<I", buf, 0, 8)  # SP_DEVICE_INTERFACE_DETAIL_DATA_W.cbSize on 64-bit
                if setup.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), buf, need, None, None):
                    path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                    if VID_PID in path.lower():
                        return path
        finally:
            setup.SetupDiDestroyDeviceInfoList(info)
        raise SystemExit("MSI Mystic Light controller (1462:1609) not found")

    def close(self):
        self.k32.CloseHandle(self.handle)

    def command(self, *payload: int) -> bytes:
        if len(payload) > 1 and payload[0] == 0x02 and payload[1] == 0xA0:
            raise ValueError("refusing to send save-to-flash (02 a0)")
        out = (ctypes.c_ubyte * 64)(*payload)
        reply = (ctypes.c_ubyte * 64)(1)
        if not self.hid.HidD_SetFeature(self.handle, out, 64) or not self.hid.HidD_GetFeature(self.handle, reply, 64):
            raise SystemExit(f"HID transfer failed (Windows error {ctypes.get_last_error()})")
        if self.verbose:
            print(f"  sent {bytes(out)[:16].hex(' ')} ...  reply {bytes(reply)[:16].hex(' ')} ...")
        return bytes(reply)

    def select(self, zones: list[int] | None = None):
        """02 01 + 32-byte bitmap; zone z is bit z of byte 0. None selects everything."""
        if zones is None:
            bitmap = [0xFF] * 32
        else:
            bitmap = [0] * 32
            for z in zones:
                bitmap[z >> 3] |= 1 << (z & 7)
        self.command(0x02, 0x01, *bitmap)

    def style(self, style: int, seconds: float = 0.0, wavelength: float = 0.0, mode: int = 0, direction: int = 0,
              stops: list[tuple[int, int, int, int]] = ()):
        """02 02 style period(u16 LE, s*100) keyX keyY wavelength*10 mode direction + stops (pos, R, G, B)."""
        ticks = round(seconds * 100)
        flat = [b for stop in stops for b in stop][:54]  # 64-byte report, stops start at byte 10
        self.command(0x02, 0x02, style, ticks & 0xFF, ticks >> 8, 0, 0, round(wavelength * 10), mode, direction, *flat)


def solid(rgb: tuple[int, int, int]) -> list[tuple[int, int, int, int]]:
    return [(0, *rgb), (100, *rgb)]


def colour(text: str) -> tuple[int, int, int]:
    text = text.lstrip("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError(f"colour must be RRGGBB hex, got {text!r}")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true", help="print every report sent and received")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("steady")
    s.add_argument("rgb", type=colour)
    s.add_argument("--zones", help="comma-separated zones 0-3, left to right (default: all)")
    s = sub.add_parser("zones", help="one colour per zone, left to right")
    s.add_argument("rgb", type=colour, nargs=ZONES)
    s = sub.add_parser("breath")
    s.add_argument("rgb", type=colour)
    s.add_argument("--speed", choices=SPEEDS, default="medium")
    s = sub.add_parser("cycle")
    s.add_argument("--random", action="store_true")
    s.add_argument("--speed", choices=SPEEDS, default="medium")
    s = sub.add_parser("wave")
    s.add_argument("--mode", choices=WAVE_MODES, default="horizontal")
    s.add_argument("--outward", action="store_true")
    s.add_argument("--speed", choices=SPEEDS, default="medium")
    sub.add_parser("off")
    sub.add_parser("demo")
    args = p.parse_args(argv)

    c = Controller(args.verbose)
    try:
        if args.cmd == "steady":
            c.select([int(z) for z in args.zones.split(",")] if args.zones else None)
            c.style(STYLES["steady"], stops=solid(args.rgb))
        elif args.cmd == "zones":
            for z, rgb in enumerate(args.rgb):
                c.select([z])
                c.style(STYLES["steady"], stops=solid(rgb))
        elif args.cmd == "breath":
            c.select()
            c.style(STYLES["breath"], SPEEDS[args.speed], stops=solid(args.rgb))
        elif args.cmd == "cycle":
            c.select()
            c.style(STYLES["cycle"], SPEEDS[args.speed], direction=int(args.random), stops=RAINBOW)
        elif args.cmd == "wave":
            c.select()
            c.style(STYLES["wave"], SPEEDS[args.speed], wavelength=1.5, mode=WAVE_MODES[args.mode],
                    direction=int(args.outward), stops=RAINBOW)
        elif args.cmd == "off":
            c.select()
            c.style(STYLES["off"], mode=1)
        elif args.cmd == "demo":
            steps = [("zones: red, green, blue, white (left to right)",
                      lambda: [(c.select([z]), c.style(1, stops=solid(rgb)))
                               for z, rgb in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)])]),
                     ("breath red", lambda: (c.select(), c.style(2, SPEEDS["medium"], stops=solid((255, 0, 0))))),
                     ("colour cycle", lambda: (c.select(), c.style(3, SPEEDS["fast"], stops=RAINBOW))),
                     ("wave horizontal", lambda: (c.select(), c.style(4, SPEEDS["medium"], 1.5, 1, 0, RAINBOW))),
                     ("wave circular outward", lambda: (c.select(), c.style(4, SPEEDS["medium"], 1.5, 0, 1, RAINBOW)))]
            for label, run in steps:
                print(f">>> {label}", flush=True)
                run()
                time.sleep(10)
    finally:
        c.close()
    print("done (not saved to flash; MSI Center or a reboot restores the saved profile)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
