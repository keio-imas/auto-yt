from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any


MAX_AUTO_CHANNELS = 16


def list_devices() -> None:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("sounddevice is not installed. Run `uv sync`.") from exc

    print(sd.query_devices())


def probe_inputs(seconds: float) -> None:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("sounddevice is not installed. Run `uv sync`.") from exc

    if seconds <= 0:
        raise RuntimeError("--seconds must be greater than 0")

    devices = sd.query_devices()
    for device_id, device_info in enumerate(devices):
        input_channels = int(device_info.get("max_input_channels") or 0)
        if input_channels <= 0:
            continue

        try:
            stats = record_audio_stats(
                seconds=seconds,
                sample_rate=None,
                device=device_id,
                channels=None,
            )
        except RuntimeError as exc:
            print(f"{device_id}: {device_info['name']} -> error: {exc}")
            continue

        print(f"{device_id}: {device_info['name']} -> {format_audio_stats(stats)}")


def resolve_input_device_name(query: str) -> int:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("sounddevice is not installed. Run `uv sync`.") from exc

    normalized_query = query.casefold()
    matches: list[tuple[int, str]] = []
    for device_id, device_info in enumerate(sd.query_devices()):
        input_channels = int(device_info.get("max_input_channels") or 0)
        name = str(device_info.get("name") or "")
        if input_channels > 0 and normalized_query in name.casefold():
            matches.append((device_id, name))

    if not matches:
        raise RuntimeError(
            f"no input device name contains {query!r}. Run `uv run auto-yt --list-devices`."
        )
    if len(matches) > 1:
        choices = ", ".join(f"{device_id}: {name}" for device_id, name in matches)
        raise RuntimeError(f"device name {query!r} is ambiguous: {choices}")

    device_id, name = matches[0]
    print(f"Using input device {device_id}: {name}")
    return device_id


