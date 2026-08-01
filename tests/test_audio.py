import warnings
from dataclasses import dataclass
from threading import Event, Thread, Timer
from typing import ClassVar

import numpy as np
import pytest

from deskscribe.audio import (
    DESKTOP,
    MICROPHONE,
    AudioCaptureError,
    DeviceInfo,
    DualSourceBuffer,
    SoundCardCapture,
    SoundCardDeviceProvider,
    meter_level,
    mix_audio,
    resample_mono,
    to_mono,
)


def test_to_mono_averages_all_channels() -> None:
    block = np.array([[1.0, -1.0], [0.5, 0.5]], dtype=np.float32)

    assert np.allclose(to_mono(block), np.array([0.0, 0.5], dtype=np.float32))


def test_mix_audio_averages_and_clips_sources() -> None:
    desktop = np.array([1.0, 0.5], dtype=np.float32)
    microphone = np.array([1.0, -0.5], dtype=np.float32)

    assert np.allclose(mix_audio(desktop, microphone), [1.0, 0.0])


def test_mix_audio_does_not_attenuate_an_active_source() -> None:
    desktop = np.array([0.25, -0.5], dtype=np.float32)
    microphone = np.zeros(2, dtype=np.float32)

    assert np.allclose(mix_audio(desktop, microphone), desktop)


def test_meter_level_is_bounded() -> None:
    assert meter_level(np.zeros(8, dtype=np.float32)) == 0.0
    assert meter_level(np.full(8, 2.0, dtype=np.float32)) == 1.0


def test_dual_source_buffer_yields_complete_chunks() -> None:
    buffer = DualSourceBuffer(chunk_samples=4)

    assert buffer.push("desktop", np.ones(4, dtype=np.float32)) == []
    chunks = buffer.push("microphone", np.zeros(4, dtype=np.float32))

    assert len(chunks) == 1
    assert np.allclose(chunks[0], np.ones(4, dtype=np.float32))


def test_dual_source_buffer_emits_when_one_source_exceeds_skew_limit() -> None:
    buffer = DualSourceBuffer(chunk_samples=4, max_skew_samples=2)

    chunks = buffer.push(DESKTOP, np.ones(6, dtype=np.float32))

    assert len(chunks) == 1
    assert np.allclose(chunks[0], np.ones(4, dtype=np.float32))


def test_dual_source_buffer_flushes_unequal_lengths_with_silence() -> None:
    buffer = DualSourceBuffer(chunk_samples=8)
    buffer.push("desktop", np.ones(4, dtype=np.float32))
    buffer.push("microphone", np.zeros(2, dtype=np.float32))

    flushed = buffer.flush()

    assert np.allclose(flushed, [1.0, 1.0, 1.0, 1.0])


@dataclass
class FakeDevice:
    id: str
    name: str
    isloopback: bool


class FakeBackend:
    @staticmethod
    def all_microphones(include_loopback: bool) -> list[FakeDevice]:
        assert include_loopback is True
        return [
            FakeDevice("speaker", "Speakers", True),
            FakeDevice("mic", "Microphone", False),
        ]


def test_device_provider_separates_loopback_and_microphone_inputs() -> None:
    provider = SoundCardDeviceProvider(backend=FakeBackend())

    devices = provider.list_devices()

    assert devices.desktop == [DeviceInfo("speaker", "Speakers")]
    assert devices.microphones == [DeviceInfo("mic", "Microphone")]


class FailingMicrophone:
    name = "ヘッドセット マイク (Loop120 by Shokz)"
    recorder_calls = 0

    def recorder(
        self,
        *,
        samplerate: int,
        blocksize: int,
    ) -> object:
        type(self).recorder_calls += 1
        raise AssertionError


class FailingCaptureBackend:
    @staticmethod
    def get_microphone(id: str, include_loopback: bool) -> FailingMicrophone:
        assert id == "broken-mic"
        assert include_loopback is True
        return FailingMicrophone()


