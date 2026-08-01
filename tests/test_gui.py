import asyncio
from pathlib import Path
from typing import ClassVar

import flet as ft

from deskscribe import gui
from deskscribe.audio import (
    DESKTOP,
    MICROPHONE,
    AudioCaptureError,
    AudioDevices,
    DeviceInfo,
)
from deskscribe.gui import TranscriptionGUI, format_duration
from deskscribe.session import RecordingResult
from deskscribe.settings import AppSettings, SettingsStore


class FakePage:
    def __init__(self) -> None:
        self.dialog: ft.AlertDialog | None = None

    def update(self) -> None:
        pass

    def show_dialog(self, dialog: ft.AlertDialog) -> None:
        self.dialog = dialog

    def pop_dialog(self) -> ft.AlertDialog | None:
        dialog = self.dialog
        self.dialog = None
        return dialog


def test_format_duration_uses_hours_minutes_and_seconds() -> None:
    assert format_duration(3661.9) == "01:01:01"


def test_audio_saving_is_disabled_by_default() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]

    assert app.save_audio.value is False
    assert app.open_transcript_button.visible is False


def test_header_uses_deskscribe_product_name() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]

    branding = app._header().controls[0].controls[1]

    assert branding.controls[0].value == "DeskScribe"


def test_live_caption_area_has_ten_visible_lines() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    recording = app._recording_card()
    caption_row = recording.content.content.controls[2]

    assert app.caption.min_lines == 10
    assert app.caption.max_lines == 10
    assert app.caption.expand is True
    assert caption_row.controls == [app.caption]


def test_live_caption_update_follows_the_end_of_the_full_text() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    text = "\n".join(f"キャプション {index}" for index in range(20))

    app._apply_caption(text)

    assert app.caption.value == text
    assert app.caption.selection is not None
    assert app.caption.selection.base_offset == len(text)
    assert app.caption.selection.extent_offset == len(text)


def test_cached_folders_are_restored_when_they_still_exist(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    model_path = tmp_path / "model"
    output_dir.mkdir()
    model_path.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(str(output_dir), str(model_path)))

    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]

    assert app.output_dir.value == str(output_dir)
    assert app.model_path.value == str(model_path)


def test_missing_cached_folders_are_ignored(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.save(
        AppSettings(
            str(tmp_path / "missing-output"),
            str(tmp_path / "missing-model"),
        )
    )

    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]

    assert app.output_dir.value == str(Path.cwd())
    assert app.model_path.value == ""


def test_current_settings_values_can_be_cached(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    model_path = tmp_path / "model"
    output_dir.mkdir()
    model_path.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]
    app.output_dir.value = str(output_dir)
    app.model_path.value = str(model_path)
    app.desktop_device.value = "desktop-id"
    app.microphone_device.value = "microphone-id"
    app.beam_size.value = "3"
    app.caption_seconds.value = "10"
    app.cpu_threads.value = "6"
    app.prompt_context_characters.value = "500"

    app._cache_settings()

    assert store.load() == AppSettings(
        str(output_dir),
        str(model_path),
        "desktop-id",
        "microphone-id",
        3,
        10,
        6,
        500,
    )


def test_settings_gear_opens_non_collapsible_settings_menu() -> None:
    page = FakePage()
    app = TranscriptionGUI(page)  # type: ignore[arg-type]

    main = app._main_content()
    header = main.controls[0]
    app._open_settings()

    assert app.settings_button in header.controls
    assert len(main.controls) == 4
    assert isinstance(page.dialog, ft.AlertDialog)
    menu_column = page.dialog.content.content
    assert all(
        not isinstance(control, ft.ExpansionTile) for control in menu_column.controls
    )
    assert app._settings_section().controls[0].controls[0].value == "保存・モデル設定"
    assert app._advanced_settings_section().controls[0].value == "詳細設定"

    app._close_settings()

    assert page.dialog is None


