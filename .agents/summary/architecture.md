# Architecture

DeskScribeはGUI、録音調停、音声I/O、認識、永続化を分離したローカルアプリです。

```mermaid
graph LR
    User[User] --> GUI[Flet GUI]
    GUI --> Settings[SettingsStore]
    GUI --> Preview[SoundCardCapture preview]
    GUI --> Session[RecordingSession]
    Session --> Capture[SoundCardCapture]
    Session --> Whisper[FasterWhisperTranscriber]
    Session --> Text[Replacement rules]
    Session --> Output[TXT and optional WAV]
    Capture --> Desktop[Desktop loopback]
    Capture --> Mic[Microphone]
```

音声は2本のキャプチャスレッドで取得され、`DualSourceBuffer` が同期します。
文字起こしは単一ワーカーがキューを順番に処理します。バックグラウンド結果は
GUIイベントキューを経由し、FletのUIループで反映されます。

```mermaid
sequenceDiagram
    participant C as Capture threads
    participant S as RecordingSession
    participant W as Transcription worker
    participant Q as GUI event queue
    participant U as Flet UI loop
    C->>S: source samples
    S->>W: TimedAudioChunk
    W->>Q: raw caption event
    Q->>U: dispatch on UI loop
```

重要な境界は、オフラインモデル限定、GUIとバックグラウンドスレッドの分離、
ライブ生テキストと保存時置換の分離です。
