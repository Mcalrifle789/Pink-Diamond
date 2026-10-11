/* Pink Diamond payment core (C): SHA-256, HMAC-SHA256 and Stripe webhook
 * signature verification.
 *
 * Stripe signs each webhook as HMAC-SHA256(secret, "<t>.<raw body>") and
 * sends "Stripe-Signature: t=<unix>,v1=<hex>[,v1=<hex>...]". A webhook is
 * only trusted when one v1 matches in constant time and t is within the
 * replay tolerance. See https://docs.stripe.com/webhooks#verify-manually
 */
#include "pd_pay.h"

#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------ SHA-256 --- */

typedef struct {
  uint32_t h[8];
  uint64_t bits;
  uint8_t buf[64];
  size_t used;
} sha256_ctx;

static const uint32_t K[64] = {
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha256_block(sha256_ctx *c, const uint8_t *p) {
  uint32_t w[64];
  for (int i = 0; i < 16; i++)
    w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = ROR(w[i - 15], 7) ^ ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = ROR(w[i - 2], 17) ^ ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3];
  uint32_t e = c->h[4], f = c->h[5], g = c->h[6], h = c->h[7];
  for (int i = 0; i < 64; i++) {
    uint32_t t1 = h + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
    uint32_t t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) + ((a & b) ^ (a & cc) ^ (b & cc));
    h = g; g = f; f = e; e = d + t1; d = cc; cc = b; b = a; a = t1 + t2;
  }
  c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d;
  c->h[4] += e; c->h[5] += f; c->h[6] += g; c->h[7] += h;
}

static void sha256_init(sha256_ctx *c) {
  static const uint32_t iv[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  memcpy(c->h, iv, sizeof iv);
  c->bits = 0;
  c->used = 0;
}

static void sha256_update(sha256_ctx *c, const uint8_t *p, size_t n) {
  c->bits += (uint64_t)n * 8;
  while (n > 0) {
    size_t take = 64 - c->used < n ? 64 - c->used : n;
    memcpy(c->buf + c->used, p, take);
    c->used += take; p += take; n -= take;
    if (c->used == 64) { sha256_block(c, c->buf); c->used = 0; }
  }
}

static void sha256_final(sha256_ctx *c, uint8_t out[32]) {
  uint64_t bits = c->bits;
  uint8_t pad = 0x80;
  sha256_update(c, &pad, 1);
  pad = 0;
  while (c->used != 56) sha256_update(c, &pad, 1);
  uint8_t len[8];
  for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - 8 * i));
  sha256_update(c, len, 8);
  for (int i = 0; i < 8; i++) {
    out[4 * i] = (uint8_t)(c->h[i] >> 24); out[4 * i + 1] = (uint8_t)(c->h[i] >> 16);
    out[4 * i + 2] = (uint8_t)(c->h[i] >> 8); out[4 * i + 3] = (uint8_t)c->h[i];
  }
}

void pd_sha256(const uint8_t *data, size_t len, uint8_t *out) {
  sha256_ctx c;
  sha256_init(&c);
  sha256_update(&c, data, len);
  sha256_final(&c, out);
}

void pd_hmac_sha256(const uint8_t *key, size_t key_len, const uint8_t *msg, size_t msg_len, uint8_t *out) {
  uint8_t k[64] = {0}, ipad[64], opad[64], inner[32];
  if (key_len > 64) pd_sha256(key, key_len, k);
  else memcpy(k, key, key_len);
  for (int i = 0; i < 64; i++) { ipad[i] = k[i] ^ 0x36; opad[i] = k[i] ^ 0x5c; }
  sha256_ctx c;
  sha256_init(&c); sha256_update(&c, ipad, 64); sha256_update(&c, msg, msg_len); sha256_final(&c, inner);
  sha256_init(&c); sha256_update(&c, opad, 64); sha256_update(&c, inner, 32); sha256_final(&c, out);
}

/* ------------------------------------------------- Stripe-Signature --- */

static int hex_nibble(char ch) {
  if (ch >= '0' && ch <= '9') return ch - '0';
  if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
  if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
  return -1;
}

/* Constant-time compare of a 64-char hex string against a 32-byte digest. */
static int hex_equals(const char *hex, size_t hex_len, const uint8_t digest[32]) {
  if (hex_len != 64) return 0;
  uint8_t diff = 0;
  for (int i = 0; i < 32; i++) {
    int hi = hex_nibble(hex[2 * i]), lo = hex_nibble(hex[2 * i + 1]);
    if (hi < 0 || lo < 0) return 0;
    diff |= (uint8_t)((hi << 4 | lo) ^ digest[i]);
  }
  return diff == 0;
}

int pd_stripe_verify(const char *payload, size_t payload_len, const char *header,
                     const char *secret, int64_t now, int64_t tolerance_seconds) {
  if (!payload || !header || !secret) return PD_SIG_MALFORMED;

  /* Pass 1: find t=. */
  const char *t_val = NULL;
  size_t t_len = 0;
  for (const char *p = header; *p;) {
    const char *end = strchr(p, ',');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    if (len > 2 && p[0] == 't' && p[1] == '=') { t_val = p + 2; t_len = len - 2; }
    p = end ? end + 1 : p + len;
  }
  if (!t_val || t_len == 0 || t_len > 19) return PD_SIG_MALFORMED;
  int64_t ts = 0;
  for (size_t i = 0; i < t_len; i++) {
    if (t_val[i] < '0' || t_val[i] > '9') return PD_SIG_MALFORMED;
    ts = ts * 10 + (t_val[i] - '0');
  }

  /* signed_payload = "<t>.<payload>" */
  size_t msg_len = t_len + 1 + payload_len;
  uint8_t *msg = (uint8_t *)malloc(msg_len);
  if (!msg) return PD_SIG_MALFORMED;
  memcpy(msg, t_val, t_len);
  msg[t_len] = '.';
  memcpy(msg + t_len + 1, payload, payload_len);
  uint8_t expected[32];
  pd_hmac_sha256((const uint8_t *)secret, strlen(secret), msg, msg_len, expected);
  free(msg);

  /* Pass 2: any v1= may match (Stripe sends several while rolling secrets). */
  int saw_v1 = 0, matched = 0;
  for (const char *p = header; *p;) {
    const char *end = strchr(p, ',');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    if (len > 3 && p[0] == 'v' && p[1] == '1' && p[2] == '=') {
      saw_v1 = 1;
      matched |= hex_equals(p + 3, len - 3, expected);
    }
    p = end ? end + 1 : p + len;
  }
  if (!saw_v1) return PD_SIG_MALFORMED;
  if (!matched) return PD_SIG_MISMATCH;
  int64_t age = now - ts;
  if (age < 0) age = -age;
  if (tolerance_seconds > 0 && age > tolerance_seconds) return PD_SIG_EXPIRED;
  return PD_SIG_OK;
}
