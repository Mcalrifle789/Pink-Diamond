"""Binding for the native payment core (native/payments: C + C++ + Zig).

Loads backend/native/<lib> when present (the linux build ships with the
Vercel function) and falls back to an identical pure-Python mirror, so the
API behaves the same everywhere. test_payments.py checks both agree.
"""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import sys
from pathlib import Path

# Constants shared with pd_money.zig / pd_pay.h
CREDITS_PER_DOLLAR = 100
TOPUP_MIN_CENTS = 500
TOPUP_MAX_CENTS = 100_000
SIG_OK, SIG_MALFORMED, SIG_MISMATCH, SIG_EXPIRED = 0, 1, 2, 3
SUB_NONE, SUB_ACTIVE, SUB_PAST_DUE, SUB_CANCELING, SUB_CANCELED = 0, 1, 2, 3, 4
EV_INVOICE_PAID, EV_PAYMENT_FAILED, EV_CANCEL_AT_PERIOD_END, EV_RESUMED, EV_DELETED = 1, 2, 3, 4, 5
SUB_STATE_NAMES = {SUB_NONE: "none", SUB_ACTIVE: "active", SUB_PAST_DUE: "past_due",
                   SUB_CANCELING: "canceling", SUB_CANCELED: "canceled"}
SUB_STATE_CODES = {v: k for k, v in SUB_STATE_NAMES.items()}


def _load():
    folder = Path(__file__).resolve().parent / "native"
    names = {"win32": ["pd_pay.dll"], "darwin": ["libpd_pay.dylib"]}.get(
        sys.platform, ["libpd_pay-linux-x86_64.so", "libpd_pay.so"])
    for name in names:
        path = folder / name
        if not path.exists():
            continue
        try:
            lib = ctypes.CDLL(str(path))
        except OSError:
            continue
        i64, c_int = ctypes.c_int64, ctypes.c_int
        for fn in ("pd_split_customer_cents", "pd_split_platform_cents", "pd_cents_to_credits"):
            getattr(lib, fn).argtypes, getattr(lib, fn).restype = [i64], i64
        lib.pd_plan_price_cents.argtypes, lib.pd_plan_price_cents.restype = [i64, c_int], i64
        lib.pd_topup_valid.argtypes, lib.pd_topup_valid.restype = [i64], c_int
        lib.pd_stripe_verify.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
                                         ctypes.c_char_p, i64, i64]
        lib.pd_stripe_verify.restype = c_int
        lib.pd_sub_transition.argtypes, lib.pd_sub_transition.restype = [c_int, c_int], c_int
        lib.pd_sub_entitled.argtypes, lib.pd_sub_entitled.restype = [c_int, i64, i64], c_int
        lib.pd_sha256.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
        return lib
    return None


_lib = _load()
NATIVE = _lib is not None


def engine() -> str:
    return "native (C + C++ + Zig)" if NATIVE else "python mirror"


# ------------------------------------------------------------ money (Zig) ---

def split_customer_cents(paid: int, *, native: bool = True) -> int:
    if native and _lib:
        return _lib.pd_split_customer_cents(paid)
    return 0 if paid <= 0 else paid - paid // 2


def split_platform_cents(paid: int, *, native: bool = True) -> int:
    if native and _lib:
        return _lib.pd_split_platform_cents(paid)
    return 0 if paid <= 0 else paid // 2


def cents_to_credits(cents: int, *, native: bool = True) -> int:
    if native and _lib:
        return _lib.pd_cents_to_credits(cents)
    return 0 if cents <= 0 else cents * CREDITS_PER_DOLLAR // 100


def plan_price_cents(monthly: int, interval: str, *, native: bool = True) -> int:
    code = 1 if interval == "year" else 0
    if native and _lib:
        return _lib.pd_plan_price_cents(monthly, code)
    if monthly <= 0:
        return 0
    return monthly if code == 0 else (12 * monthly * 80 + 50) // 100


def topup_valid(cents: int, *, native: bool = True) -> bool:
    if native and _lib:
        return bool(_lib.pd_topup_valid(cents))
    return TOPUP_MIN_CENTS <= cents <= TOPUP_MAX_CENTS


# ------------------------------------------------------- signatures (C) ---

def stripe_verify(payload: bytes, header: str, secret: str, now: int,
                  tolerance: int = 300, *, native: bool = True) -> int:
    if native and _lib:
        return _lib.pd_stripe_verify(payload, len(payload), header.encode(), secret.encode(), now, tolerance)
    parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
    ts = next((v for k, v in parts if k == "t"), None)
    sigs = [v for k, v in parts if k == "v1"]
    if not ts or not ts.isdigit() or len(ts) > 19 or not sigs:
        return SIG_MALFORMED
    expected = hmac.new(secret.encode(), ts.encode() + b"." + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s.lower()) for s in sigs):
        return SIG_MISMATCH
    if tolerance > 0 and abs(now - int(ts)) > tolerance:
        return SIG_EXPIRED
    return SIG_OK


def sha256_hex(data: bytes) -> str:
    if _lib:
        out = ctypes.create_string_buffer(32)
        _lib.pd_sha256(data, len(data), out)
        return out.raw.hex()
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------- lifecycle (C++) ---

_TABLE = {
    SUB_NONE:      {EV_INVOICE_PAID: SUB_ACTIVE, EV_DELETED: SUB_CANCELED},
    SUB_ACTIVE:    {EV_INVOICE_PAID: SUB_ACTIVE, EV_PAYMENT_FAILED: SUB_PAST_DUE,
                    EV_CANCEL_AT_PERIOD_END: SUB_CANCELING, EV_DELETED: SUB_CANCELED},
    SUB_PAST_DUE:  {EV_INVOICE_PAID: SUB_ACTIVE, EV_CANCEL_AT_PERIOD_END: SUB_CANCELING,
                    EV_DELETED: SUB_CANCELED},
    SUB_CANCELING: {EV_INVOICE_PAID: SUB_CANCELING, EV_PAYMENT_FAILED: SUB_PAST_DUE,
                    EV_RESUMED: SUB_ACTIVE, EV_DELETED: SUB_CANCELED},
    SUB_CANCELED:  {EV_INVOICE_PAID: SUB_ACTIVE},
}


def sub_transition(state: int, event: int, *, native: bool = True) -> int:
    if native and _lib:
        return _lib.pd_sub_transition(state, event)
    return _TABLE.get(state, {}).get(event, state)


def sub_entitled(state: int, period_end: int, now: int, *, native: bool = True) -> bool:
    if native and _lib:
        return bool(_lib.pd_sub_entitled(state, period_end, now))
    return state in (SUB_ACTIVE, SUB_CANCELING) and period_end > now
