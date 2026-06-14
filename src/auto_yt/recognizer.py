from __future__ import annotations

import locale
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_LANGUAGE = "en-US"


class RecognizedSong:
    def __init__(self, title: str, artist: str | None) -> None:
        self.title = title
        self.artist = artist

    @property
    def search_query(self) -> str:
        if self.artist:
            return f"{self.title} {self.artist}"
        return self.title

    @property
    def key(self) -> str:
        return " ".join(self.search_query.casefold().split())


async def recognize_music(
    path: Path,
    *,
    language: str,
    segment_duration_seconds: int,
) -> RecognizedSong:
    try:
        from shazamio import Shazam
    except ImportError as exc:
        raise RuntimeError(
            f"failed to import shazamio dependency: {exc}. Run `uv sync`."
        ) from exc

    normalized_language = normalize_language(language)
    shazam = Shazam(
        language=normalized_language,
        endpoint_country=endpoint_country_from_language(normalized_language),
        segment_duration_seconds=segment_duration_seconds,
    )
    result = await call_shazam_recognizer(shazam, path)
    track = result.get("track") if isinstance(result, dict) else None
    if not isinstance(track, dict):
        matches = result.get("matches") if isinstance(result, dict) else None
        if isinstance(matches, list) and not matches:
            raise RuntimeError(
                "Shazam returned no matches for the recorded audio. Try a clearer "
                "music-only sample, longer `--seconds`, or inspect `--save-sample`."
            )
        raise RuntimeError("could not recognize the music from the recorded audio")

    title = track.get("title")
    artist = track.get("subtitle")
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError("recognition result did not include a song title")

    return RecognizedSong(title=title.strip(), artist=artist.strip() if isinstance(artist, str) else None)


async def call_shazam_recognizer(shazam: Any, path: Path) -> dict[str, Any]:
    for method_name in ("recognize", "recognize_song"):
        method = getattr(shazam, method_name, None)
        if method is None:
            continue

        try:
            result = await method(str(path))
        except TypeError:
            result = await method(path.read_bytes())

        if isinstance(result, dict):
            return result

    raise RuntimeError("installed shazamio version does not expose a supported recognizer")


def get_system_language() -> str:
    if platform.system() == "Darwin":
        macos_language = get_macos_system_language()
        if macos_language:
            return normalize_language(macos_language)

    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name)
        if value:
            return normalize_language(value)

    locale_name, _ = locale.getlocale()
    if locale_name:
        return normalize_language(locale_name)

    return DEFAULT_LANGUAGE


def get_macos_system_language() -> str | None:
    for command in (
        ("defaults", "read", "-g", "AppleLocale"),
        ("defaults", "read", "-g", "AppleLanguages"),
    ):
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue

        if result.returncode != 0:
            continue
        language = parse_macos_defaults_language(result.stdout)
        if language:
            return language
    return None


def parse_macos_defaults_language(value: str) -> str | None:
    for line in value.splitlines():
        candidate = line.strip().strip('",')
        if not candidate or candidate in {"(", ")"}:
            continue
        return candidate
    return None


def normalize_language(value: str) -> str:
    language = value.split(".", 1)[0].split("@", 1)[0].strip()
    if not language or language.upper() == "C":
        return DEFAULT_LANGUAGE

    parts = language.replace("_", "-").split("-")
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


def endpoint_country_from_language(language: str) -> str:
    parts = normalize_language(language).split("-")
    if len(parts) >= 2 and len(parts[1]) == 2:
        return parts[1]
    return "GB"
