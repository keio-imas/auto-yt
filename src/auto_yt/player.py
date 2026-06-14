from __future__ import annotations

import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from auto_yt.youtube import YoutubeSearch
from auto_yt.youtube import YoutubeVideo


FALLBACK_AFTER_SECONDS = 8


class YoutubePlayerServer:
    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._opened = False
        self._lock = threading.Lock()
        self._search: YoutubeSearch | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("player server is not started")
        host, port = self._server.server_address
        return f"http://{host}:{port}/"

    def show(self, search: YoutubeSearch) -> None:
        self._ensure_started()
        with self._lock:
            self._search = search
        if not self._opened:
            self.open()
        else:
            print("Player updated in existing window.")

    def open(self) -> None:
        self._ensure_started()
        print(f"Player page: {self.url}")
        if not self._opened:
            webbrowser.open(self.url)
            self._opened = True

    def state(self) -> dict[str, str | int | None]:
        with self._lock:
            search = self._search
            video = search.current if search is not None else None
            position = search.position if search is not None else None
        if search is None or video is None:
            return {"title": None, "url": None, "embed_url": None, "position": None}
        return {
            "title": video.title,
            "url": video.url,
            "embed_url": video.embed_url,
            "position": position,
        }

    def fallback(self) -> dict[str, str | int | None]:
        with self._lock:
            search = self._search
            video = search.advance() if search is not None else None
            position = search.position if search is not None else None

        if search is None:
            return {"ok": 0, "reason": "no active search", **self.state()}
        if video is None:
            return {"ok": 0, "reason": "no more candidates", **self.state()}

        print(f"Embed fallback: {video.title} ({position})")
        print(video.url)
        return {"ok": 1, "reason": None, **self.state()}

    def _ensure_started(self) -> None:
        if self._server is not None:
            return

        player = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/" or self.path.startswith("/?"):
                    self._send_html(player.render_html())
                    return
                if self.path == "/state":
                    self._send_json(player.state())
                    return
                if self.path == "/fallback":
                    self._send_json(player.fallback())
                    return
                self.send_error(404)

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_html(self, body: str) -> None:
                payload = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _send_json(self, data: dict[str, str | int | None]) -> None:
                payload = json.dumps(data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def render_html(self) -> str:
        initial = self.state()
        initial_title = html.escape(initial["title"] or "Waiting for song")
        initial_url = html.escape(initial["url"] or "")
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>auto-yt player</title>
  <style>
    html, body {{
      margin: 0;
      height: 100%;
      background: #111;
      color: #f5f5f5;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      display: grid;
      grid-template-rows: 1fr auto;
    }}
    iframe {{
      width: 100%;
      height: 100%;
      border: 0;
      background: #000;
    }}
    .empty {{
      display: grid;
      place-items: center;
      height: 100%;
      color: #aaa;
      font-size: 18px;
    }}
    footer {{
      display: flex;
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      background: #1b1b1b;
      border-top: 1px solid #333;
      font-size: 14px;
    }}
    a {{
      color: #8ab4ff;
    }}
  </style>
</head>
<body>
  <main id="stage"></main>
  <footer>
    <strong id="title">{initial_title}</strong>
    <span id="position"></span>
    <a id="link" href="{initial_url}" target="_blank" rel="noreferrer">Open on YouTube</a>
  </footer>
  <script src="https://www.youtube.com/iframe_api"></script>
  <script>
    let current = null;
    let player = null;
    let fallbackTimer = null;
    let fallbackInFlight = false;
    let youtubeApiReady = false;
    const fallbackAfterMs = {FALLBACK_AFTER_SECONDS * 1000};
    const initial = {{ title: {json.dumps(initial["title"])}, url: {json.dumps(initial["url"])}, embed_url: {json.dumps(initial["embed_url"])}, position: {json.dumps(initial["position"])} }};
    function onYouTubeIframeAPIReady() {{
      youtubeApiReady = true;
      refresh();
    }}
    function clearFallbackTimer() {{
      if (fallbackTimer) {{
        clearTimeout(fallbackTimer);
        fallbackTimer = null;
      }}
    }}
    function armFallbackTimer() {{
      clearFallbackTimer();
      fallbackTimer = setTimeout(requestFallback, fallbackAfterMs);
    }}
    async function requestFallback() {{
      if (fallbackInFlight) {{
        return;
      }}
      fallbackInFlight = true;
      try {{
        const response = await fetch('/fallback', {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) {{
          console.warn('fallback failed:', data.reason);
        }}
        render(data);
      }} catch (error) {{
        console.error(error);
      }} finally {{
        fallbackInFlight = false;
      }}
    }}
    function onPlayerStateChange(event) {{
      if (event.data === YT.PlayerState.PLAYING || event.data === YT.PlayerState.BUFFERING) {{
        clearFallbackTimer();
      }}
      if (event.data === YT.PlayerState.UNSTARTED || event.data === YT.PlayerState.CUED) {{
        armFallbackTimer();
      }}
    }}
    function render(state) {{
      const stage = document.getElementById("stage");
      const title = document.getElementById("title");
      const link = document.getElementById("link");
      const position = document.getElementById("position");
      title.textContent = state.title || "Waiting for song";
      link.href = state.url || "#";
      position.textContent = state.position ? `Result ${{state.position}}` : "";
      if (!state.embed_url) {{
        stage.innerHTML = '<div class="empty">Waiting for recognized music...</div>';
        current = null;
        clearFallbackTimer();
        return;
      }}
      if (state.embed_url !== current) {{
        if (!youtubeApiReady || !window.YT || !YT.Player) {{
          setTimeout(() => render(state), 250);
          return;
        }}
        current = state.embed_url;
        clearFallbackTimer();
        stage.innerHTML = '';
        const container = document.createElement('div');
        container.id = 'youtube-player';
        container.style.width = '100%';
        container.style.height = '100%';
        stage.appendChild(container);
        if (player && player.destroy) {{
          player.destroy();
          player = null;
        }}
        const videoId = new URL(state.embed_url).pathname.split('/').pop();
        player = new YT.Player('youtube-player', {{
          width: '100%',
          height: '100%',
          videoId,
          playerVars: {{
            autoplay: 1,
            mute: 1,
            playsinline: 1,
          }},
          events: {{
            onReady: (event) => {{
              event.target.mute();
              event.target.playVideo();
              armFallbackTimer();
            }},
            onStateChange: onPlayerStateChange,
            onError: requestFallback,
          }},
        }});
      }}
    }}
    async function refresh() {{
      try {{
        const response = await fetch('/state', {{ cache: 'no-store' }});
        render(await response.json());
      }} catch (error) {{
        console.error(error);
      }}
    }}
    render(initial);
    setInterval(refresh, 1000);
  </script>
</body>
</html>"""
