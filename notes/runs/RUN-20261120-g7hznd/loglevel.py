# gdb: make nvidia-powerd 2.0 (driver 620.70.06) log everything. Its logger, at file offset
# 0x130180, takes the level in w0 (2 = ERROR, 3/4 = WARNING/INFO, 1/5 others) and only ERROR
# passes the sink's filter; relabel the rest as ERROR. The messages keep their own
# "INFO:"/"WARNING!" prefixes.
import gdb
LOGGER = 0x130180
gdb.execute("starti", to_string=True)
exe = gdb.current_progspace().filename
base = None
for line in gdb.execute("info proc mappings", to_string=True).splitlines():
    f = line.split()
    if len(f) >= 5 and f[-1] == exe:
        base = int(f[0], 16) - int(f[3], 16) if base is None else base
print(f"powerd base 0x{base:x}", flush=True)

class Promote(gdb.Breakpoint):
    def stop(self):
        lvl = int(gdb.parse_and_eval("$w0"))
        if lvl in (1, 3, 4, 5):
            gdb.execute("set $w0 = 2")
        return False

Promote(f"*0x{base + LOGGER:x}", internal=True)
gdb.execute("continue")
