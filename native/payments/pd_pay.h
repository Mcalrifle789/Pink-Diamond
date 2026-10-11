/* Pink Diamond payment core — public C ABI.
 *
 * One shared library, three languages:
 *   pd_sig.c          (C)    SHA-256, HMAC-SHA256, Stripe webhook signatures
 *   pd_money.zig      (Zig)  revenue split, Pink Credits, plan pricing
 *   pd_lifecycle.cpp  (C++)  subscription state machine and auto-renewal
 *
 * Card data never passes through this library or this codebase: cards are
 * collected by Stripe's hosted fields (PCI-DSS SAQ A). This core only does
 * the arithmetic and state decisions on amounts Stripe has already settled.
 * backend/payments_core.py loads it with ctypes and has an identical
 * pure-Python mirror; backend/test_payments.py checks the two agree.
 */
#ifndef PD_PAY_H
#define PD_PAY_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
  #define PD_PAY_API __declspec(dllexport)
#else
  #define PD_PAY_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------- C ---- */

/* out must hold 32 bytes. */
PD_PAY_API void pd_sha256(const uint8_t *data, size_t len, uint8_t *out);
PD_PAY_API void pd_hmac_sha256(const uint8_t *key, size_t key_len,
                               const uint8_t *msg, size_t msg_len, uint8_t *out);

/* Verify a Stripe-Signature header ("t=...,v1=...,v1=...") for `payload`.
 * Returns PD_SIG_OK or one of the PD_SIG_* errors. */
enum {
  PD_SIG_OK = 0,
  PD_SIG_MALFORMED = 1,      /* header missing t= or v1= */
  PD_SIG_MISMATCH = 2,       /* no v1 signature matches */
  PD_SIG_EXPIRED = 3         /* |now - t| > tolerance */
};
PD_PAY_API int pd_stripe_verify(const char *payload, size_t payload_len,
                                const char *header, const char *secret,
                                int64_t now, int64_t tolerance_seconds);

/* -------------------------------------------------------------- Zig ---- */

/* Half of every subscription payment funds the customer's model balance;
 * the odd cent goes to the customer. */
PD_PAY_API int64_t pd_split_customer_cents(int64_t paid_cents);
PD_PAY_API int64_t pd_split_platform_cents(int64_t paid_cents);
/* $1 = 100 Pink Credits, so 1 credit = 1 cent of model spend. */
PD_PAY_API int64_t pd_cents_to_credits(int64_t cents);
/* Plan price for a billing interval: monthly as listed, yearly = 12 months
 * at 20% off, rounded to the cent. interval: 0 = month, 1 = year. */
PD_PAY_API int64_t pd_plan_price_cents(int64_t monthly_cents, int interval);
/* Pay-as-you-go custom amounts: whole or fractional dollars between $5 and
 * $1,000. Returns 1 when acceptable. */
PD_PAY_API int pd_topup_valid(int64_t cents);

/* -------------------------------------------------------------- C++ ---- */

enum {
  PD_SUB_NONE = 0,
  PD_SUB_ACTIVE = 1,
  PD_SUB_PAST_DUE = 2,       /* renewal charge failed; access paused */
  PD_SUB_CANCELING = 3,      /* cancel requested, runs to period end */
  PD_SUB_CANCELED = 4
};
enum {
  PD_EV_INVOICE_PAID = 1,          /* first payment or a renewal */
  PD_EV_PAYMENT_FAILED = 2,
  PD_EV_CANCEL_AT_PERIOD_END = 3,
  PD_EV_RESUMED = 4,               /* cancel undone before period end */
  PD_EV_DELETED = 5                /* Stripe ended the subscription */
};
/* Next state after `event`. Unknown events leave the state unchanged. */
PD_PAY_API int pd_sub_transition(int state, int event);
/* Whether paid features are available in `state` at time `now` given the
 * current period end (unix seconds). */
PD_PAY_API int pd_sub_entitled(int state, int64_t period_end, int64_t now);

#ifdef __cplusplus
}
#endif

#endif /* PD_PAY_H */