class WorkingMicrophoneFallback:
    def __init__(self) -> None:
        self.device_names: list[str] = []

    def capture(
        self,
        device_name: str,
        sample_rate: int,
        block_frames: int,
        stop_event: object,
        callback,
    ) -> None:
        self.device_names.append(device_name)
        callback(np.full(block_frames, 0.25, dtype=np.float32))


def test_microphone_uses_fallback_when_soundcard_cannot_open_device() -> None:
    errors: list[Exception] = []
    received: list[np.ndarray] = []
    fallback = WorkingMicrophoneFallback()
    FailingMicrophone.recorder_calls = 0
    capture = SoundCardCapture(
        backend=FailingCaptureBackend(),
        microphone_fallback=fallback,
    )

    capture._capture(
        MICROPHONE,
        "broken-mic",
        lambda _source, samples: received.append(samples),
        errors.append,
    )

    assert fallback.device_names == ["ヘッドセット マイク (Loop120 by Shokz)"]
    assert FailingMicrophone.recorder_calls == 0
    assert len(received) == 1
    assert np.allclose(received[0], 0.25)
    assert errors == []


class FailingMicrophoneFallback:
    @staticmethod
    def capture(
        device_name: str,
        sample_rate: int,
        block_frames: int,
        stop_event: object,
        callback,
    ) -> None:
        raise RuntimeError("PortAudioでも開けません")


def test_capture_error_does_not_stop_the_other_source() -> None:
    errors: list[Exception] = []
    capture = SoundCardCapture(
        backend=FailingCaptureBackend(),
        microphone_fallback=FailingMicrophoneFallback(),
    )

    capture._capture(
        MICROPHONE,
        "broken-mic",
        lambda _source, _samples: None,
        errors.append,
    )

    assert capture._stop_event.is_set() is False
    assert len(errors) == 1
    assert isinstance(errors[0], AudioCaptureError)
    assert "マイク" in str(errors[0])
    assert "PortAudioでも開けません" in str(errors[0])


def test_resample_mono_preserves_duration_and_float32_type() -> None:
    source = np.linspace(-1, 1, 4_800, dtype=np.float32)

    result = resample_mono(source, source_rate=48_000, target_rate=16_000)

    assert result.shape == (1_600,)
    assert result.dtype == np.float32
    assert result[0] == pytest.approx(-1)
    assert result[-1] == pytest.approx(1)


class FakePortAudioBackend:
    opened_devices: ClassVar[list[int]] = []

    @staticmethod
    def query_hostapis() -> list[dict[str, str]]:
        return [
            {"name": "MME"},
            {"name": "Windows DirectSound"},
            {"name": "Windows WASAPI"},
        ]

    @staticmethod
    def query_devices() -> list[dict[str, object]]:
        name = "ヘッドセット マイク (Loop120 by Shokz)"
        return [
            {
                "name": name,
                "hostapi": 2,
                "max_input_channels": 2,
                "default_samplerate": 48_000,
            },
            {
                "name": name,
                "hostapi": 0,
                "max_input_channels": 1,
                "default_samplerate": 44_100,
            },
            {
                "name": name,
                "hostapi": 1,
                "max_input_channels": 1,
                "default_samplerate": 44_100,
            },
        ]

    @classmethod
    def InputStream(cls, *, device: int, callback, **options):
        cls.opened_devices.append(device)
        return FakePortAudioStream(callback, emits_audio=device == 2)


class FakePortAudioStream:
    def __init__(self, callback, *, emits_audio: bool) -> None:
        self._callback = callback
        self._emits_audio = emits_audio

    def __enter__(self):
        if self._emits_audio:
            self._callback(
                np.full((4_410, 1), 0.25, dtype=np.float32),
                4_410,
                None,
                None,
            )
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        pass


def test_portaudio_prefers_mme_for_matching_bluetooth_microphone() -> None:
    from deskscribe.audio import PortAudioMicrophoneCapture

    candidates = PortAudioMicrophoneCapture._candidate_devices(
        FakePortAudioBackend(),
        "ヘッドセット マイク (Loop120 by Shokz)",
    )

    assert candidates[0][2] == "MME"


