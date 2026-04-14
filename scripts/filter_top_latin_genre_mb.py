#!/usr/bin/env python3
"""
Filter top 1k.md to artists whose MusicBrainz tags indicate Latin music genres.
Uses MusicBrainz API (1 req/s). Cache: scripts/.mb_latin_genre_cache.json
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from http.client import RemoteDisconnected
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = ROOT / "top 1k.md"
CACHE_PATH = ROOT / "scripts" / ".mb_latin_genre_cache.json"
UA = "chrod-website/1.0 (contact: local; MusicBrainz genre filter for top chart)"

# Substrings / phrases (longer first) for tag matching (lowercased, NFKC)
PHRASES = sorted(
    [
        "latin trap",
        "trap latino",
        "latin pop",
        "latin rock",
        "latin jazz",
        "latin funk",
        "latin soul",
        "latin hip hop",
        "latin hip-hop",
        "latin alternative",
        "latin electronic",
        "latin metal",
        "latin christian",
        "latin folk",
        "latin house",
        "urbano latino",
        "música urbana",
        "musica urbana",
        "música mexicana",
        "musica mexicana",
        "regional mexicano",
        "regional mexican",
        "música tropical",
        "musica tropical",
        "bossa nova",
        "funk carioca",
        "rock en español",
        "rock en espanol",
        "narcocorrido",
        "son cubano",
        "son montuno",
        "rumba flamenca",
        "cha-cha-cha",
        "cha cha",
    ],
    key=len,
    reverse=True,
)

# Stems matched as substrings inside a single tag (after normalization)
STEMS = (
    "reggaeton",
    "bachata",
    "salsa",
    "merengue",
    "cumbia",
    "vallenato",
    "narcocorrido",
    "corrido",
    "norteño",
    "norteno",
    "duranguense",
    "mariachi",
    "ranchera",
    "ranchero",
    "tejano",
    "sertanej",
    "forró",
    "forro",
    "pagode",
    "samba",
    "bossa",
    "axé",
    "dembow",
    "perreo",
    "bachatón",
    "bachaton",
    "bolero",
    "guaracha",
    "timba",
    "mambo",
    "pasodoble",
    "flamenco",
    "rumba",
    "tango",
    "cuarteto",
    "chamamé",
    "chamame",
    "urbano",
    "mpb",
    "banda",  # regional Mexican bands; rare false positives
    "regional mexic",
    "musica mexicana",
    "música mexicana",
    "musica tropical",
    "música tropical",
    "son cubano",
    "son montuno",
    "rock en espanol",
    "rock en español",
    # Language / regional (MusicBrainz community tags; improves recall)
    "spanish",
    "español",
    "espanol",
    "portuguese",
    "português",
    "portugues",
    "brazilian",
    "brasileir",
    "mexican",
    "colombian",
    "cuban",
    "dominican",
    "puerto rican",
    "argentino",
    "argentinian",
    "peruvian",
    "chilean",
    "venezuelan",
    "guatemalan",
    "honduran",
    "salvadoran",
    "ecuadorian",
    "paraguayan",
    "uruguayan",
    "nicaraguan",
    "costa rican",
    "panamanian",
    "bolivian",
    "fado",
)


def norm_tag(s: str) -> str:
    t = unicodedata.normalize("NFKC", s).lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n"), ("ã", "a"), ("õ", "o"), ("ç", "c")):
        t = t.replace(a, b)
    return t


def tags_indicate_latin(tags: list[dict]) -> bool:
    if not tags:
        return False
    for t in tags:
        n = norm_tag(t.get("name", "") or "")
        if not n:
            continue
        if "latin" in n:
            return True
        for ph in PHRASES:
            if norm_tag(ph) in n:
                return True
        for stem in STEMS:
            if norm_tag(stem) in n:
                return True
    return False


def parse_top(raw: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    pre: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        if re.fullmatch(r"\d+\s*", raw[i].strip()) and i + 2 < n and "\t" in raw[i + 2] and re.search(r"\d", raw[i + 2]):
            break
        pre.append(raw[i])
        i += 1
    entries: list[tuple[str, str]] = []
    while i < n:
        m = re.fullmatch(r"(\d+)\s*", raw[i].strip())
        if not m or i + 2 >= n:
            break
        entries.append((raw[i + 1], raw[i + 2]))
        i += 3
    return pre, entries


def _http_json(url: str) -> dict | None:
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=75) as resp:
                return json.load(resp)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
            TimeoutError,
            RemoteDisconnected,
            ConnectionResetError,
            BrokenPipeError,
        ):
            time.sleep(min(45, 2.5 * (2**attempt)))
    return None


def mb_query(name: str) -> dict | None:
    safe = name.replace("\\", " ").replace('"', " ")
    q = f'artist:"{safe}"'
    url = "https://musicbrainz.org/ws/2/artist/?" + urllib.parse.urlencode({"query": q, "fmt": "json", "limit": "3"})
    return _http_json(url)


def mb_artist_tags(mbid: str) -> list[dict] | None:
    url = f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=tags&fmt=json"
    data = _http_json(url)
    if not data:
        return None
    return data.get("tags") or []


def best_match(data: dict | None) -> tuple[list[dict], str] | tuple[None, None]:
    if not data:
        return None, None
    artists = data.get("artists") or []
    if not artists:
        return None, None
    for a in artists:
        if a.get("score", 0) >= 92:
            tags = a.get("tags") or []
            return tags, a.get("id")
    a = artists[0]
    if a.get("score", 0) >= 85:
        return a.get("tags") or [], a.get("id")
    return None, None


def load_cache() -> dict:
    if CACHE_PATH.is_file():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_cache(c: dict) -> None:
    CACHE_PATH.write_text(json.dumps(c, ensure_ascii=False, indent=0), encoding="utf-8")


def is_latin_cached(name: str, cache: dict) -> bool | None:
    if name not in cache:
        return None
    v = cache[name]
    if isinstance(v, dict):
        return bool(v.get("latin"))
    return bool(v)


def main() -> int:
    raw = TOP.read_text(encoding="utf-8").splitlines()
    preamble, entries = parse_top(raw)
    cache = load_cache()
    # Re-score cached rows when genre rules change (no extra API calls)
    for _name, rec in list(cache.items()):
        if isinstance(rec, dict) and "tags" in rec:
            tlist = [{"name": x} for x in rec.get("tags") or []]
            rec["latin"] = tags_indicate_latin(tlist)
    kept: list[tuple[str, str]] = []
    removed: list[str] = []
    delay = 1.12

    for idx, (artist, stats) in enumerate(entries):
        prev = is_latin_cached(artist, cache)
        if prev is True:
            kept.append((artist, stats))
            continue
        if prev is False:
            removed.append(artist)
            continue

        data = mb_query(artist)
        time.sleep(delay)
        tags, mbid = best_match(data)
        if tags is not None and not tags and mbid:
            tags = mb_artist_tags(mbid)
            time.sleep(delay)

        latin = tags_indicate_latin(tags or [])
        cache[artist] = {"latin": latin, "tags": [t.get("name") for t in (tags or [])[:25]]}

        if idx % 25 == 0:
            save_cache(cache)

        if latin:
            kept.append((artist, stats))
        else:
            removed.append(artist)

    save_cache(cache)

    out: list[str] = []
    for line in preamble:
        s = line.strip()
        if s.startswith("<<< ") and s.endswith(" >>>"):
            out.append(f"<<< 1–{len(kept)} >>>")
        else:
            out.append(line)

    for i, (artist, stats) in enumerate(kept, 1):
        out.append(f"{i}\t")
        out.append(artist)
        out.append(stats)

    TOP.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Kept {len(kept)} Latin-genre (MusicBrainz tags). Removed {len(removed)}.")
    print(f"Sample removed: {removed[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
