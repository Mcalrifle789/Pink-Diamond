"""Who has paid for what, decided from the subscriptions table.

The lifecycle rules (which state grants access, until when) come from the
native C++ core via payments_core.
"""

from __future__ import annotations

import time

import database as db
import payments_core as core


def current_subscription(user_id: int) -> dict | None:
    """The user's entitled plan subscription, if any."""
    rows = db.all(
        "SELECT * FROM subscriptions WHERE user_id=? AND kind='plan' ORDER BY period_end DESC",
        (user_id,),
    )
    now = int(time.time())
    for row in rows:
        state = core.SUB_STATE_CODES.get(row["status"], core.SUB_NONE)
        if core.sub_entitled(state, int(row["period_end"]), now):
            return dict(row)
    return None


def subscribed(user: dict) -> bool:
    """An active paid plan — the gate for every OpenRouter model."""
    return current_subscription(user["id"]) is not None


def pink_active(user_id: int) -> bool:
    """Uncensored Mode is paid for on the active subscription. Always checked
    server-side before unfiltered chat; the browser toggle is advisory."""
    sub = current_subscription(user_id)
    return bool(sub and sub["uncensored"])
