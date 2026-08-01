# Interfaces

## 内部Protocol

- `session.Capture`: `start(device ids, callback, error_callback)` と `stop()`
- `session.Transcriber`: `load()` と `transcribe(audio, prompt)`
- `audio.SoundCardBackend`: デバイス列挙とID指定マイク取得
- `audio.MicrophoneFallback`: PortAudio代替キャプチャ境界

## コールバック

- 音声: `(source, np.ndarray) -> None`
- メーター: `(source, level) -> None`
- ライブキャプション: `(text) -> None`
- エラー: `(Exception) -> None`

## 外部境界

- SoundCard / sounddevice: OS音声デバイス
- faster-whisper / CTranslate2: ローカルモデル推論
- Flet: デスクトップUIとフォルダ選択
- ファイルシステム: 設定JSON、TXT、任意WAV、モデルファイル

ネットワークAPI境界はありません。モデルの取得はアプリ外の利用者操作です。
