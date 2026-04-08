#!/usr/bin/env python3
"""Fetch guitar chords + lyrics from acordes.lacuerda.net (La Cuerda)."""

from __future__ import annotations

import argparse
import html as html_module
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE_HOST = "https://acordes.lacuerda.net"
USER_AGENT = "Mozilla/5.0 (compatible; chord-fetcher/1.0; +https://lacuerda.net)"
INVALID_FS_DIR_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

B_MAIN_UL_RE = re.compile(
    r"<ul[^>]*\bid\s*=\s*['\"]?\s*b_main\b[^>]*>(.*?)</ul>",
    re.IGNORECASE | re.DOTALL,
)
HREF_IN_B_MAIN_RE = re.compile(
    r"""<a\s+[^>]*href\s*=\s*["']([^"'#?]+)["']""",
    re.IGNORECASE,
)
R_THUMBS_UL_RE = re.compile(
    r"""<div[^>]*\bid\s*=\s*['"]?rThumbs['"]?[^>]*>.*?<ul>(.*?)</ul>""",
    re.IGNORECASE | re.DOTALL,
)
LI_RE = re.compile(r"""<li\b[^>]*>(.*?)</li>""", re.IGNORECASE | re.DOTALL)
T_BODY_PRE_RE = re.compile(
    r"""<div[^>]*\bid\s*=\s*['"]?t_body['"]?[^>]*>\s*<pre[^>]*>(.*?)</pre\s*>""",
    re.IGNORECASE | re.DOTALL,
)


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
    cleaned = INVALID_FS_DIR_CHARS.sub(" - ", name)
    cleaned = cleaned.strip(" .")
    return cleaned or "unknown"


def normalize_artist_page_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        url = "https://" + url.lstrip("/")
        parsed = urlparse(url)
    path = parsed.path.rstrip("/") + "/"
    netloc = parsed.netloc or urlparse(BASE_HOST).netloc
    if "lacuerda.net" not in netloc:
        raise ValueError(f"Expected a lacuerda.net artist URL, got: {url!r}")
    return f"{parsed.scheme or 'https'}://{netloc}{path}"


def artist_slug_from_url(artist_url: str) -> str:
    path = urlparse(artist_url).path.strip("/").split("/")
    return path[-1] if path else ""


def extract_song_slugs_from_artist_html(page_html: str) -> list[str]:
    m = B_MAIN_UL_RE.search(page_html)
    if not m:
        return []
    block = m.group(1)
    slugs: list[str] = []
    seen: set[str] = set()
    for href_m in HREF_IN_B_MAIN_RE.finditer(block):
        href = href_m.group(1).strip()
        if not href or href.startswith(("/", "http", "javascript:")):
            continue
        if href in seen:
            continue
        seen.add(href)
        slugs.append(href)
    return slugs


def song_page_url(artist_url: str, song_slug: str) -> str:
    base = artist_url.rstrip("/") + "/"
    if song_slug.lower().endswith(".shtml"):
        return urljoin(base, song_slug)
    return urljoin(base, f"{song_slug}.shtml")


def versions_page_url(artist_url: str, song_slug: str) -> str:
    return urljoin(artist_url.rstrip("/") + "/", song_slug)


def pick_best_song_href(song_slug: str, versions_html: str) -> str:
    """
    Pick best version using:
      1) Prefer type icon class tiR (Letra y Acordes)
      2) Higher rating class cal cNN if present
      3) Keep order as final tie-breaker (site usually pre-orders by quality)
    """
    m = R_THUMBS_UL_RE.search(versions_html)
    if not m:
        return f"{song_slug}.shtml"

    best_score: tuple[int, int, int] | None = None
    best_href: str | None = None
    index = 0
    for li_m in LI_RE.finditer(m.group(1)):
        li = li_m.group(1)
        href_m = re.search(
            r"""<a\s+[^>]*href\s*=\s*["']([^"'#?]+)["']""",
            li,
            re.IGNORECASE,
        )
        if not href_m:
            continue
        href = href_m.group(1).strip()
        if not href or href.startswith(("http", "/", "javascript:")):
            continue
        if not href.lower().endswith(".shtml"):
            continue

        class_blob = " ".join(
            re.findall(
                r"""class\s*=\s*["']([^"']+)["']""",
                li,
                re.IGNORECASE,
            )
        )
        has_tir = 1 if re.search(r"\btiR\b", class_blob, re.IGNORECASE) else 0
        rating_match = re.search(r"\bcal\s+c(\d{1,3})\b", class_blob, re.IGNORECASE)
        rating = int(rating_match.group(1)) if rating_match else 0
        # earlier entry should win ties
        score = (has_tir, rating, -index)
        if best_score is None or score > best_score:
            best_score = score
            best_href = href
        index += 1

    if best_href:
        return best_href
    return f"{song_slug}.shtml"


