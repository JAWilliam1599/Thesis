-- Schema and seed data for the hybrid guestbook demo.
-- Idempotent: safe to apply repeatedly.

CREATE TABLE IF NOT EXISTS guestbook (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO guestbook (name, message)
SELECT 'Ada', 'First entry from the on-prem database!'
WHERE NOT EXISTS (SELECT 1 FROM guestbook);

INSERT INTO guestbook (name, message)
SELECT 'Grace', 'Hybrid cloud + on-prem is working.'
WHERE NOT EXISTS (
    SELECT 1 FROM guestbook WHERE name = 'Grace'
);
