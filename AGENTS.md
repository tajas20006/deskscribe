# DeskScribe 開発ガイド

このファイルは、DeskScribeを変更する開発者およびAIコーディングエージェント向けの
実装ルールです。利用方法は `README.md`、Windows配布方法は
`WINDOWS_DISTRIBUTION.md` も参照してください。

## 目次

- [プロジェクトの目的](#プロジェクトの目的): 守るべき製品境界
- [構成と責務](#構成と責務): 変更先の選び方
- [実装の進め方](#実装の進め方): 調査から検証まで
- [重要な設計ルール](#重要な設計ルール): スレッド、設定、文字起こし
- [テストと品質確認](#テストと品質確認): 必須コマンドとテスト対応表
- [配布とユーザーデータ](#配布とユーザーデータ): EXEとローカルデータの注意
- [ドキュメント](#ドキュメント): 更新時の同期対象

## プロジェクトの目的

<!-- tags: purpose, privacy, offline -->

デスクトップ音声とマイク音声を同時取得し、ローカルの faster-whisper モデルで
文字起こしするFlet製GUIです。録音と文字起こし本文を外部サービスへ送信しません。

- モデルは利用者がローカルに用意します。アプリから自動ダウンロードしません。
- `FasterWhisperTranscriber` の `local_files_only=True` を維持してください。
- 音声、文字起こし、設定キャッシュを外部APIへ送る処理を追加しないでください。
- WAV保存は明示的に有効にした場合だけ行います。

## 構成と責務

<!-- tags: architecture, files, ownership -->

| パス | 責務 |
|---|---|
| `main.py` | GUI起動エントリポイント |
| `deskscribe/gui.py` | Fletレイアウト、イベント、設定メニュー、プレビュー、モデル事前読込 |
| `deskscribe/audio.py` | デバイス列挙、2系統キャプチャ、マイク代替経路、リサンプル、ミックス |
| `deskscribe/session.py` | 録音ライフサイクル、チャンクキュー、文字起こしワーカー、保存調停 |
| `deskscribe/transcription.py` | オフライン faster-whisper アダプター |
| `deskscribe/settings.py` | 設定データ、検証、JSONキャッシュの原子的保存 |
| `deskscribe/text.py` | `誤変換 => 正しい表記` 辞書の解析と適用 |
| `deskscribe/output.py` | 安全なファイル名、TXT/WAV保存、生成ファイルを開く処理 |
| `tests/` | 上記モジュール単位の回帰テスト |
| `packaging/windows/` | PyInstaller定義とfrozen実行時フック |
| `scripts/build_windows.ps1` | 検証、EXE、配布ZIP、SHA-256生成 |

依存方向は、原則として `gui -> session -> audio/transcription/text/output` です。
GUI固有のFletコントロールを下位モジュールへ持ち込まないでください。

## 実装の進め方

<!-- tags: workflow, tdd, review -->

1. 変更対象と既存テストを先に読み、ユーザーの録音、モデル、キャッシュ、配布物を
   作業対象から除外します。
2. 期待する振る舞いを `tests/` に追加し、修正前に意図した失敗を確認します。
3. 責務を持つ最小のモジュールへ実装します。GUIだけで済む変更をセッション層へ
   波及させないなど、境界を保ちます。
4. 関連テストを通した後、全テスト、Ruff、フォーマットを確認します。
5. 利用者の操作や既定値が変わる場合は `README.md` を更新します。配布手順が
   変わる場合は `WINDOWS_DISTRIBUTION.md` とパッケージングテストも更新します。

既存の日本語UI・エラーメッセージ・UTF-8エンコーディングを維持してください。
読みやすい直線的な実装を優先し、将来用途だけを想定した抽象化は避けます。

## 重要な設計ルール

<!-- tags: threading, flet, audio, settings, transcription -->

### Fletとスレッド

- 音声キャプチャと文字起こしはバックグラウンドスレッドで動きます。
- バックグラウンドスレッドからFletコントロールを直接更新しません。
  `TranscriptionGUI._events` にイベントを入れ、`_ui_loop` で反映してください。
- プレビュー再起動時はgeneration番号を使い、古いメーター・エラーイベントを無視します。
- ブロッキング処理は `asyncio.to_thread` へ逃がし、GUIイベントループを止めないでください。

### 音声

- デスクトップ音声とマイク音声は独立スレッドで取得します。一方の失敗で他方を
  不必要に停止させないでください。
- `DualSourceBuffer` は2系統を揃え、遅延側が止まった場合はskew上限後に無音補完します。
- SoundCardでマイクを開けない場合のPortAudio/sounddevice代替経路を維持してください。
- サンプルはモノラル`float32`、既定16 kHzです。WAVはモノラルPCM16で保存します。

### 文字起こしと辞書

- CPUは`int8`、CUDAは`float16`です。既定値はbeam size 1、15秒チャンク、
  CPU 8スレッド、過去文脈300文字です。
- ライブキャプションには生の認識結果を表示します。
- 置換辞書は録音停止後、保存する各発言本文だけに適用します。ライブ表示や
  次チャンクのプロンプトへ適用しないでください。
- タイムスタンプは辞書置換の対象にせず、`format_transcript_line` で組み立てます。

### 設定とGUI

- 設定は `$XDG_CACHE_HOME/deskscribe/settings.json`、未指定時は
  `~/.cache/deskscribe/settings.json` へ保存します。
- 新しいキャッシュ項目を追加するときは、旧JSONに項目がなくても起動できる既定値と
  型・範囲検証を `SettingsStore.load` に追加してください。
- 現在永続化するのは保存先、モデルパス、2音声デバイス、beam size、処理時間、
  CPUスレッド数、過去文脈長です。タイトルは録音ごとの入力です。
- 「保存・モデル設定」と「詳細設定」は右上の歯車から開く設定ダイアログ内に置き、
  メイン画面へ重複配置しません。設定ダイアログ内では折りたたみません。
- ライブキャプションは専用`Row`内で横方向に`expand=True`とし、カード幅に追従させます。
- 録音中はデバイス、フォルダ、モデル、詳細設定、辞書を変更不可にします。

## テストと品質確認

<!-- tags: tests, pytest, ruff, commands -->

開発環境はPython 3.14とuvです。

```powershell
uv sync
uv run pytest
uv run ruff check deskscribe tests main.py
uv run ruff format --check deskscribe tests main.py
```

`ruff check .` はワークスペース内に生成された `.uv-cache` の外部コードまで走査する
場合があるため、管理対象を上記のように明示してください。

| 変更領域 | 主なテスト |
|---|---|
| 音声デバイス・ミックス・代替入力 | `tests/test_audio.py` |
| GUI構造・設定メニュー・準備状態 | `tests/test_gui.py` |
| 録音、チャンク、ライブ表示、保存時辞書 | `tests/test_session.py` |
| faster-whisper引数とローカル限定 | `tests/test_transcription.py` |
| キャッシュ既定値・互換性・検証 | `tests/test_settings.py` |
| ファイル名、TXT/WAV、ファイルを開く | `tests/test_output.py` |
| 配布物にユーザーデータを含めないこと | `tests/test_packaging.py` |

音声バックエンドやFletをテストするときは実デバイスに依存させず、既存のfake/backend
注入パターンを使ってください。
`TranscriptionGUI` のテストでは、利用者の実キャッシュを読まないよう `tmp_path` の
`SettingsStore` を注入するか、テストプロセスの `XDG_CACHE_HOME` を一時ディレクトリへ
隔離してください。実キャッシュの値を既定値として断定しないでください。

## 配布とユーザーデータ

<!-- tags: packaging, exe, safety, user-data -->

- 配布EXEやZIPを更新するのは、ユーザーが明示的に依頼した場合だけにしてください。
- ビルドは `scripts/build_windows.ps1` を使い、手作業でPyInstallerを呼びません。
- `models/`、録音TXT/WAV、設定キャッシュ、スクリーンショット、`.agents/`、テスト、
  仮想環境を配布物へ含めないでください。
- ワークスペースにある録音TXT/WAVや利用者モデルを、テストデータとして読んだり、
  移動・削除・上書きしたりしないでください。
- 配布時はライセンス文書とSHA-256を維持し、モデルは同梱しません。

## ドキュメント

<!-- tags: documentation, maintenance -->

- 利用者向け操作、設定の場所、既定値は `README.md` に記載します。
- Windows配布利用者向けの差分は `WINDOWS_DISTRIBUTION.md` に記載します。
- 依存関係やライセンス変更は `THIRD_PARTY_LICENSES.md` と `uv.lock` を確認します。
- 詳細なコードベース索引は `.agents/summary/index.md` を入口に参照してください。
