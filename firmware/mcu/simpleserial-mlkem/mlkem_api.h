#ifndef MLKEM_API_H
#define MLKEM_API_H

#include "api.h"

/* PQClean 'clean' prefixes every symbol (PQCLEAN_MLKEM768_CLEAN_...);
 * map them to the plain NIST names used by the pqm4 m4f implementations. */
#define MLK_CAT_(a, b) a##b
#define MLK_CAT(a, b)  MLK_CAT_(a, b)

#ifdef MLKEM_NAMESPACE
#define CRYPTO_SECRETKEYBYTES  MLK_CAT(MLKEM_NAMESPACE, CRYPTO_SECRETKEYBYTES)
#define CRYPTO_PUBLICKEYBYTES  MLK_CAT(MLKEM_NAMESPACE, CRYPTO_PUBLICKEYBYTES)
#define CRYPTO_CIPHERTEXTBYTES MLK_CAT(MLKEM_NAMESPACE, CRYPTO_CIPHERTEXTBYTES)
#define CRYPTO_BYTES           MLK_CAT(MLKEM_NAMESPACE, CRYPTO_BYTES)
#define crypto_kem_dec         MLK_CAT(MLKEM_NAMESPACE, crypto_kem_dec)
#endif

#endif