def test_advanced_settings_are_restored_in_settings_menu(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.save(
        AppSettings(
            beam_size=2,
            caption_seconds=20,
            cpu_threads=10,
            prompt_context_characters=1000,
        )
    )
    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]

    advanced = app._advanced_settings_section()

    assert isinstance(advanced, ft.Column)
    assert all(
        not isinstance(control, ft.ExpansionTile) for control in advanced.controls
    )
    assert app.beam_size.value == "2"
    assert app.caption_seconds.value == "20"
    assert app.cpu_threads.value == "10"
    assert app.prompt_context_characters.value == "1000"


def test_advanced_session_setting_selection_is_cached(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]
    app.caption_seconds.value = "20"
    app.prompt_context_characters.value = "500"

    app._on_session_setting_selected()

    cached = store.load()
    assert cached.caption_seconds == 20
    assert cached.prompt_context_characters == 500


def test_title_is_in_recording_card_instead_of_settings_menu() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]

    settings_column = app._settings_section()
    recording = app._recording_card()
    recording_column = recording.content.content
    recording_top_row = recording_column.controls[0]

    assert all(
        app.title not in getattr(control, "controls", [])
        for control in settings_column.controls
    )
    assert app.title not in recording_top_row.controls
    assert recording_column.controls[1] is app.title
    assert app.title.label == "タイトル"
    assert app.title.expand is False
    assert app.title.width == 320
    assert app.title.height == 40
    assert app.title.dense is True


def test_missing_settings_warning_lists_missing_fields(tmp_path: Path) -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app.output_dir.value = ""
    app.model_path.value = ""

    app._update_settings_warning()

    assert app.settings_warning_icon.visible is True
    assert app.settings_warning_icon.color == ft.Colors.RED
    assert "保存先フォルダ" in app.settings_warning_icon.tooltip
    assert "ローカルモデルフォルダ" in app.settings_warning_icon.tooltip

    app.output_dir.value = str(tmp_path)
    app.model_path.value = str(tmp_path)
    app._update_settings_warning()

    assert app.settings_warning_icon.visible is False


def test_cached_audio_devices_are_restored_when_available(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.save(
        AppSettings(
            desktop_device_id="desktop-cached",
            microphone_device_id="microphone-cached",
        )
    )
    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]

    app._set_device_options(
        AudioDevices(
            desktop=[
                DeviceInfo("desktop-other", "Other"),
                DeviceInfo("desktop-cached", "Cached"),
            ],
            microphones=[
                DeviceInfo("microphone-other", "Other"),
                DeviceInfo("microphone-cached", "Cached"),
            ],
        )
    )

    assert app.desktop_device.value == "desktop-cached"
    assert app.microphone_device.value == "microphone-cached"


def test_unavailable_cached_audio_devices_fall_back_to_first_option(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.save(
        AppSettings(
            desktop_device_id="desktop-missing",
            microphone_device_id="microphone-missing",
        )
    )
    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]

    app._set_device_options(
        AudioDevices(
            desktop=[DeviceInfo("desktop-first", "First")],
            microphones=[DeviceInfo("microphone-first", "First")],
        )
    )

    assert app.desktop_device.value == "desktop-first"
    assert app.microphone_device.value == "microphone-first"


def test_missing_audio_devices_show_source_specific_warnings() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]

    app._set_device_options(AudioDevices(desktop=[], microphones=[]))

    assert app.desktop_device_warning.visible is True
    assert app.desktop_device_warning.color == ft.Colors.RED
    assert "デスクトップ音声" in app.desktop_device_warning.tooltip
    assert app.microphone_device_warning.visible is True
    assert app.microphone_device_warning.color == ft.Colors.RED
    assert "マイク音声" in app.microphone_device_warning.tooltip


def test_available_audio_devices_clear_discovery_warnings() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app._set_device_options(AudioDevices(desktop=[], microphones=[]))

    app._set_device_options(
        AudioDevices(
            desktop=[DeviceInfo("desktop", "Desktop")],
            microphones=[DeviceInfo("microphone", "Microphone")],
        )
    )

    assert app.desktop_device_warning.visible is False
    assert app.microphone_device_warning.visible is False


