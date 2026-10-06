#ifndef MLKEM_TRIGGER_H
#define MLKEM_TRIGGER_H

#include <stdint.h>

/* Set to 1 right before crypto_kem_dec; the wrapped basemul raises the
 * trigger on its first call (the first secret-key basemul of indcpa_dec)
 * and clears the flag, so later basemuls (re-encryption) are not marked. */
extern volatile uint8_t mlkem_trig_armed;

#endif
