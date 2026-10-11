"""Prices, policy constants and environment for Pink Diamond.

The browser shows these numbers but never decides them: every checkout is
priced here, on the server.
"""

from __future__ import annotations

import os

PLAN_PRICES_CENTS = {"go": 1199, "plus": 2299, "pro": 3399, "max": 12199}   # monthly
PLAN_NAMES = {"go": "Go", "plus": "Plus", "pro": "Pro", "max": "Max"}
PLAN_CREDITS = {"go": 2000, "plus": 3500, "pro": 8300, "max": 16660}        # demo-billing quotas

UNCENSORED_PRICE_CENTS = 1000          # +$10/mo add-on, added to the subscription
TOPUP_PRESETS_CENTS = [1000, 2000, 5000, 10000, 25000, 50000]   # $10 … $500, plus a custom amount

# Bump whenever legal/terms.html changes; users re-accept before their next purchase.
TERMS_VERSION = "2026-10-10"

SESSION_SECRET_DEFAULT = "dev-secret-change-me"


def env(name: str) -> str:
    return os.environ.get(name, "").strip()
