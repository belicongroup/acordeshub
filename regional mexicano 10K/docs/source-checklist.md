# Source Checklist

Use this checklist to collect broad + long-tail artist candidates.

## 1) MusicBrainz (Backbone)
- [ ] Pull artists with area/country tied to Mexico.
- [ ] Pull artists tagged with:
  - regional mexicano
  - banda
  - norteño
  - corridos
  - sierreño
  - ranchera
  - mariachi
  - duranguense
  - grupero
- [ ] Save each batch to `data/raw/musicbrainz_*.json`.

## 2) Spotify (Modern + Graph Expansion)
- [ ] Start from 100-300 seed artists.
- [ ] Expand related artists from each seed.
- [ ] Pull artist metadata for expanded set.
- [ ] Save each batch to `data/raw/spotify_*.json`.

## 3) Discogs (Catalog Depth)
- [ ] Pull artists with Mexico country signal.
- [ ] Pull artists matching target styles.
- [ ] Save each batch to `data/raw/discogs_*.json`.

## 4) Last.fm (Tag Expansion)
- [ ] Pull artists from genre tag pages / APIs.
- [ ] Expand with similar artists.
- [ ] Save each batch to `data/raw/lastfm_*.json`.

## 5) Wikidata (Validation)
- [ ] Validate nationality when ambiguous.
- [ ] Add aliases and alternate labels.
- [ ] Save each batch to `data/raw/wikidata_*.json`.

## Standard Raw Row Format
Each row should map into these common keys before scoring:
- `name` (required)
- `aliases` (list, optional)
- `country_signals` (list, optional)
- `genre_signals` (list, optional)
- `source` (required)
- `source_artist_id` (required)
- `source_url` (optional)
- `popularity_metric` (optional number)

## Run Pipeline
1. Put normalized source files under `data/raw/`.
2. Run normalization + scoring:
   - `python3 scripts/normalize_and_score.py --config scripts/config.json`
3. Export CSVs:
   - `python3 scripts/export_csv.py --input data/processed/artists_scored.json --outdir data/exports`