def extract_chord_text_from_song_html(song_html: str) -> str:
    m = T_BODY_PRE_RE.search(song_html)
    if not m:
        return ""
    pre_inner = m.group(1)
    text = _pre_inner_html_to_plain(pre_inner)
    return text.rstrip() + "\n" if text.strip() else ""


def _pre_inner_html_to_plain(fragment: str) -> str:
    s = fragment
    s = re.sub(r"<div\s*>\s*</div\s*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<a\b[^>]*>(.*?)</a\s*>", r"\1", s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_module.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s


def filter_song_slugs(
    slugs: Iterable[str],
    songs_filter: list[str] | None,
    max_songs: int | None,
) -> list[str]:
    selected: list[str] = []
    wanted = {slugify(s) for s in songs_filter or []}

    for slug in slugs:
        if wanted and slugify(slug) not in wanted:
            continue
        selected.append(slug)
        if max_songs is not None and len(selected) >= max_songs:
            break
    return selected


def write_song_outputs(
    output_root: Path,
    artist_dir_name: str,
    song_slug: str,
    song_html: str,
    *,
    chords_only: bool,
) -> tuple[Path | None, Path]:
    target_dir = output_root / artist_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    chord_text = extract_chord_text_from_song_html(song_html)
    chords_file = target_dir / f"{song_slug}.chords.txt"
    chords_file.write_text(chord_text, encoding="utf-8")

    if chords_only:
        return None, chords_file

    source_file = target_dir / f"{song_slug}.source.html"
    source_file.write_text(song_html, encoding="utf-8")
    return source_file, chords_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch chords from acordes.lacuerda.net for one artist page URL.",
    )
    parser.add_argument(
        "artist_url",
        nargs="?",
        default=None,
        help=f"Artist index URL, e.g. {BASE_HOST}/peso_pluma/",
    )
    parser.add_argument(
        "--artist-url",
        dest="artist_url_flag",
        default=None,
        help="Same as positional artist_url (optional if position is used).",
    )
    parser.add_argument(
        "--artist-name",
        default=None,
        help="Folder name under output (default: URL slug, e.g. peso_pluma).",
    )
    parser.add_argument(
        "--songs",
        nargs="+",
        help='Optional song slug filter, e.g. --songs la_patrulla mami',
    )
    parser.add_argument(
        "--max-songs",
        type=int,
        default=None,
        help="Maximum number of songs to fetch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print song URLs without writing files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "chords-lacuedra",
        help="Output root (default: ../chords-lacuedra next to script-lacuedra)",
    )
    parser.add_argument(
        "--chords-only",
        action="store_true",
        help="Write only *.chords.txt (no *.source.html)",
    )
    parser.add_argument(
        "--crawl-delay",
        type=float,
        default=5.0,
        metavar="SEC",
        help="Seconds to sleep between HTTP requests (lacuerda robots.txt Crawl-delay: 5; use 0 to disable)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artist_url = args.artist_url or args.artist_url_flag
    if not artist_url:
        print(
            "[error] Missing artist URL: pass e.g. "
            f"{BASE_HOST}/peso_pluma/ as the first argument or --artist-url",
            file=sys.stderr,
        )
        return 1

    try:
        artist_url = normalize_artist_page_url(artist_url)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    slug = artist_slug_from_url(artist_url)
    if not slug:
        print("[error] Could not parse artist slug from URL", file=sys.stderr)
        return 1

    out_dir_name = (
        filesystem_safe_dir_name(args.artist_name)
        if args.artist_name
        else slug
    )
    output_root = args.output_dir.resolve()

    try:
        artist_page = fetch_text(artist_url)
    except Exception as exc:
        print(f"[error] Failed to load artist page: {exc}", file=sys.stderr)
        return 1

    song_slugs = extract_song_slugs_from_artist_html(artist_page)
    song_slugs = filter_song_slugs(song_slugs, args.songs, args.max_songs)

    if not song_slugs:
        print(
            "[warn] No songs found (check that the page lists songs in ul#b_main, "
            "or relax --songs filter).",
            file=sys.stderr,
        )
        return 0

    delay = max(0.0, args.crawl_delay)
    if delay > 0 and not args.dry_run:
        print(f"(crawl-delay {delay}s between requests)", file=sys.stderr)

    print(f"Artist: {artist_url} -> {output_root / out_dir_name}")
    for song_slug in song_slugs:
        versions_url = versions_page_url(artist_url, song_slug)
        song_url = song_page_url(artist_url, song_slug)
        if args.dry_run:
            print(f"  - {song_url}")
            continue
        if delay > 0:
            time.sleep(delay)
        try:
            versions_html = fetch_text(versions_url)
            best_href = pick_best_song_href(song_slug, versions_html)
            song_url = urljoin(artist_url.rstrip("/") + "/", best_href)
            if delay > 0:
                time.sleep(delay)
            song_html = fetch_text(song_url)
            src, txt = write_song_outputs(
                output_root,
                out_dir_name,
                song_slug,
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
