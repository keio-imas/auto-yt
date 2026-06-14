from __future__ import annotations

DEFAULT_SEARCH_LIMIT = 5


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


class YoutubeSearch:
    def __init__(self, query: str, videos: list[YoutubeVideo]) -> None:
        if not videos:
            raise RuntimeError("YouTube search returned no playable videos")
        self.query = query
        self.videos = videos
        self.index = 0

    @property
    def current(self) -> YoutubeVideo:
        return self.videos[self.index]

    @property
    def position(self) -> str:
        return f"{self.index + 1}/{len(self.videos)}"

    def advance(self) -> YoutubeVideo | None:
        if self.index + 1 >= len(self.videos):
            return None
        self.index += 1
        return self.current


def find_youtube_videos(query: str, *, limit: int = DEFAULT_SEARCH_LIMIT) -> list[YoutubeVideo]:
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
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    entries = info.get("entries") if isinstance(info, dict) else None
    if not entries:
        raise RuntimeError("YouTube search returned no videos")

    videos: list[YoutubeVideo] = []
    for entry in entries:
        title = entry.get("title") or query
        url = entry.get("webpage_url")
        video_id = entry.get("id")
        if not url and video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
        if not url:
            continue
        videos.append(
            YoutubeVideo(
                title=str(title),
                url=str(url),
                video_id=str(video_id) if video_id else None,
            )
        )

    if not videos:
        raise RuntimeError("YouTube search returned no playable URLs")

    return videos


def find_youtube_search(query: str, *, limit: int = DEFAULT_SEARCH_LIMIT) -> YoutubeSearch:
    return YoutubeSearch(query=query, videos=find_youtube_videos(query, limit=limit))


def find_top_youtube_video(query: str) -> YoutubeVideo:
    return find_youtube_search(query, limit=1).current
