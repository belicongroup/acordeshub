#!/usr/bin/env python3
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List


BASE_URL = "https://musicbrainz.org/ws/2/artist"


def fetch_json(url: str, user_agent: str) -> Dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def map_artist_row(artist: Dict, query_label: str) -> Dict:
    aliases = [a.get("name", "") for a in artist.get("aliases", []) if a.get("name")]
    countries = []
    if artist.get("country"):
        countries.append(str(artist["country"]))
    if artist.get("area", {}).get("name"):
        countries.append(str(artist["area"]["name"]))
    if artist.get("begin-area", {}).get("name"):
        countries.append(str(artist["begin-area"]["name"]))
    tags = [t.get("name", "") for t in artist.get("tags", []) if t.get("name")]
    genres = sorted(set(tags + [query_label]))

    return {
        "name": artist.get("name", "").strip(),
        "aliases": sorted(set([x for x in aliases if x])),
        "country_signals": sorted(set([x for x in countries if x])),
        "genre_signals": genres,
        "source": "musicbrainz",
        "source_artist_id": artist.get("id", ""),
        "source_url": f'https://musicbrainz.org/artist/{artist.get("id", "")}',
        "popularity_metric": None,
    }


def run_query(query: str, label: str, per_query: int, user_agent: str) -> List[Dict]:
    limit = 100
    offset = 0
    rows: List[Dict] = []
    seen = set()

    while len(rows) < per_query:
        encoded = urllib.parse.quote(query)
        url = f"{BASE_URL}?fmt=json&limit={limit}&offset={offset}&query={encoded}"
        payload = fetch_json(url, user_agent)
        artists = payload.get("artists", [])
        if not artists:
            break

        for artist in artists:
            row = map_artist_row(artist, label)
            sid = row["source_artist_id"]
            if not row["name"] or not sid or sid in seen:
                continue
            seen.add(sid)
            rows.append(row)
            if len(rows) >= per_query:
                break

        offset += limit
        time.sleep(1.1)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Broad MusicBrainz Mexico crawl.")
    parser.add_argument("--per-query", type=int, default=4000, help="Max artists per query.")
    parser.add_argument("--out", default="data/raw/musicbrainz_broad.json", help="Output path.")
    parser.add_argument(
        "--user-agent",
        default="regional-mexicano-10k-script/1.0 (contact: local-user)",
        help="Descriptive User-Agent.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_path = project_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    queries = [
        ('area:Mexico AND type:Person', "mx_person"),
        ('area:Mexico AND type:Group', "mx_group"),
        ('beginarea:Mexico AND type:Person', "mx_beginarea_person"),
        ('beginarea:Mexico AND type:Group', "mx_beginarea_group"),
        ('country:MX AND type:Person', "mx_country_person"),
        ('country:MX AND type:Group', "mx_country_group"),
        ('area:Mexico', "mx_any_area"),
        ('beginarea:Mexico', "mx_any_beginarea"),
        ('country:MX', "mx_any_country"),
    ]

    merged: List[Dict] = []
    seen_global = set()
    for query, label in queries:
        rows = run_query(query, label, args.per_query, args.user_agent)
        added = 0
        for row in rows:
            sid = row["source_artist_id"]
            if sid in seen_global:
                continue
            seen_global.add(sid)
            merged.append(row)
            added += 1
        print(f"{label}: fetched {len(rows)} rows, added {added} unique")

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)

    print(f"Total unique rows written: {len(merged)}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
