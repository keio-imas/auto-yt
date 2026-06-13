from __future__ import annotations

import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from auto_yt.youtube import YoutubeVideo


class YoutubePlayerServer:
    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._opened = False
        self._lock = threading.Lock()
        self._video: YoutubeVideo | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("player server is not started")
        host, port = self._server.server_address
        return f"http://{host}:{port}/"

    def show(self, video: YoutubeVideo) -> None:
        self._ensure_started()
        with self._lock:
            self._video = video
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

    def state(self) -> dict[str, str | None]:
        with self._lock:
            video = self._video
        if video is None:
            return {"title": None, "url": None, "embed_url": None}
        return {
            "title": video.title,
            "url": video.url,
            "embed_url": video.embed_url,
        }

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

            def _send_json(self, data: dict[str, str | None]) -> None:
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
    <a id="link" href="{initial_url}" target="_blank" rel="noreferrer">Open on YouTube</a>
  </footer>
  <script>
    let current = null;
    const initial = {{ title: {json.dumps(initial["title"])}, url: {json.dumps(initial["url"])}, embed_url: {json.dumps(initial["embed_url"])} }};
    function render(state) {{
      const stage = document.getElementById("stage");
      const title = document.getElementById("title");
      const link = document.getElementById("link");
      title.textContent = state.title || "Waiting for song";
      link.href = state.url || "#";
      if (!state.embed_url) {{
        stage.innerHTML = '<div class="empty">Waiting for recognized music...</div>';
        current = null;
        return;
      }}
      if (state.embed_url !== current) {{
        current = state.embed_url;
        stage.innerHTML = '';
        const iframe = document.createElement('iframe');
        iframe.src = state.embed_url;
        iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
        iframe.allowFullscreen = true;
        stage.appendChild(iframe);
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
