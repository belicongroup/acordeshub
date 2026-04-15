# Regional Mexicano 10K

This folder contains everything needed to build a long-form list of Regional Mexicano artists with a reproducible pipeline.

## Contents
- `docs/source-checklist.md`: source-by-source collection checklist.
- `sql/schema.sql`: database schema for staging and curated datasets.
- `scripts/config.example.json`: configurable inputs and matching thresholds.
- `scripts/normalize_and_score.py`: normalize, dedupe, and confidence-score pipeline.
- `scripts/export_csv.py`: exports curated outputs to CSV.
- `data/`: raw and processed CSV/JSON outputs.

## Quick Start
1. Copy `scripts/config.example.json` to `scripts/config.json` and update values.
2. Put raw source pulls under `data/raw/`.
3. Run:
   - `python3 scripts/normalize_and_score.py --config scripts/config.json`
   - `python3 scripts/export_csv.py --input data/processed/artists_scored.json --outdir data/exports`

## Notes
- The pipeline is source-agnostic. You can append rows from MusicBrainz, Spotify, Discogs, Last.fm, and Wikidata.
- Confidence scoring is heuristic and intended for prioritization, not absolute truth.
