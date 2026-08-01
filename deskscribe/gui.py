"""Flet desktop GUI for private local transcription."""

import asyncio
from pathlib import Path
from queue import Empty, SimpleQueue
from typing import Any

import flet as ft

from deskscribe.audio import (
    DESKTOP,
    MICROPHONE,
    AudioCaptureError,
    AudioDevices,
    SoundCardCapture,
    SoundCardDeviceProvider,
)
from deskscribe.output import open_file
from deskscribe.session import RecordingConfig, RecordingSession
from deskscribe.settings import (
    DEFAULT_BEAM_SIZE,
    DEFAULT_CAPTION_SECONDS,
    DEFAULT_CPU_THREADS,
    DEFAULT_PROMPT_CONTEXT_CHARACTERS,
    AppSettings,
    SettingsStore,
)
from deskscribe.text import ReplacementRuleError, parse_replacement_rules
from deskscribe.transcription import FasterWhisperTranscriber


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class TranscriptionGUI:
    def __init__(
        self,
        page: ft.Page,
        *,
        settings_store: SettingsStore | None = None,
    ) -> None:
        self.page = page
        self._settings_store = settings_store or SettingsStore()
        cached_settings = self._settings_store.load()
        cached_output_dir = Path(cached_settings.output_dir)
        cached_model_path = Path(cached_settings.model_path)
        self._preview: SoundCardCapture | None = None
        self._session: RecordingSession | None = None
        self._recording = False
        self._closed = False
        self._events: SimpleQueue[tuple[str, Any]] = SimpleQueue()
        self._preview_sources_seen: set[str] = set()
        self._preview_generation = 0
        self._transcriber: FasterWhisperTranscriber | None = None
        self._model_loading = False
        self._model_generation = 0
        self._saved_transcript_path: Path | None = None

        self.desktop_device = ft.Dropdown(
            label="デスクトップ音声デバイス",
            value=cached_settings.desktop_device_id or None,
            expand=True,
            on_select=self._on_device_selected,
        )
        self.microphone_device = ft.Dropdown(
            label="マイク音声デバイス",
            value=cached_settings.microphone_device_id or None,
            expand=True,
            on_select=self._on_device_selected,
        )
        self.desktop_device_warning = ft.Icon(
            ft.Icons.WARNING_AMBER_ROUNDED,
            color=ft.Colors.RED,
            size=24,
            visible=False,
        )
        self.microphone_device_warning = ft.Icon(
            ft.Icons.WARNING_AMBER_ROUNDED,
            color=ft.Colors.RED,
            size=24,
            visible=False,
        )
        self.desktop_meter = ft.ProgressBar(
            value=0,
            color=ft.Colors.BLUE,
            bgcolor=ft.Colors.BLUE_100,
            bar_height=10,
        )
        self.microphone_meter = ft.ProgressBar(
            value=0,
            color=ft.Colors.GREEN,
            bgcolor=ft.Colors.GREEN_100,
            bar_height=10,
        )
        self.output_dir = ft.TextField(
            label="保存先フォルダ",
            value=(
                str(cached_output_dir)
                if cached_settings.output_dir and cached_output_dir.is_dir()
                else str(Path.cwd())
            ),
            read_only=True,
            expand=True,
        )
        self.model_path = ft.TextField(
            label="ローカルモデルフォルダ",
            value=(
                str(cached_model_path)
                if cached_settings.model_path and cached_model_path.is_dir()
                else ""
            ),
            read_only=True,
            hint_text="model.bin / config.json / tokenizer.json を含むフォルダ",
            expand=True,
        )
        self.output_dir_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="保存先を選択",
            on_click=self._pick_output_dir,
        )
        self.model_path_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="ローカルモデルを選択",
            on_click=self._pick_model_dir,
        )
        self.settings_warning_icon = ft.Icon(
            ft.Icons.ERROR,
            color=ft.Colors.RED,
            size=20,
            visible=False,
        )
        self._update_settings_warning()
        self.title = ft.TextField(
            label="タイトル",
            hint_text="未入力時は「名称未設定」",
            width=320,
            height=40,
            dense=True,
            expand=False,
        )
        self.save_audio = ft.Checkbox(
            label="文字起こし後もミックス音声（WAV）を保存する",
            value=False,
        )
        self.inference_device = ft.Dropdown(
            label="推論デバイス",
            value="cpu",
            options=[
                ft.DropdownOption(key="cpu", text="CPU（int8）"),
                ft.DropdownOption(key="cuda", text="NVIDIA GPU（float16）"),
            ],
            width=240,
            on_select=self._on_inference_device_selected,
        )
        self.beam_size = ft.Dropdown(
            label="文字候補数（beam size）",
            value=str(cached_settings.beam_size),
            options=[
                ft.DropdownOption(key=str(value), text=str(value))
                for value in range(1, 11)
            ],
            width=220,
            on_select=self._on_model_setting_selected,
        )
        self.caption_seconds = ft.Dropdown(
            label="一度に処理する時間",
            value=str(cached_settings.caption_seconds),
            options=[
                ft.DropdownOption(key=str(value), text=f"{value}秒")
                for value in (5, 10, 15, 20, 30)
            ],
            width=220,
            on_select=self._on_session_setting_selected,
        )
        self.cpu_threads = ft.Dropdown(
            label="CPUスレッド数",
            value=str(cached_settings.cpu_threads),
            options=[
                ft.DropdownOption(key=str(value), text=str(value))
                for value in (1, 2, 4, 6, 8, 10, 12, 14, 16, 24, 32)
            ],
            width=220,
            on_select=self._on_model_setting_selected,
        )
        self.prompt_context_characters = ft.Dropdown(
            label="過去文脈の最大文字数",
            value=str(cached_settings.prompt_context_characters),
            options=[
                ft.DropdownOption(key=str(value), text=str(value))
                for value in (0, 100, 300, 500, 1000, 2000, 4000)
            ],
            width=220,
            on_select=self._on_session_setting_selected,
        )
        self.replacements = ft.TextField(
            label="文字列変換辞書",
            hint_text="誤変換 => 正しい表記（1行に1ルール）",
            multiline=True,
            min_lines=4,
            max_lines=7,
        )
        self.elapsed = ft.Text(
            "00:00:00",
            size=32,
            weight=ft.FontWeight.BOLD,
        )
        self.caption = ft.TextField(
            label="ライブキャプション",
            value="",
            multiline=True,
            min_lines=10,
            max_lines=10,
            read_only=True,
            expand=True,
        )
        self.status = ft.Text(
            "デバイスを確認しています…",
            color=ft.Colors.BLUE_GREY,
            selectable=True,
        )
        self.refresh_button = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="音声デバイスを再取得",
            on_click=self._refresh_devices,
        )
        self.start_button = ft.FilledButton(
            content="録音開始",
            icon=ft.Icons.FIBER_MANUAL_RECORD,
            disabled=True,
            on_click=self._start_recording,
        )
        self.stop_button = ft.Button(
            content="録音停止",
            icon=ft.Icons.STOP,
            disabled=True,
            on_click=self._stop_recording,
        )
        self.open_transcript_button = ft.TextButton(
            content="文字起こしファイルを開く",
            icon=ft.Icons.OPEN_IN_NEW,
            visible=False,
            on_click=self._open_saved_transcript,
        )
        self.settings_button = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            tooltip="設定",
            on_click=self._open_settings,
        )

    async def build(self) -> None:
        self.page.title = "DeskScribe - ローカル文字起こし"
        self.page.padding = 20
        self.page.scroll = ft.ScrollMode.AUTO
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.window.width = 1_000
        self.page.window.height = 900
        self.page.window.min_width = 720
        self.page.window.min_height = 640
        self.page.on_close = self._close
        self.page.on_disconnect = self._close

        self.page.add(self._main_content())
        self.page.run_task(self._ui_loop)
        if self.model_path.value:
            self.page.run_task(self._preload_model)
        await self._refresh_devices()

    def _main_content(self) -> ft.Column:
        return ft.Column(
            controls=[
                self._header(),
                self._device_card(),
                self._recording_card(),
                self.status,
            ],
            spacing=16,
        )

    def _header(self) -> ft.Row:
        return ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.CLOSED_CAPTION,
                            size=36,
                            color=ft.Colors.BLUE,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "DeskScribe",
                                    size=26,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    "音声とテキストを外部送信しないローカル文字起こし",
                                    color=ft.Colors.BLUE_GREY,
                                ),
                            ],
                            spacing=0,
                        ),
                    ]
                ),
                self.settings_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def _device_card(self) -> ft.Card:
        return ft.Card(
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(
                                    "音声デバイス",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                self.refresh_button,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            controls=[
                                self.desktop_device,
                                self.desktop_device_warning,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text("デスクトップ音声レベル", size=12),
                        self.desktop_meter,
                        ft.Row(
                            controls=[
                                self.microphone_device,
                                self.microphone_device_warning,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text("マイク音声レベル", size=12),
                        self.microphone_meter,
                    ]
                ),
            )
        )

    def _settings_section(self) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            "保存・モデル設定",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                        ),
                        self.settings_warning_icon,
                    ],
                    spacing=8,
                    tight=True,
                ),
                ft.Row(
                    controls=[
                        self.output_dir,
                        self.output_dir_button,
                    ]
                ),
                ft.Row(
                    controls=[
                        self.model_path,
                        self.model_path_button,
                    ]
                ),
                ft.Row(controls=[self.inference_device]),
                self.save_audio,
                self.replacements,
                ft.Text(
                    "辞書は保存時に適用します。例: Open AI => OpenAI",
                    size=12,
                    color=ft.Colors.BLUE_GREY,
                ),
            ]
        )

    def _recording_card(self) -> ft.Card:
        return ft.Card(
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text("録音時間", size=12),
                                        self.elapsed,
                                    ],
                                    spacing=0,
                                ),
                                ft.Row(
                                    controls=[
                                        self.start_button,
                                        self.stop_button,
                                        self.open_transcript_button,
                                    ]
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            wrap=True,
                        ),
                        self.title,
                        ft.Row(controls=[self.caption]),
                    ]
                ),
            )
        )

    def _advanced_settings_section(self) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Text(
                    "詳細設定",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Row(
                    controls=[
                        self.beam_size,
                        self.caption_seconds,
                        self.cpu_threads,
                        self.prompt_context_characters,
                    ],
                    wrap=True,
                ),
                ft.Text(
                    "候補数を減らし、処理時間を長くすると高速化しやすくなります。"
                    " CPUスレッド数の変更時はモデルを再読み込みします。",
                    size=12,
                    color=ft.Colors.BLUE_GREY,
                ),
            ]
        )

    def _settings_menu(self) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text("設定"),
            content=ft.Container(
                width=760,
                content=ft.Column(
                    controls=[
                        self._settings_section(),
                        ft.Divider(),
                        self._advanced_settings_section(),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("閉じる", on_click=self._close_settings),
            ],
            scrollable=True,
        )

    def _open_settings(self, _event: Any = None) -> None:
        self.page.show_dialog(self._settings_menu())

    def _close_settings(self, _event: Any = None) -> None:
        self.page.pop_dialog()

    async def _refresh_devices(self, _event: Any = None) -> None:
        if self._recording:
            return
        await asyncio.to_thread(self._stop_preview)
        self.status.value = "音声デバイスを取得しています…"
        self.refresh_button.disabled = True
        self.page.update()
        try:
            devices = await asyncio.to_thread(SoundCardDeviceProvider().list_devices)
        except Exception as error:  # noqa: BLE001 - audio backends vary by OS
            message = f"音声デバイスを取得できませんでした: {error}"
            self._set_device_warning(DESKTOP, message)
            self._set_device_warning(MICROPHONE, message)
            self.status.value = f"音声デバイスを取得できませんでした: {error}"
            self.refresh_button.disabled = False
            self.page.update()
            return
        self._set_device_options(devices)
        self.refresh_button.disabled = False
        await self._restart_preview()

    def _set_device_options(self, devices: AudioDevices) -> None:
        previous_desktop = self.desktop_device.value
        previous_microphone = self.microphone_device.value
        self.desktop_device.options = [
            ft.DropdownOption(key=device.id, text=device.name)
            for device in devices.desktop
        ]
        self.microphone_device.options = [
            ft.DropdownOption(key=device.id, text=device.name)
            for device in devices.microphones
        ]
        desktop_ids = {device.id for device in devices.desktop}
        microphone_ids = {device.id for device in devices.microphones}
        self.desktop_device.value = (
            previous_desktop
            if previous_desktop in desktop_ids
            else (devices.desktop[0].id if devices.desktop else None)
        )
        self.microphone_device.value = (
            previous_microphone
            if previous_microphone in microphone_ids
            else (devices.microphones[0].id if devices.microphones else None)
        )
        self._set_device_warning(
            DESKTOP,
            None if devices.desktop else "デスクトップ音声デバイスが見つかりません。",
        )
        self._set_device_warning(
            MICROPHONE,
            None if devices.microphones else "マイク音声デバイスが見つかりません。",
        )
        if not devices.desktop:
            self.status.value = (
                "デスクトップ音声のループバックデバイスが見つかりません。"
            )
        elif not devices.microphones:
            self.status.value = "マイク音声デバイスが見つかりません。"
        else:
            self.status.value = "音声入力を確認しています…"
        self._cache_settings()

    async def _on_device_selected(self, _event: Any = None) -> None:
        self._cache_settings()
        await self._restart_preview()

    async def _restart_preview(self) -> None:
        await asyncio.to_thread(self._stop_preview)
        self._preview_sources_seen.clear()
        self.desktop_meter.value = 0
        self.microphone_meter.value = 0
        self._update_start_readiness()
        desktop_id = self.desktop_device.value
        microphone_id = self.microphone_device.value
        if self._recording or not desktop_id or not microphone_id:
            self.page.update()
            return
        preview = SoundCardCapture()
        generation = self._preview_generation
        try:
            preview.start(
                desktop_id,
                microphone_id,
                lambda source, samples: self._preview_audio(
                    generation,
                    source,
                    samples,
                ),
                lambda error: self._queue_preview_error(generation, error),
            )
        except Exception as error:  # noqa: BLE001 - audio backends vary by OS
            self.status.value = f"音量プレビューを開始できませんでした: {error}"
        else:
            self._preview = preview
        self.page.update()

    def _preview_audio(self, generation: int, source: str, samples: Any) -> None:
        from deskscribe.audio import meter_level

        self._events.put(("preview_meter", (generation, source, meter_level(samples))))

    def _queue_preview_error(self, generation: int, error: Exception) -> None:
        self._events.put(("preview_error", (generation, error)))

    def _apply_meter(self, source: str, level: float) -> None:
        if source == DESKTOP:
            self.desktop_meter.value = level
        elif source == MICROPHONE:
            self.microphone_meter.value = level
        else:
            return
        self._set_device_warning(source, None)
        if not self._recording:
            self._preview_sources_seen.add(source)
            self._update_start_readiness()
            if not self.start_button.disabled:
                self.status.value = "準備完了（音量をプレビュー中）"
            elif (
                self._preview_sources_seen == {DESKTOP, MICROPHONE}
                and not self._model_loading
                and not self.model_path.value
            ):
                self.status.value = (
                    "音声入力は準備完了です。ローカルモデルを選択してください。"
                )

    def _apply_preview_error(self, error: Exception) -> None:
        if isinstance(error, AudioCaptureError):
            self._preview_sources_seen.discard(error.source)
            self._set_device_warning(error.source, str(error))
            if error.source == DESKTOP:
                self.desktop_meter.value = 0
            elif error.source == MICROPHONE:
                self.microphone_meter.value = 0
        self._update_start_readiness()
        self.status.value = (
            f"音声プレビューエラー: {error}。別のデバイスを選択してください。"
        )

    def _set_device_warning(self, source: str, message: str | None) -> None:
        warning = {
            DESKTOP: self.desktop_device_warning,
            MICROPHONE: self.microphone_device_warning,
        }.get(source)
        if warning is None:
            return
        warning.visible = message is not None
        warning.tooltip = message

    def _update_start_readiness(self) -> None:
        audio_ready = self._preview_sources_seen == {DESKTOP, MICROPHONE}
        self.start_button.disabled = not (
            audio_ready
            and self._transcriber is not None
            and not self._model_loading
            and not self._recording
        )

    def _stop_preview(self) -> None:
        self._preview_generation += 1
        if self._preview is not None:
            self._preview.stop()
            self._preview = None

    async def _pick_output_dir(self, _event: Any = None) -> None:
        selected = await ft.FilePicker().get_directory_path(
            dialog_title="文字起こしの保存先を選択",
            initial_directory=self.output_dir.value or None,
        )
        if selected:
            self.output_dir.value = selected
            self._update_settings_warning()
            self._cache_settings()
            self.page.update()

    async def _pick_model_dir(self, _event: Any = None) -> None:
        selected = await ft.FilePicker().get_directory_path(
            dialog_title="ローカル faster-whisper モデルを選択",
            initial_directory=self.model_path.value or None,
        )
        if selected:
            self.model_path.value = selected
            self._update_settings_warning()
            self._cache_settings()
            await self._preload_model()

    def _cache_settings(self) -> None:
        try:
            self._settings_store.save(
                AppSettings(
                    output_dir=self.output_dir.value or "",
                    model_path=self.model_path.value or "",
                    desktop_device_id=self.desktop_device.value or "",
                    microphone_device_id=self.microphone_device.value or "",
                    beam_size=int(self.beam_size.value or DEFAULT_BEAM_SIZE),
                    caption_seconds=int(
                        self.caption_seconds.value or DEFAULT_CAPTION_SECONDS
                    ),
                    cpu_threads=int(self.cpu_threads.value or DEFAULT_CPU_THREADS),
                    prompt_context_characters=int(
                        self.prompt_context_characters.value
                        or DEFAULT_PROMPT_CONTEXT_CHARACTERS
                    ),
                )
            )
        except OSError as error:
            self.status.value = f"設定を保存できませんでした: {error}"

    def _update_settings_warning(self) -> None:
        missing: list[str] = []
        output_dir = self.output_dir.value or ""
        model_path = self.model_path.value or ""
        if not output_dir or not Path(output_dir).is_dir():
            missing.append("保存先フォルダ")
        if not model_path or not Path(model_path).is_dir():
            missing.append("ローカルモデルフォルダ")
        self.settings_warning_icon.visible = bool(missing)
        self.settings_warning_icon.tooltip = (
            "不足している設定:\n" + "\n".join(f"・{name}" for name in missing)
            if missing
            else None
        )

    async def _on_inference_device_selected(self, _event: Any = None) -> None:
        if self.model_path.value:
            await self._preload_model()

    async def _on_model_setting_selected(self, _event: Any = None) -> None:
        self._cache_settings()
        if self.model_path.value:
            await self._preload_model()

    def _on_session_setting_selected(self, _event: Any = None) -> None:
        self._cache_settings()

    async def _preload_model(self) -> None:
        model_path = Path(self.model_path.value or "")
        self._model_generation += 1
        generation = self._model_generation
        self._transcriber = None
        self._model_loading = True
        self._update_start_readiness()
        self.status.value = "ローカルモデルをバックグラウンドで読み込んでいます…"
        self.page.update()

        is_cuda = self.inference_device.value == "cuda"
        transcriber = FasterWhisperTranscriber(
            model_path,
            device="cuda" if is_cuda else "cpu",
            compute_type="float16" if is_cuda else "int8",
            beam_size=int(self.beam_size.value or DEFAULT_BEAM_SIZE),
            cpu_threads=int(self.cpu_threads.value or DEFAULT_CPU_THREADS),
        )
        try:
            await asyncio.to_thread(transcriber.load)
        except Exception as error:  # noqa: BLE001 - shown safely in the GUI
            if generation != self._model_generation:
                return
            self._model_loading = False
            self._transcriber = None
            self._update_start_readiness()
            self.status.value = f"ローカルモデルを読み込めませんでした: {error}"
            self.page.update()
            return

        if generation != self._model_generation:
            return
        self._transcriber = transcriber
        self._model_loading = False
        self._update_start_readiness()
        if self.start_button.disabled:
            self.status.value = "モデル準備完了（音声入力を確認しています…）"
        else:
            self.status.value = "準備完了（モデル・音声入力を確認済み）"
        self.page.update()

    async def _start_recording(self, _event: Any = None) -> None:
        if self._model_loading:
            self.status.value = "ローカルモデルの読み込み完了を待っています…"
            self.page.update()
            return
        if self._transcriber is None:
            self.status.value = "ローカルモデルを選択して読み込みを完了してください。"
            self.page.update()
            return
        try:
            rules = parse_replacement_rules(self.replacements.value or "")
        except ReplacementRuleError as error:
            self.status.value = str(error)
            self.page.update()
            return

        await asyncio.to_thread(self._stop_preview)
        self._saved_transcript_path = None
        self.open_transcript_button.visible = False
        config = RecordingConfig(
            output_dir=Path(self.output_dir.value or ""),
            model_path=Path(self.model_path.value or ""),
            desktop_device_id=self.desktop_device.value or "",
            microphone_device_id=self.microphone_device.value or "",
            title=self.title.value or "",
            save_audio=bool(self.save_audio.value),
            replacement_rules=rules,
            caption_seconds=int(self.caption_seconds.value or DEFAULT_CAPTION_SECONDS),
            prompt_context_characters=int(
                self.prompt_context_characters.value
                or DEFAULT_PROMPT_CONTEXT_CHARACTERS
            ),
        )
        capture = SoundCardCapture(sample_rate=config.sample_rate)
        session = RecordingSession(
            config,
            capture,
            self._transcriber,
            on_caption=lambda text: self._events.put(("caption", text)),
            on_meter=lambda source, level: self._events.put(("meter", (source, level))),
            on_error=self._queue_error,
        )
        self._session = session
        self._set_recording_controls(True)
        self.stop_button.disabled = True
        self.status.value = "録音を開始しています…"
        self._apply_caption("")
        self.elapsed.value = "00:00:00"
        self.page.update()
        try:
            await asyncio.to_thread(session.start)
        except Exception as error:  # noqa: BLE001 - shown safely in the GUI
            self._session = None
            self._set_recording_controls(False)
            self.status.value = f"録音を開始できませんでした: {error}"
            self.page.update()
            await self._restart_preview()
            return
        self._recording = True
        self.stop_button.disabled = False
        self.status.value = "録音・文字起こし中（処理はローカルのみ）"
        self.page.update()

    async def _stop_recording(self, _event: Any = None) -> None:
        if self._session is None or not self._recording:
            return
        self.stop_button.disabled = True
        self.status.value = "残りの音声を文字起こしして保存しています…"
        self.page.update()
        try:
            result = await asyncio.to_thread(self._session.stop)
        except Exception as error:  # noqa: BLE001 - shown safely in the GUI
            self.status.value = f"録音停止または保存に失敗しました: {error}"
        else:
            self._apply_caption(result.text)
            self._saved_transcript_path = result.transcript_path
            self.open_transcript_button.visible = True
            saved = str(result.transcript_path)
            if result.audio_path is not None:
                saved += f" / {result.audio_path}"
            self.status.value = f"保存しました: {saved}"
        finally:
            self._recording = False
            self._session = None
            self._set_recording_controls(False)
            self.page.update()
        await self._restart_preview()

    async def _open_saved_transcript(self, _event: Any = None) -> None:
        if self._saved_transcript_path is None:
            return
        try:
            await asyncio.to_thread(open_file, self._saved_transcript_path)
        except OSError as error:
            self.status.value = f"文字起こしファイルを開けませんでした: {error}"
            self.page.update()

    def _set_recording_controls(self, recording: bool) -> None:
        self.start_button.disabled = True
        self.stop_button.disabled = not recording
        for control in (
            self.desktop_device,
            self.microphone_device,
            self.output_dir,
            self.model_path,
            self.output_dir_button,
            self.model_path_button,
            self.title,
            self.save_audio,
            self.inference_device,
            self.beam_size,
            self.caption_seconds,
            self.cpu_threads,
            self.prompt_context_characters,
            self.replacements,
            self.refresh_button,
        ):
            control.disabled = recording

    def _queue_error(self, error: Exception) -> None:
        self._events.put(("error", str(error)))

    def _apply_caption(self, text: str) -> None:
        self.caption.value = text
        end = len(text)
        self.caption.selection = ft.TextSelection(end, end)

    def _dispatch_event(self, event: str, payload: Any) -> bool:
        if event == "preview_meter":
            generation, source, level = payload
            if generation != self._preview_generation:
                return False
            self._apply_meter(source, level)
        elif event == "preview_error":
            generation, error = payload
            if generation != self._preview_generation:
                return False
            self._apply_preview_error(error)
        elif event == "meter":
            source, level = payload
            self._apply_meter(source, level)
        elif event == "caption":
            self._apply_caption(payload)
        elif event == "error":
            self.status.value = f"エラー: {payload}"
        else:
            return False
        return True

    async def _ui_loop(self) -> None:
        while not self._closed:
            changed = False
            while True:
                try:
                    event, payload = self._events.get_nowait()
                except Empty:
                    break
                changed = self._dispatch_event(event, payload) or changed
            if self._recording and self._session is not None:
                self.elapsed.value = format_duration(self._session.elapsed_seconds)
                changed = True
            if changed:
                self.page.update()
            await asyncio.sleep(0.1)

    async def _close(self, _event: Any = None) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._stop_preview)
        if self._recording and self._session is not None:
            await asyncio.to_thread(self._session.stop)


async def main(page: ft.Page) -> None:
    await TranscriptionGUI(page).build()


def run() -> None:
    ft.run(main)