def record_wav(
    path: Path,
    *,
    seconds: float,
    sample_rate: int | None,
    device: int | None,
    channels: int | None,
) -> "AudioStats":
    mono, stats = record_audio(
        seconds=seconds,
        sample_rate=sample_rate,
        device=device,
        channels=channels,
    )
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is not installed. Run `uv sync`.") from exc

    pcm = (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(stats.sample_rate)
        wav.writeframes(pcm.tobytes())
    return stats


def record_audio_stats(
    *,
    seconds: float,
    sample_rate: int | None,
    device: int | None,
    channels: int | None,
) -> "AudioStats":
    _, stats = record_audio(
        seconds=seconds,
        sample_rate=sample_rate,
        device=device,
        channels=channels,
    )
    return stats


def record_audio(
    *,
    seconds: float,
    sample_rate: int | None,
    device: int | None,
    channels: int | None,
) -> tuple[Any, "AudioStats"]:
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("audio dependencies are not installed. Run `uv sync`.") from exc

    actual_device = device if device is not None else get_default_input_device_id(sd)
    actual_sample_rate = sample_rate or get_default_sample_rate(sd, actual_device)
    frames = int(seconds * actual_sample_rate)
    input_channels = channels or get_auto_channel_count(sd, actual_device)
    try:
        audio = sd.rec(
            frames,
            samplerate=actual_sample_rate,
            channels=input_channels,
            dtype="float32",
            device=actual_device,
        )
        sd.wait()
    except Exception as exc:
        raise RuntimeError(
            "failed to record audio. Check microphone permission, sample rate, "
            "or input device routing."
        ) from exc

    audio_array = np.asarray(audio, dtype=np.float32)
    if audio_array.ndim == 1:
        audio_array = audio_array.reshape(-1, 1)
    device_name = get_device_name(sd, actual_device)
    return select_loudest_channel(
        audio_array,
        sample_rate=actual_sample_rate,
        device=actual_device,
        device_name=device_name,
    )


def get_auto_channel_count(sd: Any, device: int | None) -> int:
    if device is None:
        return 1

    device_info = sd.query_devices(device, "input")
    max_channels = int(device_info.get("max_input_channels") or 1)
    if max_channels <= 0:
        raise RuntimeError(f"device {device} has no input channels")
    return min(max_channels, MAX_AUTO_CHANNELS)


def get_default_input_device_id(sd: Any) -> int | None:
    default_device = sd.default.device
    if isinstance(default_device, (list, tuple)) and default_device:
        input_device = default_device[0]
    else:
        input_device = default_device

    try:
        input_device_id = int(input_device)
    except (TypeError, ValueError):
        input_device_id = -1
    if input_device_id >= 0:
        return input_device_id

    device_info = sd.query_devices(kind="input")
    input_device = device_info.get("index")
    try:
        input_device_id = int(input_device)
    except (TypeError, ValueError):
        input_device_id = -1
    if input_device_id >= 0:
        return input_device_id
    return None


def get_default_sample_rate(sd: Any, device: int | None) -> int:
    if device is None:
        device_info = sd.query_devices(kind="input")
    else:
        device_info = sd.query_devices(device, "input")
    return int(device_info.get("default_samplerate") or 48_000)


def get_device_name(sd: Any, device: int | None) -> str:
    if device is None:
        device_info = sd.query_devices(kind="input")
    else:
        device_info = sd.query_devices(device, "input")
    return str(device_info.get("name") or "unknown input")


def select_loudest_channel(
    audio: Any,
    *,
    sample_rate: int,
    device: int | None,
    device_name: str,
) -> tuple[Any, "AudioStats"]:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is not installed. Run `uv sync`.") from exc

    channel_peaks = np.max(np.abs(audio), axis=0)
    channel_index = int(np.argmax(channel_peaks))
    mono = audio[:, channel_index]
    return mono, AudioStats.from_audio(
        mono,
        channel=channel_index + 1,
        input_channels=int(audio.shape[1]),
        sample_rate=sample_rate,
        device=device,
        device_name=device_name,
    )


class AudioStats:
    def __init__(
        self,
        rms: float,
        peak: float,
        channel: int,
        input_channels: int,
        sample_rate: int,
        device: int | None,
        device_name: str,
    ) -> None:
        self.rms = rms
        self.peak = peak
        self.channel = channel
        self.input_channels = input_channels
        self.sample_rate = sample_rate
        self.device = device
        self.device_name = device_name

    @classmethod
    def from_audio(
        cls,
        audio: Any,
        *,
        channel: int,
        input_channels: int,
        sample_rate: int,
        device: int | None,
        device_name: str,
    ) -> "AudioStats":
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("numpy is not installed. Run `uv sync`.") from exc

        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        return cls(
            rms=rms,
            peak=peak,
            channel=channel,
            input_channels=input_channels,
            sample_rate=sample_rate,
            device=device,
            device_name=device_name,
        )

    @property
    def rms_dbfs(self) -> float:
        return amplitude_to_dbfs(self.rms)

    @property
    def peak_dbfs(self) -> float:
        return amplitude_to_dbfs(self.peak)

    @property
    def looks_silent(self) -> bool:
        return self.peak_dbfs < -55.0

    @property
    def is_zero(self) -> bool:
        return self.peak <= 0.0


def amplitude_to_dbfs(value: float) -> float:
    if value <= 0:
        return -120.0
    return max(-120.0, 20.0 * math.log10(value))


def format_audio_stats(stats: AudioStats) -> str:
    device = "default" if stats.device is None else str(stats.device)
    return (
        f"Audio level: rms {stats.rms_dbfs:.1f} dBFS, "
        f"peak {stats.peak_dbfs:.1f} dBFS, "
        f"channel {stats.channel}/{stats.input_channels}, "
        f"sample rate {stats.sample_rate} Hz, "
        f"device {device} ({stats.device_name})"
    )