def test_portaudio_tries_next_api_when_first_stream_emits_no_audio() -> None:
    from deskscribe.audio import PortAudioMicrophoneCapture

    FakePortAudioBackend.opened_devices.clear()
    stop_event = Event()
    received: list[np.ndarray] = []
    capture = PortAudioMicrophoneCapture(
        backend=FakePortAudioBackend(),
        first_block_timeout=0.01,
    )

    capture.capture(
        "ヘッドセット マイク (Loop120 by Shokz)",
        sample_rate=16_000,
        block_frames=1_600,
        stop_event=stop_event,
        callback=lambda samples: (received.append(samples), stop_event.set()),
    )

    assert FakePortAudioBackend.opened_devices[:2] == [1, 2]
    assert len(received) == 1
    assert received[0].shape == (1_600,)


class WarningRecorder:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        pass

    @staticmethod
    def record(numframes: int) -> np.ndarray:
        warnings.warn("data discontinuity in recording", RuntimeWarning)
        return np.zeros(numframes, dtype=np.float32)


class WarningDevice:
    name = "Loopback"

    @staticmethod
    def recorder(*, samplerate: int, blocksize: int) -> WarningRecorder:
        return WarningRecorder()


class WarningBackend:
    @staticmethod
    def get_microphone(id: str, include_loopback: bool) -> WarningDevice:
        return WarningDevice()


def test_known_soundcard_discontinuity_warning_is_suppressed() -> None:
    capture = SoundCardCapture(backend=WarningBackend())
    observed: list[warnings.WarningMessage]

    with warnings.catch_warnings(record=True) as observed:
        warnings.simplefilter("always")
        capture._capture(
            DESKTOP,
            "desktop",
            lambda _source, _samples: capture._stop_event.set(),
            lambda _error: None,
        )

    assert not [
        warning
        for warning in observed
        if "data discontinuity in recording" in str(warning.message)
    ]


class StuckThread:
    name = "capture-stuck"

    @staticmethod
    def join(timeout: float | None = None) -> None:
        assert timeout == 3

    @staticmethod
    def is_alive() -> bool:
        return True


def test_capture_retains_threads_that_do_not_stop_within_timeout() -> None:
    capture = SoundCardCapture(backend=FakeBackend())
    stuck = StuckThread()
    capture._threads = [stuck]  # type: ignore[list-item]

    with pytest.raises(RuntimeError, match="capture-stuck"):
        capture.stop()

    assert capture._threads == [stuck]


class LateCallbackBackend:
    callback_thread: ClassVar[Thread | None] = None

    @staticmethod
    def query_hostapis() -> list[dict[str, str]]:
        return [{"name": "MME"}]

    @staticmethod
    def query_devices() -> list[dict[str, object]]:
        return [
            {
                "name": "Late microphone",
                "hostapi": 0,
                "max_input_channels": 1,
                "default_samplerate": 16_000,
            }
        ]

    @classmethod
    def InputStream(cls, *, callback, **_options):
        return LateCallbackStream(callback)


class LateCallbackStream:
    def __init__(self, callback) -> None:
        self._callback = callback

    def __enter__(self):
        self._callback(np.zeros((4, 1), dtype=np.float32), 4, None, None)

        def emit_late_block() -> None:
            self._callback(np.zeros((4, 1), dtype=np.float32), 4, None, None)

        LateCallbackBackend.callback_thread = Timer(0.01, emit_late_block)
        LateCallbackBackend.callback_thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if LateCallbackBackend.callback_thread is not None:
            LateCallbackBackend.callback_thread.join()


def test_portaudio_surfaces_callback_error_after_first_block() -> None:
    from deskscribe.audio import PortAudioMicrophoneCapture

    stop_event = Event()
    calls = 0

    def fail_after_first_block(_samples: np.ndarray) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            stop_event.set()
            raise RuntimeError("late callback failure")

    capture = PortAudioMicrophoneCapture(
        backend=LateCallbackBackend(),
        first_block_timeout=0.1,
    )

    with pytest.raises(RuntimeError, match="late callback failure"):
        capture.capture(
            "Late microphone",
            sample_rate=16_000,
            block_frames=4,
            stop_event=stop_event,
            callback=fail_after_first_block,
        )
