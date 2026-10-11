-- Pink Diamond schema (Postgres — production; set DATABASE_URL).
-- Twin of database/schema.sql. Timestamps stay TEXT in the same
-- 'YYYY-MM-DD HH:MM:SS' UTC shape so the API code is backend-agnostic.

CREATE TABLE IF NOT EXISTS users (
    id                 BIGSERIAL PRIMARY KEY,
    username           TEXT    NOT NULL UNIQUE,
    email              TEXT    NOT NULL UNIQUE,
    password_hash      TEXT    NOT NULL,
    api_key_hash       TEXT    NOT NULL,
    created_at         TEXT    NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'),
    plan               TEXT    NOT NULL DEFAULT 'free',
    pink_mode          INTEGER NOT NULL DEFAULT 0,
    credits            DOUBLE PRECISION NOT NULL DEFAULT 0,
    credits_used       DOUBLE PRECISION NOT NULL DEFAULT 0,
    api_balance        DOUBLE PRECISION NOT NULL DEFAULT 0,
    theme              TEXT    NOT NULL DEFAULT 'neon-rose',
    terms_version      TEXT,
    terms_accepted_at  TEXT,
    stripe_customer_id TEXT,
    or_key_hash        TEXT,
    or_key_enc         TEXT,
    funded_cents       BIGINT  NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                     BIGSERIAL PRIMARY KEY,
    user_id                BIGINT  NOT NULL REFERENCES users(id),
    kind                   TEXT    NOT NULL,
    tier                   TEXT,
    billing_interval       TEXT    NOT NULL DEFAULT 'month',
    uncensored             INTEGER NOT NULL DEFAULT 0,
    amount_cents           BIGINT  NOT NULL DEFAULT 0,
    status                 TEXT    NOT NULL DEFAULT 'none',
    period_end             BIGINT  NOT NULL DEFAULT 0,
    stripe_subscription_id TEXT    UNIQUE,
    started_at             TEXT    NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS payments (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT  NOT NULL REFERENCES users(id),
    kind           TEXT    NOT NULL,
    amount_cents   BIGINT  NOT NULL,
    funded_cents   BIGINT  NOT NULL,
    platform_cents BIGINT  NOT NULL,
    credits        BIGINT  NOT NULL,
    stripe_ref     TEXT    NOT NULL UNIQUE,
    payment_intent TEXT,
    created_at     TEXT    NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS stripe_events (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_timeline (
    id      BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    delta   DOUBLE PRECISION NOT NULL,
    reason  TEXT   NOT NULL,
    at      TEXT   NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT  NOT NULL REFERENCES users(id),
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    unfiltered INTEGER NOT NULL DEFAULT 0,
    at         TEXT    NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS ad_slots (
    id         BIGSERIAL PRIMARY KEY,
    placement  TEXT    NOT NULL UNIQUE,
    box        TEXT    NOT NULL,
    price_usd  INTEGER NOT NULL DEFAULT 0,
    advertiser TEXT,
    active     INTEGER NOT NULL DEFAULT 1
);

INSERT INTO ad_slots (placement, box, price_usd) VALUES
    ('rail_left',  'black', 445),
    ('rail_right', 'black', 445),
    ('bottom',     'black', 470),
    ('popup',      'grey',  0)
ON CONFLICT (placement) DO NOTHING;
