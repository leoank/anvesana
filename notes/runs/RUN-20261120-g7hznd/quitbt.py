# gdb: backtrace at nvidia-powerd's shutdown routine (file offset 0x6c6d0) and at every
# pthread_kill/exit, to find the function that decides to quit.
import gdb
gdb.execute("starti", to_string=True)
exe = gdb.current_progspace().filename
base = None
for line in gdb.execute("info proc mappings", to_string=True).splitlines():
    f = line.split()
    if len(f) >= 5 and f[-1] == exe and base is None:
        base = int(f[0], 16) - int(f[3], 16)
print(f"powerd base 0x{base:x}", flush=True)

class Bt(gdb.Breakpoint):
    def stop(self):
        print(f"== {self.location} thread {gdb.selected_thread().num}", flush=True)
        f = gdb.newest_frame(); n = 0
        while f is not None and n < 40:
            pc = f.pc()
            off = pc - base if base <= pc < base + 0x400000 else None
            print(f"  #{n} 0x{pc:x}" + (f"  powerd+0x{off:x}" if off is not None else f"  {f.name() or ''}"), flush=True)
            f = f.older(); n += 1
        return False

Bt(f"*0x{base + 0x6c6d0:x}", internal=False)
Bt("pthread_kill"); Bt("exit"); Bt("_exit")
gdb.execute("continue")
