#include "hal.h"
#include "simpleserial.h"
#include "mlkem_api.h"
#include "mlkem_trigger.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define CHUNK 128

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

/* buf[0] = chunk index, buf[1..CHUNK] = data (last chunk zero-padded by host) */
static uint8_t load_chunk(uint8_t *dst, size_t dst_len, uint8_t *buf)
{
    size_t off = (size_t)buf[0] * CHUNK;
    if (off >= dst_len) return 0x01;
    size_t n = dst_len - off;
    if (n > CHUNK) n = CHUNK;
    memcpy(dst + off, buf + 1, n);
    return 0x00;
}

static uint8_t set_sk(uint8_t *buf, uint8_t len) { return load_chunk(sk, sizeof sk, buf); }
static uint8_t set_ct(uint8_t *buf, uint8_t len) { return load_chunk(ct, sizeof ct, buf); }

static uint8_t do_dec(uint8_t *buf, uint8_t len)
{
#ifdef MLKEM_TRIGGER_BASEMUL
    mlkem_trig_armed = 1;
    crypto_kem_dec(ss, ct, sk);
    mlkem_trig_armed = 0;
#else
    trigger_high();
    crypto_kem_dec(ss, ct, sk);
    trigger_low();
#endif
    simpleserial_put('r', CRYPTO_BYTES, ss);
    return 0x00;
}

static uint8_t reset(uint8_t *buf, uint8_t len)
{
    memset(sk, 0, sizeof sk);
    memset(ct, 0, sizeof ct);
    return 0x00;
}

/* 'i': firmware info -> 'r' 4 bytes: params/256, implementation, trigger, chunk size */
static uint8_t info(uint8_t *buf, uint8_t len)
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
#ifdef MLKEM_TRIGGER_BASEMUL
    out[2] = 1;
#else
    out[2] = 0;
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
    init_uart();
    trigger_setup();

    simpleserial_init();
    simpleserial_addcmd('s', 1 + CHUNK, set_sk);
    simpleserial_addcmd('c', 1 + CHUNK, set_ct);
    simpleserial_addcmd('d', 0, do_dec);
    simpleserial_addcmd('x', 0, reset);
    simpleserial_addcmd('i', 0, info);

    while (1)
        simpleserial_get();
}