def test_device_selection_is_cached(monkeypatch, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    app = TranscriptionGUI(FakePage(), settings_store=store)  # type: ignore[arg-type]
    app.desktop_device.value = "desktop-id"
    app.microphone_device.value = "microphone-id"

    async def skip_preview() -> None:
        pass

    monkeypatch.setattr(app, "_restart_preview", skip_preview)

    asyncio.run(app._on_device_selected())

    assert store.load().desktop_device_id == "desktop-id"
    assert store.load().microphone_device_id == "microphone-id"


def test_folder_picker_buttons_are_disabled_while_recording() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]

    app._set_recording_controls(True)

    assert app.output_dir_button.disabled is True
    assert app.model_path_button.disabled is True

    app._set_recording_controls(False)

    assert app.output_dir_button.disabled is False
    assert app.model_path_button.disabled is False


def test_recording_is_enabled_only_after_both_preview_sources_emit_audio() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app._transcriber = object()  # type: ignore[assignment]

    assert app.start_button.disabled is True

    app._apply_meter(DESKTOP, 0.25)

    assert app.desktop_meter.value == 0.25
    assert app.start_button.disabled is True

    app._apply_meter(MICROPHONE, 0.5)

    assert app.microphone_meter.value == 0.5
    assert app.start_button.disabled is False


def test_audio_ready_does_not_enable_recording_before_model_is_loaded() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]

    app._apply_meter(DESKTOP, 0.25)
    app._apply_meter(MICROPHONE, 0.5)

    assert app.start_button.disabled is True


class FakePreloadedTranscriber:
    instances: ClassVar[list[FakePreloadedTranscriber]] = []

    def __init__(
        self,
        model_path: Path,
        *,
        device: str,
        compute_type: str,
        beam_size: int = 1,
        cpu_threads: int = 8,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads
        self.loaded = False
        self.instances.append(self)

    def load(self) -> None:
        self.loaded = True


def test_model_preload_enables_recording_when_audio_is_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "deskscribe.gui.FasterWhisperTranscriber",
        FakePreloadedTranscriber,
    )
    FakePreloadedTranscriber.instances.clear()
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app.model_path.value = str(tmp_path)
    app._preview_sources_seen = {DESKTOP, MICROPHONE}

    asyncio.run(app._preload_model())

    loaded = FakePreloadedTranscriber.instances[-1]
    assert loaded.loaded is True
    assert app._transcriber is loaded
    assert loaded.beam_size == 1
    assert loaded.cpu_threads == 8
    assert app.start_button.disabled is False
    assert "準備完了" in app.status.value


class FailingPreloadTranscriber(FakePreloadedTranscriber):
    def load(self) -> None:
        raise RuntimeError("モデルを開けません")


def test_model_preload_error_keeps_recording_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "deskscribe.gui.FasterWhisperTranscriber",
        FailingPreloadTranscriber,
    )
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app.model_path.value = str(tmp_path)
    app._preview_sources_seen = {DESKTOP, MICROPHONE}

    asyncio.run(app._preload_model())

    assert app._transcriber is None
    assert app.start_button.disabled is True
    assert "モデルを開けません" in app.status.value


class FakeCapture:
    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate


class FakeRecordingSession:
    transcriber = None

    def __init__(self, config, capture, transcriber, **callbacks) -> None:
        self.config = config
        self.capture = capture
        self.elapsed_seconds = 0
        FakeRecordingSession.transcriber = transcriber

    def start(self) -> None:
        pass


