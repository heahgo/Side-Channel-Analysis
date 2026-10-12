# ML-KEM SimpleSerial firmware for ChipWhisperer (pqm4 implementations)
#
#   make PLATFORM=CW308_STM32F4                                   # ML-KEM-768, m4fstack
#   make PLATFORM=CW308_STM32F4 PARAMS=512 IMPL=clean TRIGGER_A=1 TRIGGER_B=0
#
#   PARAMS    : 512 | 768 | 1024                    (default 768)
#   IMPL      : m4fstack | m4fspeed | clean         (default m4fstack)
#   TRIGGER_A : 1 -> trigger_high/low around the secret-key basemul
#                    (indcpa_dec, polyvec_basemul_acc_montgomery)   (default 1)
#   TRIGGER_B : 1 -> trigger_high/low around poly_tomsg             (default 1)
#               0 -> that trigger is compiled out
#   TRIGGER   : shorthand, overrides both TRIGGER_A and TRIGGER_B when set
#               explicitly on the command line (0 or 1)
#
#   Only IMPL=clean has the #ifdef MLKEM_TRIGGER_A / MLKEM_TRIGGER_B sites
#   (both in indcpa.c, indcpa_dec). m4fstack/m4fspeed have no trigger: setting
#   TRIGGER_A/TRIGGER_B=1 there just defines the macro with no effect (warning).
#
#   Host protocol: SimpleSerial 2.1 only (SS_VER_2_1, 230400 baud); dk/ct are
#   sent in 240-byte chunks with scmd = chunk index (see simpleserial-mlkem.c).
#
# Output: simpleserial-mlkem<PARAMS>-<IMPL>-<PLATFORM>.hex

PARAMS    ?= 768
IMPL      ?= m4fstack
TRIGGER_A ?= 1
TRIGGER_B ?= 1
ifdef TRIGGER
  TRIGGER_A := $(TRIGGER)
  TRIGGER_B := $(TRIGGER)
endif

ifeq ($(filter $(PARAMS),512 768 1024),)
  $(error PARAMS must be 512, 768 or 1024 (got '$(PARAMS)'))
endif
ifeq ($(filter $(IMPL),m4fstack m4fspeed clean),)
  $(error IMPL must be m4fstack, m4fspeed or clean (got '$(IMPL)'))
endif
ifeq ($(filter $(TRIGGER_A),0 1),)
  $(error TRIGGER_A must be 0 or 1 (got '$(TRIGGER_A)'))
endif
ifeq ($(filter $(TRIGGER_B),0 1),)
  $(error TRIGGER_B must be 0 or 1 (got '$(TRIGGER_B)'))
endif

# ---------------------------------------------------------------------------
# ChipWhisperer build system: firmware/mcu of this repository (same layout as
# chipwhisperer/firmware/mcu). The STM32F4 HAL is the hal/chipwhisperer-fw-extra submodule.
FIRMWAREPATH = ../.
ifeq ($(PLATFORM),CW308_STM32F4)
  ifeq ($(wildcard $(FIRMWAREPATH)/hal/chipwhisperer-fw-extra/stm32f4/Makefile.stm32f4),)
    $(error STM32F4 HAL missing: run 'git submodule update --init --depth 1' in the repository root)
  endif
endif

# ---------------------------------------------------------------------------
# pqm4 sources: firmware/mcu/pqm4, same layout as the pqm4 repository and
# byte-identical to it (see tools/import_pqm4.sh)
PQM4 = $(FIRMWAREPATH)/pqm4
ifeq ($(IMPL),clean)
  IMPL_DIR = $(PQM4)/mupq/pqclean/crypto_kem/ml-kem-$(PARAMS)/clean
else
  IMPL_DIR = $(PQM4)/crypto_kem/ml-kem-$(PARAMS)/$(IMPL)
endif

TARGET = simpleserial-mlkem$(PARAMS)-$(IMPL)

SRC  += simpleserial-mlkem.c
SRC  += $(notdir $(wildcard $(IMPL_DIR)/*.c)) fips202.c
ASRC += $(notdir $(wildcard $(IMPL_DIR)/*.S)) keccakf1600.S
# Bare file names + VPATH: CW's 'make clean' removes $(SRC:.c=.i), which must not
# reach pqm4's matacc.i.
VPATH        += :$(IMPL_DIR):$(PQM4)/common:$(PQM4)/mupq/common
EXTRAINCDIRS += $(IMPL_DIR) $(PQM4)/mupq/common

ifeq ($(IMPL),m4fstack)
  CDEFS += -DMLKEM_IMPL_M4FSTACK
else ifeq ($(IMPL),m4fspeed)
  CDEFS += -DMLKEM_IMPL_M4FSPEED
else
  CDEFS += -DMLKEM_IMPL_CLEAN -DMLKEM_NAMESPACE=PQCLEAN_MLKEM$(PARAMS)_CLEAN_
endif
CDEFS += -DMLKEM_PARAMS=$(PARAMS)
ifeq ($(TRIGGER_A),1)
  CDEFS += -DMLKEM_TRIGGER_A
  ifeq ($(shell grep -l MLKEM_TRIGGER_A $(IMPL_DIR)/*.c),)
    $(warning TRIGGER_A=1 but no '#ifdef MLKEM_TRIGGER_A' in $(IMPL_DIR): firmware has no A trigger)
  endif
endif
ifeq ($(TRIGGER_B),1)
  CDEFS += -DMLKEM_TRIGGER_B
  ifeq ($(shell grep -l MLKEM_TRIGGER_B $(IMPL_DIR)/*.c),)
    $(warning TRIGGER_B=1 but no '#ifdef MLKEM_TRIGGER_B' in $(IMPL_DIR): firmware has no B trigger)
  endif
endif

# pqm4 asm keeps values in FPU registers (vmov); CW builds STM32F4 soft-float,
# so only the assembler needs the FPU. CP10/CP11 are enabled in main().
ASFLAGS += -mfpu=fpv4-sp-d16

SS_VER ?= SS_VER_2_1
ifneq ($(SS_VER),SS_VER_2_1)
  $(error simpleserial-mlkem uses SimpleSerial 2.1 (scmd = chunk index); got SS_VER=$(SS_VER))
endif
# ML-KEM brings its own code: no CW crypto library
CRYPTO_TARGET = NONE
EXTRA_OPTS = NO_EXTRA_OPTS
CFLAGS += -D$(EXTRA_OPTS)

include $(FIRMWAREPATH)/Makefile.inc
