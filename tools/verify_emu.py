#!/usr/bin/env python3
"""Run crypto_kem_dec from a built firmware ELF in the Unicorn Cortex-M4 emulator
and compare the shared secret with kyber-py (FIPS 203). No board needed.

For TRIGGER=basemul builds it also checks that the trigger GPIO is raised and
lowered exactly once during decapsulation and reports the window length.

    python tools/verify_emu.py firmware/mcu/simpleserial-mlkem/simpleserial-mlkem768-m4fstack-CW308_STM32F4.elf -n 10
"""
import argparse
import re
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M4, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)
from kyber_py.ml_kem import ML_KEM_512, ML_KEM_768, ML_KEM_1024

KEMS = {512: ML_KEM_512, 768: ML_KEM_768, 1024: ML_KEM_1024}
FLASH, RAM = 0x08000000, 0x20000000
SK, CT, SS = RAM + 0x2C000, RAM + 0x2E000, RAM + 0x2F800
STACK_TOP = RAM + 0x2B000
GPIO_LO, GPIO_HI = 0x40020000, 0x40022C00      # STM32F4 GPIOA..GPIOK (trigger pin)
STOP = FLASH + 0xFFFF0


class Firmware:
    def __init__(self, elf_path):
        with open(elf_path, "rb") as f:
            elf = ELFFile(f)
            self.syms = {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()}
            self.mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
            self.mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
            self.mu.mem_map(FLASH, 0x100000)
            self.mu.mem_map(RAM, 0x30000)
            self.mu.mem_map(0x40000000, 0x80000)   # peripherals
            for seg in elf.iter_segments():
                if seg["p_type"] == "PT_LOAD" and seg["p_filesz"]:
                    self.mu.mem_write(seg["p_vaddr"], seg.data())
        dec = [n for n in self.syms if n.endswith("crypto_kem_dec") and not n.startswith("__")]
        assert len(dec) == 1, dec
        self.entry = self.syms[dec[0]]
        self.basemul = "-basemul" in elf_path
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elf")
    ap.add_argument("-p", "--params", type=int, choices=KEMS, help="ML-KEM parameter set (default: from file name)")
    ap.add_argument("-n", type=int, default=5, help="number of trials (every 3rd uses a tampered ciphertext)")
    args = ap.parse_args()

    params = args.params
    if params is None:
        m = re.search(r"mlkem(512|768|1024)", args.elf)
        params = int(m.group(1)) if m else 768
    kem = KEMS[params]
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
        if fw.basemul:
            t = len(w) == 2
            note = f"trigger window {w[1] - w[0]} instr of {fw.icount}" if t else f"trigger writes={len(w)} (expected 2)"
        else:
            t = len(w) == 0
            note = f"{fw.icount} instr" + ("" if t else f", unexpected GPIO writes={len(w)}")
        trig_ok += t
        print(f"[{i}] ML-KEM-{params} {'tampered ' if tampered else ''}{'MATCH' if good else 'MISMATCH'}  {note}")
    print(f"{ok}/{args.n} match, trigger {trig_ok}/{args.n} ok")
    raise SystemExit(0 if ok == args.n and trig_ok == args.n else 1)


if __name__ == "__main__":
    main()
