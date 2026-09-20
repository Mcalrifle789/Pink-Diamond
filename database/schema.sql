-- Pink Diamond schema (SQLite)
-- Users carry the Pink Mode entitlement server-side; the client toggle is
-- advisory only and is re-checked on every chat request.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    api_key_hash  TEXT    NOT NULL,                -- secret key: hashed, never shown to the user
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    plan          TEXT    NOT NULL DEFAULT 'free', -- free | port | plus | pro | max
    pink_mode     INTEGER NOT NULL DEFAULT 0,      -- 1 only while an active pink_mode subscription exists
    credits       REAL    NOT NULL DEFAULT 0,
    credits_used  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    kind         TEXT    NOT NULL,                 -- plan | pink_mode | credit_pack
    tier         TEXT,                             -- port | plus | pro | max (kind=plan only)
    amount_cents INTEGER NOT NULL DEFAULT 0,
    started_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    renews_at    TEXT,
    active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS credit_timeline (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    delta   REAL    NOT NULL,
    reason  TEXT    NOT NULL,
    at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    role       TEXT    NOT NULL,                    -- user | agent
    content    TEXT    NOT NULL,
    unfiltered INTEGER NOT NULL DEFAULT 0,          -- 1 = Pink Mode was active for this message
    at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Ad inventory per the monetization spec: two vertical rails at $400,
-- bottom horizontal at $350, dismissible grey pop-ups.
CREATE TABLE IF NOT EXISTS ad_slots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    placement  TEXT NOT NULL,                     -- rail_left | rail_right | bottom | popup
    box        TEXT NOT NULL,                     -- black | grey
    price_usd  INTEGER NOT NULL DEFAULT 0,        -- 400 | 400 | 350 | 0
    advertiser TEXT,
    active     INTEGER NOT NULL DEFAULT 1
);

INSERT OR IGNORE INTO ad_slots (placement, box, price_usd) VALUES
    ('rail_left',  'black', 400),
    ('rail_right', 'black', 400),
    ('bottom',     'black', 350),
    ('popup',      'grey',  0);
