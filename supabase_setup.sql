-- ============================================================
-- SmartQueue — Supabase Database Setup
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- 1. Queue entries table
CREATE TABLE IF NOT EXISTS queue_entries (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    user_name   TEXT,
    email       TEXT,
    priority    TEXT        NOT NULL DEFAULT 'normal',
    status      TEXT        NOT NULL DEFAULT 'waiting',
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    served_at   TIMESTAMPTZ,
    notified    BOOLEAN     NOT NULL DEFAULT FALSE
);

-- 2. Index for fast queue lookups
CREATE INDEX IF NOT EXISTS idx_queue_status_joined
    ON queue_entries (status, joined_at);

-- 3. Priority sort order (emergency first, then senior, then normal)
-- This is handled in Python, but documented here for reference.

-- 4. Enable Row Level Security (allow all for now — tighten later)
ALTER TABLE queue_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all" ON queue_entries
    FOR ALL USING (true) WITH CHECK (true);

-- 5. Served log view (for admin stats)
CREATE OR REPLACE VIEW served_today AS
    SELECT COUNT(*) AS count,
           AVG(EXTRACT(EPOCH FROM (served_at - joined_at))) AS avg_wait_seconds
    FROM queue_entries
    WHERE status = 'served'
      AND served_at::date = CURRENT_DATE;
