"""Display identity from EDID, in one schema for both OSes.

The EDID is the panel's own description of itself (manufacturer, model, native timing,
refresh range, HDR and DisplayID extensions). On Linux the eDP connector's EDID is what DRM
binds panel quirks and backlight handling to, so the raw bytes are saved next to the snapshot
(display/<id>.edid) and parsed here. The serial number fields are not recorded.
"""

from __future__ import annotations

import struct

EXTENSION_TAGS = {0x02: "CTA-861", 0x10: "VTB", 0x40: "DI", 0x50: "LS", 0x60: "DPVL", 0x70: "DisplayID",
                  0xF0: "block map"}


def parse_edid(edid: bytes) -> dict:
    if len(edid) < 128 or edid[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return {"error": "not an EDID"}
    mfg = struct.unpack(">H", edid[8:10])[0]
    pnp = "".join(chr(((mfg >> s) & 0x1F) + 64) for s in (10, 5, 0))
    out = {"manufacturer": pnp, "product_code": f"0x{struct.unpack('<H', edid[10:12])[0]:04x}",
           "year": 1990 + edid[17], "week": edid[16], "version": f"{edid[18]}.{edid[19]}",
           "digital": bool(edid[20] & 0x80), "size_cm": [edid[21], edid[22]],
           "bits_per_color": {1: 6, 2: 8, 3: 10, 4: 12, 5: 14, 6: 16}.get((edid[20] >> 4) & 7) if edid[20] & 0x80 else None}
    for off in range(54, 126, 18):
        d = edid[off:off + 18]
        if d[0] or d[1]:
            if "native" not in out:
                out["native"] = _dtd(d)
            continue
        tag, text = d[3], d[5:18].split(b"\n")[0].decode("ascii", "replace").strip()
        if tag == 0xFC:
            out["name"] = text
        elif tag == 0xFE and text.isprintable():  # some panels put binary vendor data here
            out.setdefault("text", []).append(text)
        elif tag == 0xFD:
            out["range"] = {"v_min_hz": d[5], "v_max_hz": d[6], "h_min_khz": d[7], "h_max_khz": d[8]}
    out["extensions"] = []
    for n in range(1, min(edid[126], len(edid) // 128 - 1) + 1):
        out["extensions"].append(_extension(edid[128 * n:128 * (n + 1)]))
    return out


def _dtd(d: bytes) -> dict:
    clock_khz = struct.unpack("<H", d[0:2])[0] * 10
    h_active, h_blank = d[2] | (d[4] & 0xF0) << 4, d[3] | (d[4] & 0x0F) << 8
    v_active, v_blank = d[5] | (d[7] & 0xF0) << 4, d[6] | (d[7] & 0x0F) << 8
    total = (h_active + h_blank) * (v_active + v_blank)
    return {"width": h_active, "height": v_active, "pixel_clock_mhz": clock_khz / 1000,
            "refresh_hz": round(clock_khz * 1000 / total, 2) if total else None,
            "size_mm": [d[12] | (d[14] & 0xF0) << 4, d[13] | (d[14] & 0x0F) << 8]}


def _extension(block: bytes) -> dict:
    tag = block[0]
    ext = {"tag": EXTENSION_TAGS.get(tag, f"0x{tag:02x}")}
    if tag == 0x02 and len(block) > 4:  # CTA-861: walk the data block collection
        end, i, blocks = block[2], 4, []
        while 4 <= i < end and i < len(block):
            btype, blen = block[i] >> 5, block[i] & 0x1F
            body = block[i + 1:i + 1 + blen]
            if btype == 7 and body:  # extended tag
                name = {0x06: "HDR static metadata", 0x07: "HDR dynamic metadata", 0x05: "colorimetry",
                        0x00: "video capability"}.get(body[0], f"ext 0x{body[0]:02x}")
                blocks.append(name)
                if body[0] == 0x06 and len(body) > 2:
                    eotf = body[1]
                    ext["hdr_eotf"] = [n for bit, n in ((0, "SDR"), (1, "HDR gamma"), (2, "PQ (HDR10)"), (3, "HLG"))
                                       if eotf & (1 << bit)]
                    if len(body) > 3:
                        ext["hdr_max_luminance_cd_m2"] = round(50 * 2 ** (body[3] / 32))
            else:
                blocks.append({1: "audio", 2: "video", 3: "vendor", 4: "speaker"}.get(btype, f"type {btype}"))
            i += 1 + blen
        ext["blocks"] = blocks
    elif tag == 0x70 and len(block) > 5:  # DisplayID: section of data blocks
        version, length = block[1], block[2]
        i, blocks = 5, []
        while i + 3 <= min(5 + length, len(block) - 1):
            btag, blen = block[i], block[i + 2]
            if btag == 0 and blen == 0:
                break
            blocks.append({0x20: "product id", 0x21: "display params", 0x22: "type VII timing",
                           0x25: "dynamic video timing range", 0x26: "interface features",
                           0x2B: "adaptive sync", 0x81: "CTA DisplayID", 0x7E: "vendor"}.get(btag, f"0x{btag:02x}"))
            if btag == 0x22 and blen >= 20:  # type VII detailed timing: first one is the native mode
                t = block[i + 3:i + 3 + 20]
                clock_khz = int.from_bytes(t[0:3], "little") + 1
                h, hb = struct.unpack_from("<HH", t, 4)
                v, vb = struct.unpack_from("<HH", t, 12)
                h, hb, v, vb = h + 1, hb + 1, v + 1, vb + 1
                ext.setdefault("timings", []).append(
                    {"width": h, "height": v, "refresh_hz": round(clock_khz * 1000 / ((h + hb) * (v + vb)), 2)})
            i += 3 + blen
        ext.update(version=f"{version >> 4}.{version & 0xF}", blocks=blocks)
    return ext


def summary(d: dict) -> str:
    e = d.get("edid") or {}
    native = e.get("native") or {}
    timings = [t for x in e.get("extensions", []) for t in x.get("timings", [])]
    best = max([native, *timings], key=lambda t: (t.get("width", 0), t.get("refresh_hz") or 0), default={})
    hdr = next((x["hdr_eotf"] for x in e.get("extensions", []) if x.get("hdr_eotf")), None)
    parts = [f"{e.get('manufacturer', '?')} {e.get('product_code', '')} {e.get('name') or ' '.join(e.get('text', []))}".strip()]
    if best:
        parts.append(f"{best.get('width')}x{best.get('height')}@{best.get('refresh_hz')}Hz")
    if e.get("range"):
        parts.append(f"{e['range']['v_min_hz']}-{e['range']['v_max_hz']} Hz range")
    if hdr:
        parts.append("HDR " + "/".join(hdr))
    return ", ".join(parts)
