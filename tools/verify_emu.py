#!/usr/bin/env python3
"""Check a built simpleserial-mlkem firmware ELF in the Unicorn Cortex-M4 emulator
against kyber-py (FIPS 203). No board needed.

Default mode calls crypto_kem_dec directly and reports the trigger windows
(0, 1 or 2 high pulses: A = secret-key basemul, B = poly_tomsg).

    python tools/verify_emu.py firmware/mcu/simpleserial-mlkem/simpleserial-mlkem768-clean-CW308_STM32F4.elf -n 10

--protocol runs the firmware's own main() (SimpleSerial 2.1 loop) with getch/putch
wired to ChipWhisperer's host class SimpleSerial2, and goes through the same calls
as jupyter/mlkem-test.ipynb: 'i' info, 's'/'c' chunks (scmd = chunk index), 'd',
error acks for bad chunks, and the trigger pulse count against the 'i' trigger bits.
Needs the chipwhisperer package (pip install, or --cw <chipwhisperer>/software).

    python tools/verify_emu.py <elf> --protocol --cw ../software -n 5
"""
import argparse
import queue
import re
import sys
import threading
import time
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M4, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)
from kyber_py.ml_kem import ML_KEM_512, ML_KEM_768, ML_KEM_1024

KEMS = {512: ML_KEM_512, 768: ML_KEM_768, 1024: ML_KEM_1024}
FLASH, RAM = 0x08000000, 0x20000000
SK, CT, SS = RAM + 0x2C000, RAM + 0x2E000, RAM + 0x2F800
STACK_TOP = RAM + 0x2B000
GPIO_LO, GPIO_HI = 0x40020000, 0x40022C00      # STM32F4 GPIOA..GPIOK (trigger pin)
STOP = FLASH + 0xFFFF0


def load_elf(elf_path):
    """Map flash/RAM/peripherals and load the ELF; returns (Uc, symbol table)."""
    with open(elf_path, "rb") as f:
        elf = ELFFile(f)
        syms = {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()}
        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
        mu.mem_map(FLASH, 0x100000)
        mu.mem_map(RAM, 0x30000)
        mu.mem_map(0x40000000, 0x80000)   # peripherals
        for seg in elf.iter_segments():
            if seg["p_type"] == "PT_LOAD" and seg["p_filesz"]:
                mu.mem_write(seg["p_vaddr"], seg.data())
    return mu, syms


class Firmware:
    """Calls crypto_kem_dec directly (no SimpleSerial)."""

    def __init__(self, elf_path):
        self.mu, self.syms = load_elf(elf_path)
        dec = [n for n in self.syms if n.endswith("crypto_kem_dec") and not n.startswith("__")]
        assert len(dec) == 1, dec
        self.entry = self.syms[dec[0]]
        self.gpio_writes, self.icount = [], 0
        self.mu.hook_add(UC_HOOK_MEM_WRITE, self._on_write, begin=GPIO_LO, end=GPIO_HI)
        self.mu.hook_add(UC_HOOK_CODE, self._on_code)

    def _on_write(self, mu, access, addr, size, value, user):
        self.gpio_writes.append(self.icount)

    def _on_code(self, mu, addr, size, user):
        self.icount += 1

    def decaps(self, dk, ct):
        mu = self.mu
        mu.mem_write(SK, dk); mu.mem_write(CT, ct); mu.mem_write(SS, bytes(32))
        self.gpio_writes, self.icount = [], 0
        mu.reg_write(UC_ARM_REG_SP, STACK_TOP)
        mu.reg_write(UC_ARM_REG_R0, SS); mu.reg_write(UC_ARM_REG_R1, CT); mu.reg_write(UC_ARM_REG_R2, SK)
        mu.reg_write(UC_ARM_REG_LR, STOP | 1)
        mu.emu_start(self.entry | 1, STOP)
        return bytes(mu.mem_read(SS, 32))


