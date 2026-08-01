# Data Models

| モデル | 主なフィールド | ライフタイム |
|---|---|---|
| `AppSettings` | フォルダ、デバイス、beam、秒数、CPUスレッド、文脈長 | ユーザー単位JSON |
| `AudioDevices` | desktop / microphones の `DeviceInfo` リスト | デバイス再取得ごと |
| `RecordingConfig` | 保存先、モデル、デバイス、タイトル、辞書、認識設定 | 録音ごと |
| `TimedAudioChunk` | float32音声、開始秒、終了秒 | 認識キュー内 |
| `RecordingResult` | TXTパス、任意WAVパス、保存済み本文 | 録音停止結果 |
| `OutputPaths` | TXT / WAV候補パス | 保存開始時 |

設定JSONは欠落・不正値を既定値へ戻します。保存は一時ファイルを書いてから置換します。
タイトル、辞書、WAV保存、推論デバイスは現在の `AppSettings` には含まれません。
