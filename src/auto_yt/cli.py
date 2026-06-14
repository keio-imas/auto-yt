from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

from auto_yt.audio import format_audio_stats
from auto_yt.audio import list_devices
from auto_yt.audio import probe_inputs
from auto_yt.audio import record_wav
from auto_yt.audio import resolve_input_device_name
from auto_yt.player import YoutubePlayerServer
from auto_yt.recognizer import RecognizedSong
from auto_yt.recognizer import get_system_language
from auto_yt.recognizer import normalize_language
from auto_yt.recognizer import recognize_music
from auto_yt.youtube import YoutubeVideo
from auto_yt.youtube import YoutubeSearch
from auto_yt.youtube import find_youtube_search


DEFAULT_SECONDS = 6.0
DEFAULT_SAMPLE_RATE = None
DEFAULT_INTERVAL = 0.0
DEFAULT_CONFIRMATIONS = 1


def main() -> None:
    args = parse_args()

    if args.list_devices:
        list_devices()
        return
    if args.probe_inputs:
        probe_inputs(args.seconds)
        return

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130) from None
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recognize currently playing music and open the top YouTube result."
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_SECONDS,
        help=f"recording length per check in seconds (default: {DEFAULT_SECONDS:g})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"seconds to wait between checks in watch mode (default: {DEFAULT_INTERVAL:g})",
    )
    parser.add_argument(
        "--sample-rate",
        type=parse_sample_rate,
        default=DEFAULT_SAMPLE_RATE,
        help="recording sample rate, or 'auto' to use the device default (default: auto)",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="sounddevice input device id (default: system input device marked with *)",
    )
    parser.add_argument(
        "--device-name",
        default=None,
        help="case-insensitive substring of the input device name",
    )
    parser.add_argument(
        "--channels",
        default="auto",
        help="input channel count, or 'auto' to inspect all channels (default: auto)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="recognition language such as ja-JP or en-US (default: system language)",
    )
    parser.add_argument(
        "--confirmations",
        type=int,
        default=DEFAULT_CONFIRMATIONS,
        help=f"consecutive matching recognitions required before switching videos (default: {DEFAULT_CONFIRMATIONS})",
    )
    parser.add_argument(
        "--list-devices",
        "--device-list",
        action="store_true",
        help="print available audio devices and exit",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="print the YouTube URL without opening a browser",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="recognize and open a YouTube result once, then exit",
    )
    parser.add_argument(
        "--save-sample",
        type=Path,
        default=None,
        help="save the latest recorded WAV sample to this path for debugging",
    )
    parser.add_argument(
        "--probe-inputs",
        action="store_true",
        help="record each input device briefly and print measured levels",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    if args.seconds <= 0:
        raise RuntimeError("--seconds must be greater than 0")
    if args.interval < 0:
        raise RuntimeError("--interval must be 0 or greater")
    if args.confirmations <= 0:
        raise RuntimeError("--confirmations must be greater than 0")
    if args.device is not None and args.device_name is not None:
        raise RuntimeError("--device and --device-name cannot be used together")
    if args.device_name is not None:
        args.device = resolve_input_device_name(args.device_name)
    args.channels = parse_channels(args.channels)
    args.language = normalize_language(args.language or get_system_language())
    print(f"Recognition language: {args.language}")
    player = None if args.no_open else YoutubePlayerServer()

    with tempfile.TemporaryDirectory(prefix="auto-yt-") as tmp_dir:
        audio_path = Path(tmp_dir) / "sample.wav"
        if args.once:
            song = await record_and_recognize(args, audio_path)
            open_youtube_for_song(song, player=player)
            return

        if player is not None:
            player.open()
        await watch_for_song_changes(args, audio_path, player=player)


async def watch_for_song_changes(
    args: argparse.Namespace,
    audio_path: Path,
    *,
    player: YoutubePlayerServer | None,
) -> None:
    last_song_key: str | None = None
    pending_song_key: str | None = None
    pending_song: RecognizedSong | None = None
    pending_count = 0
    searches_by_song: dict[str, YoutubeSearch] = {}
    print("Watching for music changes. Press Ctrl+C to stop.")

    while True:
        loop_started_at = time.monotonic()
        try:
            song = await record_and_recognize(args, audio_path)
        except RuntimeError as exc:
            print(f"Not recognized: {exc}", file=sys.stderr)
        else:
            song_key = song.key
            if song_key == last_song_key:
                pending_song_key = None
                pending_song = None
                pending_count = 0
                print(f"No change: {song.search_query}")
            else:
                if pending_song_key == song_key:
                    pending_count += 1
                else:
                    pending_song_key = song_key
                    pending_song = song
                    pending_count = 1

                print(
                    f"Candidate change: {song.search_query} "
                    f"({pending_count}/{args.confirmations})"
                )
                if pending_count >= args.confirmations and pending_song is not None:
                    video = switch_to_song(
                        pending_song,
                        searches_by_song=searches_by_song,
                        player=player,
                    )
                    last_song_key = song_key
                    pending_song_key = None
                    pending_song = None
                    pending_count = 0

        elapsed = time.monotonic() - loop_started_at
        wait_seconds = max(0.0, args.interval - elapsed)
        if wait_seconds:
            await asyncio.sleep(wait_seconds)


async def record_and_recognize(args: argparse.Namespace, audio_path: Path) -> RecognizedSong:
    print(f"Recording {args.seconds:g} seconds...")
    stats = record_wav(
        audio_path,
        seconds=args.seconds,
        sample_rate=args.sample_rate,
        device=args.device,
        channels=args.channels,
    )
    print(format_audio_stats(stats))

    if args.save_sample is not None:
        args.save_sample.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(audio_path, args.save_sample)
        print(f"Saved sample: {args.save_sample}")

    if stats.looks_silent:
        if stats.is_zero:
            raise RuntimeError(
                "recorded audio is completely silent. On macOS, allow microphone "
                "access for your terminal app, then restart the terminal. If you "
                "are using an audio interface, also confirm its input routing."
            )
        raise RuntimeError(
            "recorded audio is almost silent. Select a working input device with "
            "`uv run auto-yt --list-devices` and `--device ID`, or increase the "
            "input volume."
        )

    print("Recognizing music...")
    return await recognize_music(
        audio_path,
        language=args.language,
        segment_duration_seconds=max(5, int(args.seconds)),
    )


def switch_to_song(
    song: RecognizedSong,
    *,
    searches_by_song: dict[str, YoutubeSearch],
    player: YoutubePlayerServer | None,
) -> YoutubeVideo:
    song_key = song.key
    search = searches_by_song.get(song_key)
    if search is not None:
        video = search.current
        print(f"Detected change: {song.search_query}")
        print(f"Top result: {video.title} ({search.position})")
        print(video.url)
        if player is not None:
            player.show(search)
        return video

    search = open_youtube_for_song(song, player=player)
    searches_by_song[song_key] = search
    return search.current


def open_youtube_for_song(
    song: RecognizedSong,
    *,
    player: YoutubePlayerServer | None,
) -> YoutubeSearch:
    query = song.search_query
    print(f"Recognized: {query}")

    print("Searching YouTube...")
    search = find_youtube_search(query)
    video = search.current
    print(f"Top result: {video.title} ({search.position})")
    print(video.url)

    if player is not None:
        player.show(search)

    return search


def parse_sample_rate(value: str) -> int | None:
    if value == "auto":
        return None
    try:
        sample_rate = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--sample-rate must be 'auto' or a positive integer") from exc
    if sample_rate <= 0:
        raise argparse.ArgumentTypeError("--sample-rate must be 'auto' or a positive integer")
    return sample_rate


def parse_channels(value: str) -> int | None:
    if value == "auto":
        return None
    try:
        channels = int(value)
    except ValueError as exc:
        raise RuntimeError("--channels must be 'auto' or a positive integer") from exc
    if channels <= 0:
        raise RuntimeError("--channels must be 'auto' or a positive integer")
    return channels


if __name__ == "__main__":
    main()
