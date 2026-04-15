#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def load_json(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return payload
    return []


def row_for_csv(item: Dict) -> Dict:
    return {
        "artist_key": item.get("artist_key", ""),
        "canonical_name": item.get("canonical_name", ""),
        "normalized_name": item.get("normalized_name", ""),
        "aliases": "|".join(item.get("aliases", [])),
        "country_signals": "|".join(item.get("country_signals", [])),
        "genre_signals": "|".join(item.get("genre_signals", [])),
        "source_ids": json.dumps(item.get("source_ids", []), ensure_ascii=False),
        "confidence_score": item.get("confidence_score", 0),
        "confidence_tier": item.get("confidence_tier", "low"),
        "inclusion_reasons": "|".join(item.get("inclusion_reasons", [])),
        "notes": item.get("notes", ""),
    }


def write_csv(path: Path, rows: List[Dict]) -> None:
    fields = [
        "artist_key",
        "canonical_name",
        "normalized_name",
        "aliases",
        "country_signals",
        "genre_signals",
        "source_ids",
        "confidence_score",
        "confidence_tier",
        "inclusion_reasons",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export curated artist JSON to CSV files.")
    parser.add_argument("--input", required=True, help="Input JSON path.")
    parser.add_argument("--outdir", required=True, help="Output directory for CSV files.")
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = load_json(input_path)
    csv_rows = [row_for_csv(item) for item in rows]

    all_path = outdir / "regional_mexicano_artists_deduped.csv"
    high_path = outdir / "regional_mexicano_artists_high_confidence.csv"

    write_csv(all_path, csv_rows)
    write_csv(high_path, [r for r in csv_rows if r["confidence_tier"] == "high"])

    print(f"Input rows: {len(rows)}")
    print(f"Wrote: {all_path}")
    print(f"Wrote: {high_path}")


if __name__ == "__main__":
    main()
