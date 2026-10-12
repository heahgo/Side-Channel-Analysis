#include "hal.h"
#include "simpleserial.h"
#include "mlkem_api.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#if SS_VER != SS_VER_2_1
#error "simpleserial-mlkem needs SS_VER_2_1 (scmd = chunk index, variable length)"
#endif

/* SimpleSerial 2.1 frame: [cmd, scmd, len, data(len), crc] + COBS, at most 255 bytes,
 * so one packet carries at most 249 data bytes. dk/ct are sent in CHUNK-byte pieces:
 * scmd = chunk index, len = piece length (the last piece may be shorter). */
#define CHUNK 240

/* error codes returned in the 'e' (ack) packet; 0x00..0x05 are used by simpleserial.c */
#define ERR_CHUNK_INDEX 0x10    /* scmd * CHUNK beyond the buffer */
#define ERR_CHUNK_LEN   0x11    /* len > CHUNK or piece runs past the end of the buffer */

static uint8_t sk[CRYPTO_SECRETKEYBYTES];
static uint8_t ct[CRYPTO_CIPHERTEXTBYTES];
static uint8_t ss[CRYPTO_BYTES];

/* Only used by keypair/enc; decapsulation never calls it. */
int randombytes(uint8_t *out, size_t n)
{
    static uint32_t x = 0x12345678u;
    while (n--) {
        x ^= x << 13; x ^= x >> 17; x ^= x << 5;
        *out++ = (uint8_t)x;
    }
    return 0;
}

/* copy piece number 'idx' (len bytes) to dst + idx * CHUNK */
static uint8_t load_chunk(uint8_t *dst, size_t dst_len, uint8_t idx, uint8_t len, const uint8_t *buf)
{
    size_t off = (size_t)idx * CHUNK;
    if (off >= dst_len) return ERR_CHUNK_INDEX;
    if (len > CHUNK || off + len > dst_len) return ERR_CHUNK_LEN;
    memcpy(dst + off, buf, len);
    return 0x00;
}

static uint8_t set_sk(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t *buf)
{
    return load_chunk(sk, sizeof sk, scmd, len, buf);
}

static uint8_t set_ct(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t *buf)
{
    return load_chunk(ct, sizeof ct, scmd, len, buf);
}

static uint8_t do_dec(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t *buf)
{
    /* trigger: #ifdef MLKEM_TRIGGER_A / MLKEM_TRIGGER_B inside the pqm4 sources */
    crypto_kem_dec(ss, ct, sk);
    simpleserial_put('r', CRYPTO_BYTES, ss);
    return 0x00;
}

static uint8_t reset(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t *buf)
{
    memset(sk, 0, sizeof sk);
    memset(ct, 0, sizeof ct);
    return 0x00;
}

/* 'i': firmware info -> 'r' 4 bytes: params/256, implementation, trigger (bit0=A bit1=B), chunk size */
static uint8_t info(uint8_t cmd, uint8_t scmd, uint8_t len, uint8_t *buf)
{
    uint8_t out[4];
    out[0] = MLKEM_PARAMS / 256;            /* 2, 3, 4 */
#if defined(MLKEM_IMPL_M4FSTACK)
    out[1] = 1;
#elif defined(MLKEM_IMPL_M4FSPEED)
    out[1] = 2;
#else
    out[1] = 3;                             /* clean */
#endif
    out[2] = 0;                             /* bit0: trigger A (basemul), bit1: trigger B (poly_tomsg) */
#ifdef MLKEM_TRIGGER_A
    out[2] |= 0x01;
#endif
#ifdef MLKEM_TRIGGER_B
    out[2] |= 0x02;
#endif
    out[3] = CHUNK;
    simpleserial_put('r', 4, out);
    return 0x00;
}

int main(void)
{
    platform_init();
    /* Enable CP10/CP11: the M4 asm uses FPU registers as spill space. */
    *(volatile uint32_t *)0xE000ED88u |= (0xFu << 20);
    __asm volatile("dsb\n\tisb");
    init_uart();                            /* SS_VER_2_1: 230400 baud (CW STM32F4 HAL) */
    trigger_setup();

    simpleserial_init();
    /* SS 2.1 does not enforce the registered length; the handlers check it */
    simpleserial_addcmd('s', CHUNK, set_sk);
    simpleserial_addcmd('c', CHUNK, set_ct);
    simpleserial_addcmd('d', 0, do_dec);
    simpleserial_addcmd('x', 0, reset);
    simpleserial_addcmd('i', 0, info);

    while (1)
        simpleserial_get();
}
