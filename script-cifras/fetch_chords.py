#!/usr/bin/env python3
"""Fetch multi-artist song chord text from cifras.com.br."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from chord_parser import extract_chord_text_from_html, extract_pre_html


BASE_URL = "https://www.cifras.com.br"
USER_AGENT = "Mozilla/5.0 (compatible; chord-fetcher/1.0)"
ARTIST_LINK_RE = re.compile(r'href="(/[^"/?#]+)"', re.IGNORECASE)
SONG_PATH_RE = re.compile(r"/cifra/([a-z0-9-]+)/([a-z0-9-]+)", re.IGNORECASE)
INVALID_FS_DIR_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return cleaned or "unknown"


def filesystem_safe_dir_name(name: str) -> str:
    """Sanitize artist display name for use as a single path segment."""
    cleaned = INVALID_FS_DIR_CHARS.sub(" - ", name)
    cleaned = cleaned.strip(" .")
    return cleaned or "unknown"


def load_artist_names_from_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = " ".join(text.split())
    return [part.strip() for part in text.split(",") if part.strip()]


def discover_artist_url(artist_name: str) -> tuple[str, str]:
    artist_slug = slugify(artist_name)
    direct_url = f"{BASE_URL}/{artist_slug}"
    html = fetch_text(direct_url)
    if f"/{artist_slug}" in html.lower():
        return artist_slug, direct_url

    search_url = f"{BASE_URL}/busca/?q={quote_plus(artist_name)}"
    search_html = fetch_text(search_url)
    for match in ARTIST_LINK_RE.finditer(search_html):
        href = match.group(1)
        if href.startswith("/cifra/"):
            continue
        candidate_url = urljoin(BASE_URL, href)
        try:
            candidate_html = fetch_text(candidate_url)
        except Exception:
            continue
        if "## Todas as músicas" in candidate_html or "Mais Acessadas" in candidate_html:
            return href.strip("/"), candidate_url

    raise RuntimeError(f"Could not discover artist page for '{artist_name}'")


def extract_song_links(artist_slug: str, artist_page_html: str) -> list[str]:
    unique_links: list[str] = []
    seen: set[str] = set()
    for artist_part, song_part in SONG_PATH_RE.findall(artist_page_html):
        if artist_part.lower() != artist_slug.lower():
            continue
        href = f"/cifra/{artist_part}/{song_part}".rstrip("/")
        if href in seen:
            continue
        seen.add(href)
        unique_links.append(urljoin(BASE_URL, href))
    return unique_links


def filter_song_urls(
    urls: Iterable[str],
    songs_filter: list[str] | None,
    max_songs: int | None,
) -> list[str]:
    selected: list[str] = []
    wanted_slugs = {slugify(s) for s in songs_filter or []}

    for url in urls:
        song_slug = url.rstrip("/").split("/")[-1]
        if wanted_slugs and song_slug not in wanted_slugs:
            continue
        selected.append(url)
        if max_songs is not None and len(selected) >= max_songs:
            break
    return selected


def write_song_outputs(
    output_root: Path,
    artist_dir_name: str,
    song_url: str,
    song_html: str,
    *,
    chords_only: bool,
) -> tuple[Path | None, Path]:
    song_slug = song_url.rstrip("/").split("/")[-1]
    target_dir = output_root / artist_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    chord_text = extract_chord_text_from_html(song_html)
    if not chord_text:
        pre_html = extract_pre_html(song_html)
        chord_text = pre_html.strip() + "\n" if pre_html else ""
    chords_file = target_dir / f"{song_slug}.chords.txt"
    chords_file.write_text(chord_text, encoding="utf-8")

    if chords_only:
        return None, chords_file

    source_file = target_dir / f"{song_slug}.source.html"
    source_file.write_text(song_html, encoding="utf-8")
    return source_file, chords_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch chords for multiple artists.")
    parser.add_argument(
        "--artists",
        nargs="*",
        default=[],
        help='Artist names, e.g. --artists "Junior H" "Peso Pluma"',
    )
    parser.add_argument(
        "--artists-file",
        type=Path,
        default=None,
        help="Path to a comma-separated list of artist names (e.g. artist-names.md)",
    )
    parser.add_argument(
        "--songs",
        nargs="+",
        help='Optional song title filter, e.g. --songs "No Cap" "Ella"',
    )
    parser.add_argument(
        "--max-songs",
        type=int,
        default=None,
        help="Maximum number of songs per artist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected artist/song URLs without writing files",
    )
    parser.add_argument(
        "--output-dir",
        default="chord-test",
        help="Output root directory (default: chord-test)",
    )
    parser.add_argument(
        "--chords-only",
        action="store_true",
        help="Write only *.chords.txt (no *.source.html)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_dir)

    artist_names: list[str] = list(args.artists)
    if args.artists_file:
        if not args.artists_file.is_file():
            print(f"[error] --artists-file not found: {args.artists_file}", file=sys.stderr)
            return 1
        artist_names.extend(load_artist_names_from_file(args.artists_file))

    if not artist_names:
        print("[error] No artists: use --artists and/or --artists-file", file=sys.stderr)
        return 1

    for artist_name in artist_names:
        try:
            artist_slug, artist_url = discover_artist_url(artist_name)
            artist_page = fetch_text(artist_url)
        except Exception as exc:
            print(f"[error] {artist_name}: {exc}", file=sys.stderr)
            continue

        song_urls = extract_song_links(artist_slug, artist_page)
        song_urls = filter_song_urls(song_urls, args.songs, args.max_songs)

        if not song_urls:
            print(f"[warn] {artist_name}: no songs matched filters")
            continue

        out_dir = filesystem_safe_dir_name(artist_name)
        print(f"\nArtist: {artist_name} ({artist_url}) -> {output_root / out_dir}")
        for song_url in song_urls:
            if args.dry_run:
                print(f"  - {song_url}")
                continue
            try:
                song_html = fetch_text(song_url)
                src, txt = write_song_outputs(
                    output_root,
                    out_dir,
                    song_url,
                    song_html,
                    chords_only=args.chords_only,
                )
                if src is not None:
                    print(f"  - saved {src} and {txt}")
                else:
                    print(f"  - saved {txt}")
            except Exception as exc:
                print(f"  - [error] {song_url}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