def run_direct(args, kem, params):
    fw = Firmware(args.elf)
    ok, trig_ok = 0, 0
    for i in range(args.n):
        ek, dk = kem.keygen()
        key, ct = kem.encaps(ek)
        tampered = i % 3 == 2
        if tampered:
            ct = bytes([ct[0] ^ 1]) + ct[1:]
            key = kem.decaps(dk, ct)  # implicit rejection value
        good = fw.decaps(dk, ct) == key
        ok += good
        w = fw.gpio_writes
        t = len(w) in (0, 2, 4)
        if len(w) == 4:
            note = (f"2 trigger windows: A={w[1] - w[0]} instr, B={w[3] - w[2]} instr "
                    f"(gap={w[2] - w[1]} instr) of {fw.icount}")
        elif len(w) == 2:
            note = f"trigger window {w[1] - w[0]} instr of {fw.icount}"
        elif not w:
            note = f"{fw.icount} instr, no trigger"
        else:
            note = f"{fw.icount} instr, trigger writes={len(w)} (expected 0, 2 or 4)"
        trig_ok += t
        print(f"[{i}] ML-KEM-{params} {'tampered ' if tampered else ''}{'MATCH' if good else 'MISMATCH'}  {note}")
    print(f"{ok}/{args.n} match, trigger {trig_ok}/{args.n} ok")
    return ok == args.n and trig_ok == args.n


# ---------------------------------------------------------------------------
# --protocol: firmware main() + ChipWhisperer SimpleSerial2 host class

class UartFirmware:
    """Runs main() in a thread; getch()/putch() are replaced by byte queues.
    platform_init/init_uart/trigger_setup are skipped (they poll clock/UART flags)."""

    def __init__(self, elf_path):
        self.mu, self.syms = load_elf(elf_path)
        try:
            self.mu.mem_map(0xE0000000, 0x100000)   # SCB (main() sets CPACR for the FPU)
        except Exception:
            pass
        self.rx, self.tx = queue.Queue(), queue.Queue()
        self.gpio_writes = 0
        self._stop = False
        for name in ("platform_init", "init_uart", "trigger_setup"):
            self._hook(name, lambda mu: None)
        self._hook("getch", self._getch)
        self._hook("putch", lambda mu: self.tx.put(mu.reg_read(UC_ARM_REG_R0) & 0xFF))
        self.mu.hook_add(UC_HOOK_MEM_WRITE, self._on_gpio, begin=GPIO_LO, end=GPIO_HI)

    def _hook(self, name, fn):
        addr = self.syms[name] & ~1

        def cb(mu, a, size, user):
            fn(mu)
            if not self._stop:
                mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))   # return to caller
        self.mu.hook_add(UC_HOOK_CODE, cb, begin=addr, end=addr)

    def _getch(self, mu):
        while True:
            try:
                b = self.rx.get(timeout=0.1)
                break
            except queue.Empty:
                if self._stop:
                    mu.emu_stop()
                    return
        mu.reg_write(UC_ARM_REG_R0, b)

    def _on_gpio(self, mu, access, addr, size, value, user):
        self.gpio_writes += 1

    def start(self):
        def run():
            self.mu.reg_write(UC_ARM_REG_SP, self.syms["_estack"])
            self.mu.emu_start(self.syms["main"] | 1, STOP)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop = True
        self.thread.join(timeout=5)


class EmuSerial:
    """The 'ser' object ChipWhisperer's SimpleSerial2 talks to, backed by the emulator."""

    def __init__(self, fw):
        self.fw, self.buf = fw, bytearray()

    def _drain(self):
        while True:
            try:
                self.buf.append(self.fw.tx.get_nowait())
            except queue.Empty:
                return

    def write(self, data, timeout=0):
        for b in bytes(data):
            self.fw.rx.put(b)

    def read(self, num, timeout=250):
        deadline = time.time() + timeout / 1000
        while len(self.buf) < num:
            left = deadline - time.time()
            if left <= 0:
                break
            try:
                self.buf.append(self.fw.tx.get(timeout=left))
            except queue.Empty:
                break
        out = bytes(self.buf[:num]); del self.buf[:num]
        return out.decode("latin-1")

    def inWaiting(self):
        self._drain()
        return len(self.buf)

    def flush(self):
        self._drain()
        self.buf.clear()

    def close(self):
        pass


