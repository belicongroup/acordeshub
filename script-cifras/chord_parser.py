"""Utilities for parsing chord pages from cifras.com.br."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


SPAN_CHORD_RE = re.compile(
    r"<span[^>]*data-chord=\"([^\"]+)\"[^>]*>(.*?)</span>", re.IGNORECASE | re.DOTALL
)
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    without_tags = TAG_RE.sub("", text)
    return html.unescape(without_tags)


def normalize_song_text(raw_text: str) -> str:
    """Normalize song text while preserving chord alignment spacing."""
    normalized_lines: list[str] = []

    for raw_line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        # Preserve leading/internal spaces so chord columns stay aligned.
        line = raw_line.expandtabs(4).rstrip()
        if line.strip():
            normalized_lines.append(line)
            continue

        if normalized_lines and normalized_lines[-1] != "":
            normalized_lines.append("")

    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()

    return "\n".join(normalized_lines) + ("\n" if normalized_lines else "")


class _PreExtractor(HTMLParser):
    """Collect the first <pre> block from the document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_pre = False
        self._done = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        if tag.lower() == "pre":
            self._inside_pre = True
            return
        if not self._inside_pre:
            return
        attrs_string = "".join(
            f' {k}="{html.escape(v, quote=True)}"' if v is not None else f" {k}"
            for k, v in attrs
        )
        self._parts.append(f"<{tag}{attrs_string}>")

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if tag.lower() == "pre" and self._inside_pre:
            self._inside_pre = False
            self._done = True
            return
        if self._inside_pre:
            self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._inside_pre and not self._done:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._inside_pre and not self._done:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._inside_pre and not self._done:
            self._parts.append(f"&#{name};")

    def get_pre_content(self) -> str:
        return "".join(self._parts)


def extract_pre_html(document_html: str) -> str:
    """Extract the first pre block's inner HTML, or empty string."""
    parser = _PreExtractor()
    parser.feed(document_html)
    return parser.get_pre_content()


def pre_html_to_text(pre_html: str) -> str:
    """Turn pre inner HTML into plain text preserving chord tokens."""
    with_chords = SPAN_CHORD_RE.sub(lambda m: f"{m.group(1)}", pre_html)
    as_text = strip_tags(with_chords)
    return as_text


def extract_chord_text_from_html(document_html: str) -> str:
    """Extract normalized chord text from a full song page."""
    pre_html = extract_pre_html(document_html)
    if not pre_html:
        return ""
    text = pre_html_to_text(pre_html)
    return normalize_song_text(text)
