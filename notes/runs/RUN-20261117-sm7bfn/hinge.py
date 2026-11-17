"""Hinge angle per posture from an n1x-sensors summary: lid accelerometer (200073.36) and
base accelerometer (200073.39) in the y-z plane, hinge along x.
hinge = (180 + atan2(lid_y, lid_z) - atan2(base_y, base_z)) mod 360."""
import math, re, sys
txt = open(sys.argv[1]).read()
dev = dict((re.search(r'parent=HID-SENSOR-200073\.(\d+)', l).group(1), re.search(r'dev=(\S+)', l).group(1))
           for l in txt.splitlines() if 'parent=HID-SENSOR-200073' in l)
lid, base = dev['36'], dev['39']
vec = lambda d, l: [float(v) for v in re.search(re.escape(d) + r'=\[([^\]]+)\]', l).group(1).split(',')]
for block in re.split(r'^== ', txt, flags=re.M)[1:]:
    rows = [l for l in block.splitlines() if l.strip().startswith('t=')]
    s = [sum(vec(lid, l)[i] for l in rows) / len(rows) for i in range(3)]
    b = [sum(vec(base, l)[i] for l in rows) / len(rows) for i in range(3)]
    h = (180 + math.degrees(math.atan2(s[1], s[2]) - math.atan2(b[1], b[2]))) % 360
    print(f"{block.split()[0]:8} hinge={h:6.1f}  |lid|={math.hypot(*s):5.2f}  |base|={math.hypot(*b):5.2f}")
