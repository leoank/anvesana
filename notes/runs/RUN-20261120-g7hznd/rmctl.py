# gdb (aarch64): at each ioctl syscall stop print the RM control's command and status
# (NVOS54: cmd at 0x8, status at 0x1c) or the RM alloc's class and status, and save every
# NV0000_CTRL_CMD_SYSTEM_NVPCF_GET_POWER_MODE_INFO (0x13b) exchange to $NVPCF_DIR. Stops come
# in pairs, syscall entry then exit; the exit shows the answer.
import os, struct
import gdb

OUT = os.environ.get("NVPCF_DIR", ".")
count = 0

def stop(ev):
    global count
    try:
        req = int(gdb.parse_and_eval("$x1")) & 0xffffffff
        arg = int(gdb.parse_and_eval("$x2"))
    except gdb.error:
        return
    inf = gdb.selected_inferior()
    nr = req & 0xff
    if nr == 0x2a and arg:  # NV_ESC_RM_CONTROL
        _, obj, cmd, _, pp, size, status = struct.unpack("<IIIIQII", bytes(inf.read_memory(arg, 0x20)))
        print(f"RMCTL cmd=0x{cmd:08x} size={size} status=0x{status:x} obj=0x{obj:x}", flush=True)
        if cmd == 0x13b and pp:
            count += 1
            par = bytes(inf.read_memory(pp, 896))
            sub = struct.unpack("<I", par[20:24])[0]
            dptr, dsz = struct.unpack("<QI", par[880:892])  # inOutData, inOutDataSize
            open(f"{OUT}/{count:03d}-sub{sub}-params.bin", "wb").write(par)
            if dptr and dsz:
                open(f"{OUT}/{count:03d}-sub{sub}-data.bin", "wb").write(bytes(inf.read_memory(dptr, min(dsz, 4096))))
            print(f"   nvpcf #{count} sub={sub} dataSize={dsz}", flush=True)
        if pp and size and cmd < 0x10000 and cmd >= 0x100:  # NV0000 (system) controls
            print("   params " + bytes(inf.read_memory(pp, min(size, 48))).hex(" ", 4), flush=True)
    elif nr == 0x2b and arg:  # NV_ESC_RM_ALLOC
        m = bytes(inf.read_memory(arg, 0x30))
        _, parent, new, cls = struct.unpack("<IIII", m[:16])
        status = struct.unpack("<I", m[0x28:0x2c])[0]
        print(f"RMALLOC parent=0x{parent:x} new=0x{new:x} class=0x{cls:x} status=0x{status:x}", flush=True)

gdb.events.stop.connect(stop)
