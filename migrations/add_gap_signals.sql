-- Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

CREATE TYPE gap_signal_status AS ENUM ('OPEN', 'IN_PROGRESS', 'RESOLVED');

CREATE TABLE IF NOT EXISTS knowledge_gap_signals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query               TEXT NOT NULL,
    topic_needed        TEXT,
    jurisdiction_needed TEXT,
    gap_description     TEXT NOT NULL,
    metadata            JSONB NOT NULL DEFAULT '{}',
    status              gap_signal_status NOT NULL DEFAULT 'OPEN',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ
);

-- Index to support curator dashboard queries fetching open signals sorted by time
CREATE INDEX IF NOT EXISTS idx_kgs_status_created_at
    ON knowledge_gap_signals (status, created_at DESC);
