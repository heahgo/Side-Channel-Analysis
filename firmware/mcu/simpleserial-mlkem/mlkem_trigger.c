#include "mlkem_trigger.h"

volatile uint8_t mlkem_trig_armed;

#ifdef MLKEM_TRIGGER_BASEMUL
#include "hal.h"
#include "mlkem_api.h"
#include "poly.h"

#define TRIGGER_FIRST_CALL(call)        \
    do {                                \
        if (mlkem_trig_armed) {         \
            mlkem_trig_armed = 0;       \
            trigger_high();             \
            call;                       \
            trigger_low();              \
        } else {                        \
            call;                       \
        }                               \
    } while (0)

#if defined(MLKEM_IMPL_M4FSTACK)
/* indcpa_dec: poly_frombytes_mul(&mp, &mp, sk)  -> sk[0] * NTT(u[0]) */
void __real_poly_frombytes_mul(poly *r, const poly *b, const unsigned char *a);
void __wrap_poly_frombytes_mul(poly *r, const poly *b, const unsigned char *a)
{
    TRIGGER_FIRST_CALL(__real_poly_frombytes_mul(r, b, a));
}

#elif defined(MLKEM_IMPL_M4FSPEED)
/* indcpa_dec: poly_frombytes_mul_16_32(r_tmp, &mp, sk) -> sk[0] * NTT(u[0]) */
void __real_poly_frombytes_mul_16_32(int32_t *r_tmp, const poly *b, const unsigned char *a);
void __wrap_poly_frombytes_mul_16_32(int32_t *r_tmp, const poly *b, const unsigned char *a)
{
    TRIGGER_FIRST_CALL(__real_poly_frombytes_mul_16_32(r_tmp, b, a));
}

#elif defined(MLKEM_IMPL_CLEAN)
/* indcpa_dec -> polyvec_basemul_acc_montgomery -> poly_basemul_montgomery(r, &skpv[0], &b[0]) */
#define REAL_FN MLK_CAT(__real_, MLK_CAT(MLKEM_NAMESPACE, poly_basemul_montgomery))
#define WRAP_FN MLK_CAT(__wrap_, MLK_CAT(MLKEM_NAMESPACE, poly_basemul_montgomery))
void REAL_FN(poly *r, const poly *a, const poly *b);
void WRAP_FN(poly *r, const poly *a, const poly *b)
{
    TRIGGER_FIRST_CALL(REAL_FN(r, a, b));
}
#endif
#endif /* MLKEM_TRIGGER_BASEMUL */
