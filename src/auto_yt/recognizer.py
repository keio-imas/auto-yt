from __future__ import annotations

from pathlib import Path
from typing import Any


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


async def recognize_music(path: Path) -> RecognizedSong:
    try:
        from shazamio import Shazam
    except ImportError as exc:
        raise RuntimeError(
            f"failed to import shazamio dependency: {exc}. Run `uv sync`."
        ) from exc

    shazam = Shazam()
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
