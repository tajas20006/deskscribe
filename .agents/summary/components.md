# Components

| コンポーネント | 主な責務 | 注意点 |
|---|---|---|
| `TranscriptionGUI` | 画面、設定ダイアログ、準備状態、非同期イベント | UI更新はUIループのみ |
| `SoundCardDeviceProvider` | ループバックと通常マイクの分類 | platform固有名を扱う |
| `SoundCardCapture` | 2系統の独立キャプチャ | 一方の失敗を個別通知 |
| `PortAudioMicrophoneCapture` | SoundCard失敗時のマイク代替 | host API候補を順次試す |
| `DualSourceBuffer` | 2系統同期、skew制御、無音補完 | チャンク時刻の基礎 |
| `RecordingSession` | 録音、認識キュー、保存 | 再利用時にrun stateを初期化 |
| `FasterWhisperTranscriber` | モデル検証・読込・認識 | `local_files_only=True` |
| `SettingsStore` | JSON読込・検証・原子的保存 | 旧キャッシュ互換を維持 |
| text/output utilities | 辞書、ファイル名、TXT/WAV | 辞書は保存本文だけ |

GUI設定は右上の歯車ダイアログに集約され、録音タイトルとライブキャプションは
録音カードに残ります。
