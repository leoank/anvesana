"""HID top-level collections, in one schema for both OSes.

Input devices on a convertible (touch screen, pen, touchpad, keyboard, sensor hub, RGB
controllers) are HID over I2C / SPI / USB. What a Linux driver needs is the report layout:
which collections exist (pen, touch screen, touch pad, haptics, vendor), and which usages
each input / output / feature report carries (pressure, tilt, battery strength, transducer
serial, contact count, vendor blobs). Windows exposes it through hid.dll's parsed caps;
Linux exposes the raw report descriptor, parsed here.

  collection = {usage_page, usage, name,
                reports: {input|output|feature: [{report_id, usage_page, usages, bits, count}]}}
"""

from __future__ import annotations

PAGES = {0x01: "Generic Desktop", 0x07: "Keyboard", 0x08: "LED", 0x09: "Button", 0x0C: "Consumer",
         0x0D: "Digitizer", 0x0E: "Haptics", 0x20: "Sensor", 0x59: "Lighting", 0x84: "Power", 0x85: "Battery"}

# (page, usage) -> name, for collection usages and the field usages that matter for drivers.
USAGES = {
    (0x01, 0x01): "pointer", (0x01, 0x02): "mouse", (0x01, 0x05): "gamepad", (0x01, 0x06): "keyboard",
    (0x01, 0x0C): "wireless radio controls",
    (0x01, 0x0D): "portable device control", (0x01, 0x30): "X", (0x01, 0x31): "Y", (0x01, 0x80): "system control",
    (0x0C, 0x01): "consumer control",
    (0x0D, 0x01): "digitizer", (0x0D, 0x02): "pen", (0x0D, 0x04): "touch screen", (0x0D, 0x05): "touch pad",
    (0x0D, 0x0E): "device configuration", (0x0D, 0x20): "stylus", (0x0D, 0x22): "finger",
    (0x0D, 0x30): "tip pressure", (0x0D, 0x32): "in range", (0x0D, 0x3B): "battery strength",
    (0x0D, 0x3C): "invert", (0x0D, 0x3F): "azimuth", (0x0D, 0x5A): "secondary barrel switch",
    (0x0D, 0x60): "latency mode", (0xFF00, 0xC5): "certification blob (THQA)", (0x0D, 0x3D): "X tilt", (0x0D, 0x3E): "Y tilt", (0x0D, 0x41): "twist",
    (0x0D, 0x42): "tip switch", (0x0D, 0x44): "barrel switch", (0x0D, 0x45): "eraser",
    (0x0D, 0x47): "confidence", (0x0D, 0x48): "width", (0x0D, 0x49): "height", (0x0D, 0x51): "contact id",
    (0x0D, 0x52): "device mode", (0x0D, 0x54): "contact count", (0x0D, 0x55): "contact count max",
    (0x0D, 0x56): "scan time", (0x0D, 0x57): "surface switch", (0x0D, 0x58): "button switch",
    (0x0D, 0x59): "pad type", (0x0D, 0x5B): "transducer serial number", (0x0D, 0xC5): "certification blob",
    (0x0E, 0x01): "simple haptic controller", (0x0E, 0x21): "manual trigger", (0x0E, 0x23): "intensity",
    (0x20, 0x01): "sensor", (0x20, 0x73): "accelerometer 3D", (0x20, 0x76): "gyrometer 3D",
    (0x20, 0x41): "ambient light", (0x20, 0x8A): "orientation", (0x20, 0xE1): "hinge angle",
    (0x59, 0x01): "lamp array",
}


def name(page: int, usage: int) -> str:
    if (page, usage) in USAGES:
        return USAGES[(page, usage)]
    if page >= 0xFF00:
        return f"vendor 0x{page:04x}:0x{usage:02x}"
    return f"{PAGES.get(page, f'page 0x{page:02x}')} 0x{usage:02x}"


def field_text(f: dict) -> str:
    """{report_id 2, page 0x0D, usages [0x30]} -> "#2 tip pressure (16b)"."""
    us = f["usages"]
    if isinstance(us, list) and len(us) == 2 and f.get("range"):
        what = f"{name(f['usage_page'], us[0])}..{name(f['usage_page'], us[1])}"
    else:
        what = ", ".join(name(f["usage_page"], u) for u in us) or f"page 0x{f['usage_page']:02x}"
    size = f"{f['bits']}b" + (f"x{f['count']}" if f.get("count", 1) > 1 else "")
    return f"#{f['report_id']} {what} ({size})"


def summary(collections: list[dict]) -> str:
    return ", ".join(c["name"] for c in collections)


# ------------------------------------------------------------------ descriptor parser

_MAIN = {0x8: "input", 0x9: "output", 0xB: "feature"}


def parse_descriptor(desc: bytes) -> list[dict]:
    """Top-level collections of a raw report descriptor (Linux sysfs report_descriptor)."""
    collections: list[dict] = []
    glob = {"page": 0, "size": 0, "count": 0, "id": 0}
    stack: list[dict] = []
    local: dict = {"usages": [], "min": None, "max": None}
    depth, i = 0, 0
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:  # long item: skip
            i += 3 + (desc[i + 1] if i + 1 < len(desc) else 0)
            continue
        size = (0, 1, 2, 4)[b & 3]
        kind, tag = (b >> 2) & 3, b >> 4
        raw = desc[i + 1:i + 1 + size]
        value = int.from_bytes(raw, "little") if raw else 0
        i += 1 + size
        if kind == 1:  # global
            if tag == 0:
                glob["page"] = value
            elif tag == 7:
                glob["size"] = value
            elif tag == 8:
                glob["id"] = value
            elif tag == 9:
                glob["count"] = value
            elif tag == 10:
                stack.append(dict(glob))
            elif tag == 11 and stack:
                glob = stack.pop()
        elif kind == 2:  # local; 4-byte usages carry their own page in the high word
            if tag == 0:
                local["usages"].append(value)
            elif tag == 1:
                local["min"] = value
            elif tag == 2:
                local["max"] = value
        elif kind == 0:
            if tag == 0xA:  # collection
                if depth == 0:
                    page, usage = _split(local["usages"][0] if local["usages"] else 0, glob["page"])
                    collections.append({"usage_page": page, "usage": usage, "name": name(page, usage),
                                        "reports": {}})
                depth += 1
            elif tag == 0xC:
                depth = max(0, depth - 1)
            elif tag in _MAIN and collections and not value & 1:  # skip constant (padding) fields
                page, usages, rng = glob["page"], [], False
                if local["usages"]:
                    split = [_split(u, glob["page"]) for u in local["usages"]]
                    page, usages = split[0][0], [u for _, u in split]
                elif local["min"] is not None and local["max"] is not None:
                    usages, rng = [local["min"], local["max"]], True
                field = {"report_id": glob["id"], "usage_page": page, "usages": usages, "bits": glob["size"],
                         "count": glob["count"]}
                if rng:
                    field["range"] = True
                collections[-1]["reports"].setdefault(_MAIN[tag], []).append(field)
            local = {"usages": [], "min": None, "max": None}
    return collections


def _split(usage: int, page: int) -> tuple[int, int]:
    return (usage >> 16, usage & 0xFFFF) if usage > 0xFFFF else (page, usage)
