#!/usr/bin/env python3
import argparse
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple


def slugify_name(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\b(feat|ft)\.?\b.*$", "", value).strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def similarity(a: str, b: str) -> int:
    return int(SequenceMatcher(None, a, b).ratio() * 100)


@dataclass
class CuratedArtist:
    artist_key: str
    canonical_name: str
    normalized_name: str
    aliases: List[str] = field(default_factory=list)
    country_signals: List[str] = field(default_factory=list)
    genre_signals: List[str] = field(default_factory=list)
    source_ids: List[Dict[str, str]] = field(default_factory=list)
    confidence_score: int = 0
    confidence_tier: str = "low"
    inclusion_reasons: List[str] = field(default_factory=list)
    notes: str = ""


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def read_raw_records(raw_dir: Path) -> List[Dict]:
    records: List[Dict] = []
    for entry in sorted(raw_dir.glob("*.json")):
        with entry.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
            if isinstance(payload, list):
                records.extend(payload)
            elif isinstance(payload, dict):
                records.append(payload)
    return records


def is_mexico_signal(signals: List[str], keywords: List[str]) -> bool:
    joined = " ".join(signals).lower()
    return any(k.lower() in joined for k in keywords)


def has_regional_signal(genres: List[str], regional_genres: List[str]) -> bool:
    joined = " ".join(genres).lower()
    return any(g.lower() in joined for g in regional_genres)


def compute_confidence(
    country_signals: List[str],
    genre_signals: List[str],
    source_count: int,
    mexico_keywords: List[str],
    regional_genres: List[str],
) -> Tuple[int, List[str], str]:
    score = 0
    reasons: List[str] = []

    if is_mexico_signal(country_signals, mexico_keywords):
        score += 2
        reasons.append("mexico_signal")
    if has_regional_signal(genre_signals, regional_genres):
        score += 1
        reasons.append("regional_genre_signal")
    if source_count >= 2:
        score += 1
        reasons.append("multi_source_presence")
    if score >= 4:
        tier = "high"
    elif score >= 2:
        tier = "medium"
    else:
        tier = "low"
    return score, reasons, tier


def dedupe_records(records: List[Dict], config: Dict) -> Tuple[List[CuratedArtist], List[Dict]]:
    by_name: Dict[str, CuratedArtist] = {}
    name_buckets: Dict[str, List[str]] = {}
    review_queue: List[Dict] = []
    auto_merge_threshold = int(config["min_auto_merge_similarity"])
    review_threshold = int(config["review_similarity_floor"])

    for row in records:
        name = str(row.get("name", "")).strip()
        source = str(row.get("source", "")).strip()
        source_artist_id = str(row.get("source_artist_id", "")).strip()
        if not name or not source or not source_artist_id:
            continue

        norm = slugify_name(name)
        if not norm:
            continue

        countries = [str(x) for x in row.get("country_signals", [])]
        genres = [str(x) for x in row.get("genre_signals", [])]
        aliases = [str(x) for x in row.get("aliases", [])]
        source_id = {"source": source, "id": source_artist_id}

        if norm in by_name:
            target = by_name[norm]
            target.aliases = sorted(set(target.aliases + aliases + [name]))
            target.country_signals = sorted(set(target.country_signals + countries))
            target.genre_signals = sorted(set(target.genre_signals + genres))
            target.source_ids.append(source_id)
            continue

        matched_key = None
        best_score = -1
        bucket_key = norm[0] if norm else "#"
        candidates = name_buckets.get(bucket_key, [])
        for existing_norm in candidates:
            # Quick guard to avoid expensive fuzzy checks on very different lengths.
            if abs(len(existing_norm) - len(norm)) > 4:
                continue
            score = similarity(norm, existing_norm)
            if score > best_score:
                best_score = score
                matched_key = existing_norm

        if matched_key and best_score >= auto_merge_threshold:
            target = by_name[matched_key]
            target.aliases = sorted(set(target.aliases + aliases + [name]))
            target.country_signals = sorted(set(target.country_signals + countries))
            target.genre_signals = sorted(set(target.genre_signals + genres))
            target.source_ids.append(source_id)
            continue

        if matched_key and review_threshold <= best_score < auto_merge_threshold:
            review_queue.append(
                {
                    "candidate_name": name,
                    "candidate_normalized_name": norm,
                    "possible_match_normalized_name": matched_key,
                    "similarity": best_score,
                    "source": source,
                    "source_artist_id": source_artist_id,
                }
            )

        artist = CuratedArtist(
            artist_key=str(uuid.uuid4()),
            canonical_name=name,
            normalized_name=norm,
            aliases=sorted(set(aliases + [name])),
            country_signals=sorted(set(countries)),
            genre_signals=sorted(set(genres)),
            source_ids=[source_id],
        )
        by_name[norm] = artist
        if bucket_key not in name_buckets:
            name_buckets[bucket_key] = []
        name_buckets[bucket_key].append(norm)

    curated = list(by_name.values())
    for artist in curated:
        score, reasons, tier = compute_confidence(
            artist.country_signals,
            artist.genre_signals,
            len({f"{x['source']}::{x['id']}" for x in artist.source_ids}),
            config["mexico_keywords"],
            config["regional_genres"],
        )
        artist.confidence_score = score
        artist.inclusion_reasons = reasons
        artist.confidence_tier = tier

    return curated, review_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize, dedupe, and score artist candidates.")
    parser.add_argument("--config", required=True, help="Path to config JSON file.")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)

    root = config_path.parent.parent
    raw_dir = root / config["raw_data_dir"]
    output_path = root / config["processed_output_path"]
    review_path = root / "data" / "processed" / "merge_review_queue.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = read_raw_records(raw_dir)
    curated, review_queue = dedupe_records(records, config)

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump([asdict(a) for a in curated], fh, ensure_ascii=False, indent=2)

    with review_path.open("w", encoding="utf-8") as fh:
        json.dump(review_queue, fh, ensure_ascii=False, indent=2)

    print(f"Processed raw records: {len(records)}")
    print(f"Curated artists: {len(curated)}")
    print(f"Review queue rows: {len(review_queue)}")
    print(f"Wrote: {output_path}")
    print(f"Wrote: {review_path}")


if __name__ == "__main__":
    main()
