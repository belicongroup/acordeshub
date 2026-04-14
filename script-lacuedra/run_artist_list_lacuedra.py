#!/usr/bin/env python3
"""Batch fetch chords from acordes.lacuerda.net using an artist-name list."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fetch_chords_lacuerda import (  # type: ignore
    BASE_HOST,
    USER_AGENT,
    extract_chord_text_from_song_html,
    extract_song_slugs_from_artist_html,
    filesystem_safe_dir_name,
    pick_best_song_href,
    slugify,
    urljoin,
)


class ArtistTimeoutError(RuntimeError):
    pass


def _alarm_handler(_signum: int, _frame: object) -> None:
    raise ArtistTimeoutError("artist exceeded max processing time")


def fetch_text_with_timeout(url: str, timeout_sec: float) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout_sec) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_with_retries(
    url: str,
    *,
    request_timeout: float,
    max_retries: int,
    label: str = "",
) -> str:
    """Fetch quickly; default behavior is to skip on first failure."""
    max_attempts = max(1, max_retries + 1)
    for attempt in range(max_attempts):
        try:
            return fetch_text_with_timeout(url, request_timeout)
        except HTTPError as exc:
            # 403 is treated as a hard block signal: skip this target immediately.
            if exc.code == 403:
                raise
            raise
        except OSError as exc:
            if attempt < max_attempts - 1:
                wait = float(attempt + 1)
                print(
                    f"  - [retry] {label}network error: {exc}, sleeping {wait:.0f}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("unreachable")


def artist_slug_lacuerda(name: str) -> str:
    """Build LaCuerda artist slugs (underscore-separated)."""
    return slugify(name).replace("-", "_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch chords for artists from a text file and write output as "
            "output_dir/<artist_name>/<song_slug>.chords.txt only when chords exist."
        )
    )
    parser.add_argument(
        "--artists-file",
        type=Path,
        required=True,
        help="Path to newline-delimited artist names.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "chords-lc",
        help="Output root for artist folders.",
    )
    parser.add_argument(
        "--crawl-delay",
        type=float,
        default=5.0,
        metavar="SEC",
        help="Delay between HTTP requests (La Cuerda robots.txt suggests 5s).",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=12.0,
        metavar="SEC",
        help="Per-request network timeout before skipping.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retries per request (default 0 = skip immediately on failure).",
    )
    parser.add_argument(
        "--max-artist-seconds",
        type=int,
        default=0,
        metavar="SEC",
        help=(
            "Optional wall-clock cap per artist (SIGALRM). 0 = disabled (recommended for "
            "artists with many songs). When set, stops song loop and saves partial output."
        ),
    )
    parser.add_argument(
        "--max-songs-per-artist",
        type=int,
        default=None,
        metavar="N",
        help="Fetch at most N songs per artist (default: all listed on the index page).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for number of artist lines to process.",
    )
    parser.add_argument(
        "--start-line",
        type=int,
        default=1,
        help="1-based line index to start from.",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=None,
        help=(
            "Append-only checkpoint: last fully processed 1-based line in artists file. "
            "Default: <output-dir>/.lacuedra_batch_progress"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue after last line recorded in --progress-file (start-line +1).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artists_file = args.artists_file.resolve()
    output_root = args.output_dir.resolve()
    delay = max(0.0, args.crawl_delay)
    request_timeout = max(1.0, float(args.request_timeout))
    max_retries = max(0, int(args.max_retries))
    raw_max_artist = int(args.max_artist_seconds)
    use_artist_alarm = raw_max_artist > 0
    max_artist_seconds = max(5, raw_max_artist) if use_artist_alarm else 0
    max_songs_per_artist = args.max_songs_per_artist
    if max_songs_per_artist is not None and max_songs_per_artist < 1:
        print("[error] --max-songs-per-artist must be >= 1", file=sys.stderr)
        return 1
    progress_path = (
        args.progress_file.resolve()
        if args.progress_file is not None
        else (output_root / ".lacuedra_batch_progress")
    )

    if not artists_file.exists():
        print(f"[error] artists file not found: {artists_file}", file=sys.stderr)
        return 1

    start_line = args.start_line
    if args.resume:
        if progress_path.exists():
            try:
                last = int(progress_path.read_text(encoding="utf-8").strip())
                start_line = last + 1
                print(
                    f"[resume] last completed line was {last}; starting at line {start_line}",
                    flush=True,
                )
            except ValueError:
                print(
                    f"[warn] could not parse {progress_path}, using --start-line",
                    file=sys.stderr,
                )
        else:
            print(
                f"[warn] no progress file at {progress_path}, using --start-line",
                file=sys.stderr,
            )

    if start_line < 1:
        print("[error] start line must be >= 1", file=sys.stderr)
        return 1

    lines = artists_file.read_text(encoding="utf-8", errors="replace").splitlines()
    start_idx = start_line - 1
    selected = lines[start_idx:]
    if args.limit is not None:
        selected = selected[: max(0, args.limit)]

    seen_slugs: set[str] = set()
    total = len(selected)
    with_chords = 0
    consecutive_artist_403 = 0

    print(f"Artists file: {artists_file}")
    print(f"Output root:  {output_root}")
    print(f"Start line:   {start_line}")
    print(f"Lines queued: {total}")
    print(f"Progress file: {progress_path}")
    print(
        f"Max artist sec: {max_artist_seconds if use_artist_alarm else 'off'}",
        flush=True,
    )
    if max_songs_per_artist is not None:
        print(f"Max songs/artist: {max_songs_per_artist}", flush=True)

    output_root.mkdir(parents=True, exist_ok=True)

    run_state: dict[str, object] = {"file_line": None, "artist": ""}

    def _on_shutdown(signum: int, _frame: object) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        progress_raw = (
            progress_path.read_text(encoding="utf-8").strip()
            if progress_path.exists()
            else ""
        )
        line = run_state.get("file_line")
        artist = run_state.get("artist", "")
        next_line = int(progress_raw) + 1 if progress_raw.isdigit() else None
        lines_out = [
            f"{ts} shutdown signal={signum}",
            f"  artists_file={artists_file}",
            f"  batch_start_line={start_line}",
            f"  .lacuedra_batch_progress={progress_raw!r}  # last fully completed artists-file line",
            f"  current_artists_file_line={line!r} current_artist={artist!r}",
            f"  next_run: add --resume  -> starts at line {next_line}",
            f"            or --start-line {line}  -> retry that line if you prefer explicit start",
        ]
        msg = "\n".join(lines_out) + "\n"
        stop_log = output_root / ".lacuedra_stop.log"
        with stop_log.open("a", encoding="utf-8") as f:
            f.write(msg)
        print(msg, file=sys.stderr, flush=True)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, _on_shutdown)
    signal.signal(signal.SIGTERM, _on_shutdown)

    for offset, raw_name in enumerate(selected, start=1):
        file_line = start_idx + offset
        artist_name = raw_name.strip()
        run_state["file_line"] = file_line
        run_state["artist"] = artist_name
        try:
            if use_artist_alarm:
                signal.signal(signal.SIGALRM, _alarm_handler)
                signal.alarm(max_artist_seconds)
            if not artist_name:
                continue

            slug = artist_slug_lacuerda(artist_name)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            artist_url = f"{BASE_HOST}/{slug}/"
            print(f"[{offset}/{total}] line {file_line} {artist_name} -> {artist_url}")

            try:
                artist_html = fetch_with_retries(
                    artist_url,
                    request_timeout=request_timeout,
                    max_retries=max_retries,
                    label="artist page ",
                )
                consecutive_artist_403 = 0
            except HTTPError as exc:
                if exc.code == 403:
                    consecutive_artist_403 += 1
                    print(
                        "  - [skip] artist page fetch failed: HTTP 403 "
                        f"(consecutive artist 403s: {consecutive_artist_403}/4)",
                        file=sys.stderr,
                    )
                    if consecutive_artist_403 >= 4:
                        print(
                            "[stop] hit 4 consecutive artist HTTP 403 responses; ending run.",
                            file=sys.stderr,
                        )
                        return 2
                    continue
                print(f"  - [skip] artist page fetch failed: {exc}", file=sys.stderr)
                continue
            except ArtistTimeoutError as exc:
                print(f"  - [skip] artist page fetch failed: {exc}", file=sys.stderr)
                continue
            except Exception as exc:
                print(f"  - [skip] artist page fetch failed: {exc}", file=sys.stderr)
                continue
            if delay > 0:
                time.sleep(delay)

            song_slugs = extract_song_slugs_from_artist_html(artist_html)
            if not song_slugs:
                print("  - [skip] no songs found")
                continue
            if max_songs_per_artist is not None:
                song_slugs = song_slugs[:max_songs_per_artist]

            total_songs = len(song_slugs)
            songs_with_chords: dict[str, str] = {}
            for song_idx, song_slug in enumerate(song_slugs, start=1):
                if total_songs > 1 and (song_idx == 1 or song_idx % 25 == 0):
                    print(
                        f"  ... song {song_idx}/{total_songs} {song_slug}",
                        flush=True,
                    )
                versions_url = urljoin(artist_url, song_slug)
                try:
                    versions_html = fetch_with_retries(
                        versions_url,
                        request_timeout=request_timeout,
                        max_retries=max_retries,
                        label="versions ",
                    )
                    if delay > 0:
                        time.sleep(delay)
                    best_href = pick_best_song_href(song_slug, versions_html)
                    song_url = urljoin(artist_url, best_href)
                    song_html = fetch_with_retries(
                        song_url,
                        request_timeout=request_timeout,
                        max_retries=max_retries,
                        label="song ",
                    )
                    if delay > 0:
                        time.sleep(delay)
                    chord_text = extract_chord_text_from_song_html(song_html)
                    if chord_text.strip():
                        songs_with_chords[song_slug] = chord_text
                except ArtistTimeoutError as exc:
                    print(
                        f"  - [warn] artist time cap hit at '{song_slug}': {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    break
                except Exception as exc:
                    print(
                        f"  - [warn] failed song '{song_slug}': {exc}",
                        file=sys.stderr,
                        flush=True,
                    )

            if not songs_with_chords:
                print("  - [skip] no non-empty chords found")
                continue

            artist_dir = output_root / filesystem_safe_dir_name(artist_name)
            artist_dir.mkdir(parents=True, exist_ok=True)
            for song_slug, chord_text in songs_with_chords.items():
                (artist_dir / f"{song_slug}.chords.txt").write_text(
                    chord_text, encoding="utf-8"
                )
            with_chords += 1
            print(f"  - saved {len(songs_with_chords)} chord files to {artist_dir}")
        except ArtistTimeoutError as exc:
            print(f"  - [skip] {exc}", file=sys.stderr, flush=True)
        finally:
            signal.alarm(0)
            progress_path.write_text(str(file_line), encoding="utf-8")

    print(
        f"Done. Processed {total} lines in this run; created {with_chords} artist folders with chords."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