def test_recording_start_reuses_preloaded_transcriber(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("deskscribe.gui.SoundCardCapture", FakeCapture)
    monkeypatch.setattr("deskscribe.gui.RecordingSession", FakeRecordingSession)
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    preloaded = FakePreloadedTranscriber(
        tmp_path,
        device="cpu",
        compute_type="int8",
    )
    preloaded.loaded = True
    app._transcriber = preloaded  # type: ignore[assignment]
    app.output_dir.value = str(tmp_path)
    app.model_path.value = str(tmp_path)
    app.desktop_device.value = "desktop"
    app.microphone_device.value = "microphone"
    app.caption_seconds.value = "20"
    app.prompt_context_characters.value = "500"

    asyncio.run(app._start_recording())

    assert FakeRecordingSession.transcriber is preloaded
    assert app._session.config.caption_seconds == 20
    assert app._session.config.prompt_context_characters == 500
    assert app._recording is True


def test_preview_error_identifies_source_and_keeps_recording_disabled() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    error = AudioCaptureError(MICROPHONE, "mic-id", AssertionError())

    app._apply_preview_error(error)

    assert app.start_button.disabled is True
    assert "マイク" in app.status.value
    assert "別のデバイス" in app.status.value
    assert app.microphone_device_warning.visible is True
    assert "マイク" in app.microphone_device_warning.tooltip


def test_audio_reception_clears_the_source_warning() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    error = AudioCaptureError(
        MICROPHONE,
        "mic-id",
        RuntimeError("PortAudio unavailable"),
    )
    app._apply_preview_error(error)

    app._apply_meter(MICROPHONE, 0.5)

    assert app.microphone_device_warning.visible is False


def test_stale_preview_events_are_ignored_after_generation_changes() -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app._transcriber = object()  # type: ignore[assignment]
    app._preview_generation = 2

    app._dispatch_event("preview_meter", (1, DESKTOP, 0.25))
    app._dispatch_event("preview_meter", (1, MICROPHONE, 0.5))

    assert app._preview_sources_seen == set()
    assert app.start_button.disabled is True


def test_saved_transcript_link_opens_the_generated_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "transcript.txt"
    path.touch()
    opened: list[Path] = []
    monkeypatch.setattr(
        "deskscribe.gui.open_file",
        lambda value: opened.append(value),
    )
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app._saved_transcript_path = path
    app.open_transcript_button.visible = True

    asyncio.run(app._open_saved_transcript())

    assert opened == [path]


class CompletedSession:
    def __init__(self, result: RecordingResult) -> None:
        self.result = result

    def stop(self) -> RecordingResult:
        return self.result


def test_successful_save_shows_the_transcript_link(tmp_path: Path) -> None:
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.touch()
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app._session = CompletedSession(  # type: ignore[assignment]
        RecordingResult(transcript_path, None, "保存済み")
    )
    app._recording = True

    async def skip_preview() -> None:
        pass

    app._restart_preview = skip_preview  # type: ignore[method-assign]

    asyncio.run(app._stop_recording())

    assert app.open_transcript_button.visible is True
    assert app._saved_transcript_path == transcript_path


def test_close_runs_shutdown_without_forcing_exit_when_it_finishes_in_time(
    monkeypatch,
) -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    calls: list[str] = []

    async def fake_shutdown() -> None:
        calls.append("shutdown")

    monkeypatch.setattr(app, "_shutdown", fake_shutdown)
    monkeypatch.setattr(gui.os, "_exit", lambda code: calls.append(f"exit-{code}"))

    asyncio.run(app._close())

    assert calls == ["shutdown"]


def test_close_forces_process_exit_when_shutdown_hangs_past_the_timeout(
    monkeypatch,
) -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    monkeypatch.setattr(gui, "CLOSE_TIMEOUT_SECONDS", 0.01)

    async def hanging_shutdown() -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr(app, "_shutdown", hanging_shutdown)
    exit_codes: list[int] = []
    monkeypatch.setattr(gui.os, "_exit", exit_codes.append)

    asyncio.run(app._close())

    assert exit_codes == [1]


def test_close_is_a_no_op_when_already_closed(monkeypatch) -> None:
    app = TranscriptionGUI(FakePage())  # type: ignore[arg-type]
    app._closed = True
    calls: list[str] = []

    async def fake_shutdown() -> None:
        calls.append("shutdown")

    monkeypatch.setattr(app, "_shutdown", fake_shutdown)

    asyncio.run(app._close())

    assert calls == []
