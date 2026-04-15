-- Regional Mexicano 10K schema

CREATE TABLE IF NOT EXISTS artist_raw (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    source_artist_id TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    country_signals JSONB DEFAULT '[]'::jsonb,
    genre_signals JSONB DEFAULT '[]'::jsonb,
    source_url TEXT,
    popularity_metric NUMERIC,
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, source_artist_id)
);

CREATE TABLE IF NOT EXISTS artist_curated (
    artist_key UUID PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    country_signals JSONB DEFAULT '[]'::jsonb,
    genre_signals JSONB DEFAULT '[]'::jsonb,
    source_ids JSONB DEFAULT '[]'::jsonb,
    confidence_score INTEGER NOT NULL,
    confidence_tier TEXT NOT NULL CHECK (confidence_tier IN ('high', 'medium', 'low')),
    inclusion_reasons JSONB DEFAULT '[]'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS artist_merge_audit (
    id BIGSERIAL PRIMARY KEY,
    losing_source TEXT NOT NULL,
    losing_source_artist_id TEXT NOT NULL,
    merged_into_artist_key UUID NOT NULL,
    merge_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artist_raw_name ON artist_raw (name);
CREATE INDEX IF NOT EXISTS idx_artist_curated_norm_name ON artist_curated (normalized_name);
CREATE INDEX IF NOT EXISTS idx_artist_curated_tier ON artist_curated (confidence_tier);