def run_protocol(args, kem, params):
    if args.cw:
        sys.path.insert(0, args.cw)
    import logging
    from chipwhisperer.capture.targets.SimpleSerial2 import SimpleSerial2
    logging.getLogger("ChipWhisperer Target").setLevel(logging.CRITICAL)

    fw = UartFirmware(args.elf)
    fw.start()
    target = SimpleSerial2()
    target.ser = EmuSerial(fw)
    target._flush_on_err = False
    T = args.timeout          # emulator speed != board speed: generous timeouts
    failures = []

    def check(cond, msg):
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            failures.append(msg)

    def ack():
        r = target.simpleserial_wait_ack(timeout=T)
        return None if r is None else r[0]

    # 'i' -> params, implementation, trigger bits, chunk size  (same as the notebook)
    target.simpleserial_write("i", bytearray())
    info = target.simpleserial_read("r", 4, timeout=T)
    check(info is not None, f"'i' answered: {None if info is None else list(info)}")
    if info is None:
        fw.stop()
        return False
    chunk, trig_bits = info[3], info[2]
    expect_writes = 2 * bin(trig_bits).count("1")
    check(info[0] * 256 == params, f"params {info[0] * 256}")
    print(f"  info: impl={info[1]} trigger=0b{trig_bits:02b} chunk={chunk}")

    def send_chunks(cmd, data):
        codes = []
        for i in range(0, len(data), chunk):
            target.send_cmd(cmd, i // chunk, data[i:i + chunk])   # scmd = chunk index
            codes.append(ack())
        return codes

    def decaps(ct):
        codes = send_chunks("c", ct)
        fw.gpio_writes = 0
        target.simpleserial_write("d", bytearray())
        ss = target.simpleserial_read("r", 32, timeout=T)
        return codes, None if ss is None else bytes(ss)

    ek, dk = kem.keygen()
    codes = send_chunks("s", dk)
    check(codes == [0] * len(codes), f"dk {len(dk)} B in {len(codes)} chunks, acks {set(codes)}")

    for i in range(args.n):
        key, ct = kem.encaps(ek)
        tampered = i % 3 == 2
        if tampered:
            ct = bytes([ct[0] ^ 1]) + ct[1:]
            key = kem.decaps(dk, ct)
        codes, ss = decaps(ct)
        check(codes == [0] * len(codes) and ss == key and fw.gpio_writes == expect_writes,
              f"[{i}] {'tampered ' if tampered else ''}decaps: ct acks {set(codes)}, "
              f"{'MATCH' if ss == key else 'MISMATCH'}, trigger writes {fw.gpio_writes} (expect {expect_writes})")

    # bad chunks must be refused with the firmware's error codes
    target.send_cmd("s", 200, bytes(chunk))
    check(ack() == 0x10, "chunk index out of range -> error 0x10")
    last = (len(ct) - 1) // chunk
    target.send_cmd("c", last, bytes(chunk))
    check(ack() == 0x11 or len(ct) % chunk == 0, "last chunk too long -> error 0x11")
    target.send_cmd("c", 0, bytes(chunk + 1))
    check(ack() == 0x11, f"piece longer than {chunk} -> error 0x11")

    # after the errors the key is still in place
    key, ct = kem.encaps(ek)
    codes, ss = decaps(ct)
    check(ss == key, "decaps still OK after error packets")

    # 'x' clears the buffers -> decaps no longer matches
    target.simpleserial_write("x", bytearray())
    check(ack() == 0, "'x' acked")
    codes, ss = decaps(ct)
    check(ss is not None and ss != key, "after 'x' the key is gone (no match)")

    fw.stop()
    print(f"{'PASS' if not failures else 'FAIL'}: {len(failures)} failure(s)")
    return not failures


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elf")
    ap.add_argument("-p", "--params", type=int, choices=KEMS, help="ML-KEM parameter set (default: from file name)")
    ap.add_argument("-n", type=int, default=5, help="number of trials (every 3rd uses a tampered ciphertext)")
    ap.add_argument("--protocol", action="store_true", help="run main() and talk SimpleSerial 2.1 via ChipWhisperer")
    ap.add_argument("--cw", help="path to <chipwhisperer>/software if chipwhisperer is not installed")
    ap.add_argument("--timeout", type=int, default=60000, help="--protocol read timeout in ms (default 60000)")
    args = ap.parse_args()

    params = args.params
    if params is None:
        m = re.search(r"mlkem(512|768|1024)", args.elf)
        params = int(m.group(1)) if m else 768
    kem = KEMS[params]
    ok = run_protocol(args, kem, params) if args.protocol else run_direct(args, kem, params)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
