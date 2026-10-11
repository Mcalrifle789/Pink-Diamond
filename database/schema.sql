-- Pink Diamond schema (SQLite — local development).
-- database/schema.postgres.sql is the production twin; keep them in step.
-- Users carry the Pink Mode entitlement server-side; the client toggle is
-- advisory only and is re-checked on every chat request.
-- Money is stored as integer cents. Card numbers are never stored anywhere:
-- Stripe holds payment methods, we keep only its customer id.

CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT    NOT NULL UNIQUE,
    email             TEXT    NOT NULL UNIQUE,
    password_hash     TEXT    NOT NULL,
    api_key_hash      TEXT    NOT NULL,                -- secret key: hashed, never shown to the user
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    plan              TEXT    NOT NULL DEFAULT 'free', -- free | go | plus | pro | max
    pink_mode         INTEGER NOT NULL DEFAULT 0,      -- 1 only while an active pink_mode subscription exists
    credits           REAL    NOT NULL DEFAULT 0,
    credits_used      REAL    NOT NULL DEFAULT 0,
    api_balance       REAL    NOT NULL DEFAULT 0,      -- demo-billing balance (dollars)
    theme             TEXT    NOT NULL DEFAULT 'neon-rose', -- one of 10 themes, restored on sign-in
    terms_version     TEXT,                            -- Terms & Agreement version accepted at sign-up
    terms_accepted_at TEXT,
    stripe_customer_id TEXT,                           -- Stripe holds the saved cards
    or_key_hash       TEXT,                            -- the user's auto-generated OpenRouter key
    or_key_enc        TEXT,                            -- that key, encrypted at rest (Fernet)
    funded_cents      INTEGER NOT NULL DEFAULT 0       -- total ever funded to the key = its spend limit
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                INTEGER NOT NULL REFERENCES users(id),
    kind                   TEXT    NOT NULL,           -- plan
    tier                   TEXT,                       -- go | plus | pro | max
    billing_interval       TEXT    NOT NULL DEFAULT 'month', -- month | year
    uncensored             INTEGER NOT NULL DEFAULT 0, -- Uncensored Mode add-on (+$10/mo) on this subscription
    amount_cents           INTEGER NOT NULL DEFAULT 0,
    status                 TEXT    NOT NULL DEFAULT 'none', -- none | active | past_due | canceling | canceled
    period_end             INTEGER NOT NULL DEFAULT 0, -- unix seconds; auto-renews here
    stripe_subscription_id TEXT    UNIQUE,
    started_at             TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Every settled payment, once. stripe_ref (invoice / payment intent id) makes
-- webhook retries idempotent.
CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    kind           TEXT    NOT NULL,                   -- subscription | topup | refund
    amount_cents   INTEGER NOT NULL,
    funded_cents   INTEGER NOT NULL,                   -- credited to the user's model balance
    platform_cents INTEGER NOT NULL,
    credits        INTEGER NOT NULL,                   -- Pink Credits ($1 = 100)
    stripe_ref     TEXT    NOT NULL UNIQUE,
    payment_intent TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stripe_events (
    id          TEXT PRIMARY KEY,                      -- evt_... processed exactly once
    type        TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
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

-- Ad inventory per the AdSense update: two vertical rails at an estimated
-- $445/mo each, bottom horizontal at $470/mo, dismissible grey pop-ups.
CREATE TABLE IF NOT EXISTS ad_slots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    placement  TEXT NOT NULL UNIQUE,              -- rail_left | rail_right | bottom | popup
    box        TEXT NOT NULL,                     -- black | grey
    price_usd  INTEGER NOT NULL DEFAULT 0,        -- 445 | 445 | 470 | 0
    advertiser TEXT,
    active     INTEGER NOT NULL DEFAULT 1
);

INSERT OR IGNORE INTO ad_slots (placement, box, price_usd) VALUES
    ('rail_left',  'black', 445),
    ('rail_right', 'black', 445),
    ('bottom',     'black', 470),
    ('popup',      'grey',  0);
