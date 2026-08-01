# DeskScribe Windows版

## 起動方法

1. 配布ZIPを任意のローカルフォルダーへ展開します。
2. `DeskScribe.exe` をダブルクリックします。
3. 保存先、デスクトップ音声、マイク音声を選択します。
4. ローカルの faster-whisper モデルフォルダーを選択します。

Pythonやuvを配布先PCへインストールする必要はありません。

## 音声認識モデル

音声認識モデルは容量とライセンス確認の都合でEXEに同梱されていません。
利用者側で faster-whisper 用CTranslate2モデルを用意してください。モデルフォルダーには
少なくとも次のファイルが必要です。

- `model.bin`
- `config.json`
- `tokenizer.json`

例として `Systran/faster-whisper-small` を使用できます。モデル自体の利用条件は配布元で
確認してください。

## Windowsの警告

このEXEにはコード署名がありません。Windows SmartScreenが表示された場合は、配布元と
SHA-256チェックサムを確認してから実行してください。不明な配布元から受け取ったEXEは
実行しないでください。

## データとネットワーク

録音と文字起こしはローカルPC内で処理されます。選択したモデルを使用している間、
文字起こし処理のために外部APIへ音声を送信しません。

設定キャッシュは `XDG_CACHE_HOME` が設定されている場合は
`$XDG_CACHE_HOME/deskscribe/settings.json`、未設定時は
`~/.cache/deskscribe/settings.json` に保存されます。

## 動作環境

- Windows 10/11 64-bit
- デスクトップ音声を取得できるWASAPIループバックデバイス
- マイク利用権限
- GPU推論を選ぶ場合は、対応するNVIDIAドライバーとCUDAランタイム

DeskScribe本体の利用条件は `LICENSE`、詳しい依存ライブラリのライセンスは
`THIRD_PARTY_LICENSES.md` を参照してください。
