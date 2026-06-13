from __future__ import annotations


class YoutubeVideo:
    def __init__(self, title: str, url: str, video_id: str | None) -> None:
        self.title = title
        self.url = url
        self.video_id = video_id

    @property
    def embed_url(self) -> str:
        if self.video_id:
            return (
                f"https://www.youtube.com/embed/{self.video_id}"
                "?autoplay=1&mute=1&playsinline=1&enablejsapi=1"
            )
        return self.url


def find_top_youtube_video(query: str) -> YoutubeVideo:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. Run `uv sync`.") from exc

    options = {
        "quiet": True,
        "noplaylist": True,
        "extract_flat": "in_playlist",
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch1:{query}", download=False)

    entries = info.get("entries") if isinstance(info, dict) else None
    if not entries:
        raise RuntimeError("YouTube search returned no videos")

    first = entries[0]
    title = first.get("title") or query
    url = first.get("webpage_url")
    video_id = first.get("id")
    if not url and video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    if not url:
        raise RuntimeError("YouTube search result did not include a playable URL")

    return YoutubeVideo(title=str(title), url=str(url), video_id=str(video_id) if video_id else None)
