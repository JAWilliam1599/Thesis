-- Schema and seed data for the hybrid guestbook demo.
-- Idempotent: safe to apply repeatedly.

CREATE TABLE IF NOT EXISTS guestbook (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reactions feature: a per-entry like counter. Added via ALTER so existing
-- installations gain the column without dropping data.
ALTER TABLE guestbook
    ADD COLUMN IF NOT EXISTS likes INTEGER NOT NULL DEFAULT 0;

INSERT INTO guestbook (name, message)
SELECT 'Ada', 'First entry from the on-prem database!'
WHERE NOT EXISTS (SELECT 1 FROM guestbook);

INSERT INTO guestbook (name, message)
SELECT 'Grace', 'Hybrid cloud + on-prem is working.'
WHERE NOT EXISTS (
    SELECT 1 FROM guestbook WHERE name = 'Grace'
);
