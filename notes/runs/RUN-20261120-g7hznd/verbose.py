# gdb: run nvidia-powerd 2.0 (driver 620.70.06) with its INFO logging on. INFO lines are
# guarded by a global verbosity (file offset 0x328b88, 64-bit) that must exceed 3, and then
# go through the logger at 0x130180 whose sink passes ERROR (level 2) only. Set the verbosity
# to 10 at the program's entry, relabel every logger call as ERROR, and report any later
# write to the verbosity.
import gdb
ENTRY, VERBOSITY, LOGGER = 0x5c394, 0x328b88, 0x130180
gdb.execute("starti", to_string=True)
exe = gdb.current_progspace().filename
base = None
for line in gdb.execute("info proc mappings", to_string=True).splitlines():
    f = line.split()
    if len(f) >= 5 and f[-1] == exe and base is None:
        base = int(f[0], 16) - int(f[3], 16)
print(f"powerd base 0x{base:x}", flush=True)
gdb.execute(f"tbreak *0x{base + ENTRY:x}", to_string=True)
gdb.execute("continue", to_string=True)
v = base + VERBOSITY
print(f"verbosity was {int(gdb.parse_and_eval(f'*(long*)0x{v:x}'))}", flush=True)
gdb.execute(f"set *(long*)0x{v:x} = 10")

class Watch(gdb.Breakpoint):
    def stop(self):
        print(f"verbosity written: {int(gdb.parse_and_eval(f'*(long*)0x{v:x}'))} at 0x{gdb.newest_frame().pc() - base:x}", flush=True)
        gdb.execute(f"set *(long*)0x{v:x} = 10")
        return False
Watch(f"*(long*)0x{v:x}", gdb.BP_WATCHPOINT, gdb.WP_WRITE, internal=True)

class Promote(gdb.Breakpoint):
    def stop(self):
        if int(gdb.parse_and_eval("$w0")) in (1, 3, 4, 5):
            gdb.execute("set $w0 = 2")
        return False
Promote(f"*0x{base + LOGGER:x}", internal=True)
gdb.execute("continue")
