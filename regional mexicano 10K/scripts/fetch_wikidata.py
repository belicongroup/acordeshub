#!/usr/bin/env python3
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List


SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


def run_sparql(query: str, user_agent: str) -> Dict:
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    url = f"{SPARQL_ENDPOINT}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/sparql-results+json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def build_query(limit: int) -> str:
    # Broad Mexican music-artist pull for long-tail volume.
    return f"""
SELECT DISTINCT ?artist ?artistLabel ?genreLabel WHERE {{
  VALUES ?occupation {{
    wd:Q177220   # singer
    wd:Q639669   # musician
    wd:Q753110   # songwriter
    wd:Q36834    # composer
  }}
  ?artist wdt:P31 ?instance .
  FILTER(?instance IN (wd:Q5, wd:Q215380, wd:Q5741069, wd:Q16334295))
  OPTIONAL {{ ?artist wdt:P106 ?occ . }}
  FILTER(?instance != wd:Q5 || ?occ = ?occupation)
  {{
    ?artist wdt:P27 wd:Q96 .
  }} UNION {{
    ?artist wdt:P495 wd:Q96 .
  }}
  OPTIONAL {{ ?artist wdt:P136 ?genre . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,es". }}
}}
LIMIT {limit}
"""


def wikidata_id_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def map_rows(bindings: List[Dict]) -> List[Dict]:
    by_id: Dict[str, Dict] = {}
    for row in bindings:
        artist_uri = row.get("artist", {}).get("value", "")
        artist_name = row.get("artistLabel", {}).get("value", "").strip()
        genre = row.get("genreLabel", {}).get("value", "").strip()
        if not artist_uri or not artist_name:
            continue
        qid = wikidata_id_from_uri(artist_uri)
        if qid not in by_id:
            by_id[qid] = {
                "name": artist_name,
                "aliases": [],
                "country_signals": ["Mexico"],
                "genre_signals": [],
                "source": "wikidata",
                "source_artist_id": qid,
                "source_url": artist_uri,
                "popularity_metric": None,
            }
        if genre:
            by_id[qid]["genre_signals"].append(genre)

    rows = []
    for item in by_id.values():
        item["genre_signals"] = sorted(set(item["genre_signals"]))
        rows.append(item)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Regional Mexicano candidate artists from Wikidata.")
    parser.add_argument("--limit", type=int, default=5000, help="SPARQL LIMIT value.")
    parser.add_argument("--out", default="data/raw/wikidata_seed.json", help="Output JSON path.")
    parser.add_argument(
        "--user-agent",
        default="regional-mexicano-10k-script/1.0 (contact: local-user)",
        help="Descriptive user-agent for endpoint access.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_path = project_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    query = build_query(args.limit)
    payload = run_sparql(query, args.user_agent)
    bindings = payload.get("results", {}).get("bindings", [])
    rows = map_rows(bindings)

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    print(f"SPARQL bindings: {len(bindings)}")
    print(f"Unique artists written: {len(rows)}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
