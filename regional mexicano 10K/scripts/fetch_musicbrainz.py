#!/usr/bin/env python3
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List


BASE_URL = "https://musicbrainz.org/ws/2/artist"


def build_query(genre: str) -> str:
    # MusicBrainz Lucene query: Mexico area + genre/tag signal.
    return f'area:Mexico AND (tag:"{genre}" OR genre:"{genre}")'


def fetch_json(url: str, user_agent: str) -> Dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def map_artist_row(artist: Dict, genre_seed: str) -> Dict:
    aliases = [a.get("name", "") for a in artist.get("aliases", []) if a.get("name")]
    country_signals = []
    if artist.get("country"):
        country_signals.append(str(artist["country"]))
    if artist.get("area", {}).get("name"):
        country_signals.append(str(artist["area"]["name"]))
    if artist.get("begin-area", {}).get("name"):
        country_signals.append(str(artist["begin-area"]["name"]))

    tags = [t.get("name", "") for t in artist.get("tags", []) if t.get("name")]
    genre_signals = sorted(set(tags + [genre_seed]))

    return {
        "name": artist.get("name", "").strip(),
        "aliases": sorted(set([x for x in aliases if x])),
        "country_signals": sorted(set([x for x in country_signals if x])),
        "genre_signals": genre_signals,
        "source": "musicbrainz",
        "source_artist_id": artist.get("id", ""),
        "source_url": f'https://musicbrainz.org/artist/{artist.get("id", "")}',
        "popularity_metric": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch MusicBrainz artists for Regional Mexicano seeds.")
    parser.add_argument(
        "--genres",
        nargs="+",
        default=[
            "regional mexicano",
            "banda",
            "norteño",
            "corridos",
            "mariachi",
            "ranchera",
            "duranguense",
            "grupero",
        ],
        help="Genre seeds to query.",
    )
    parser.add_argument("--per-genre", type=int, default=250, help="Max artists per genre.")
    parser.add_argument(
        "--out",
        default="data/raw/musicbrainz_seed.json",
        help="Output JSON path relative to project folder.",
    )
    parser.add_argument(
        "--user-agent",
        default="regional-mexicano-10k-script/1.0 (contact: local-user)",
        help="MusicBrainz requires a descriptive User-Agent.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_path = project_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows: List[Dict] = []
    seen_ids = set()
    limit = 100

    for genre in args.genres:
        fetched = 0
        offset = 0
        while fetched < args.per_genre:
            query = build_query(genre)
            encoded_q = urllib.parse.quote(query)
            url = f"{BASE_URL}?fmt=json&limit={limit}&offset={offset}&query={encoded_q}"
            payload = fetch_json(url, args.user_agent)
            artists = payload.get("artists", [])
            if not artists:
                break

            for artist in artists:
                row = map_artist_row(artist, genre)
                source_id = row["source_artist_id"]
                if not row["name"] or not source_id or source_id in seen_ids:
                    continue
                seen_ids.add(source_id)
                all_rows.append(row)
                fetched += 1
                if fetched >= args.per_genre:
                    break

            offset += limit
            # Be polite with MusicBrainz rate limits.
            time.sleep(1.1)

        print(f"Fetched up to {fetched} unique artists for genre seed: {genre}")

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(all_rows, fh, ensure_ascii=False, indent=2)

    print(f"Total unique artists written: {len(all_rows)}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
