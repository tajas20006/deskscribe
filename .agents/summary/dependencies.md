# Dependencies

## Runtime

| 依存 | 用途 |
|---|---|
| Flet | デスクトップGUI、ダイアログ、フォルダ選択 |
| faster-whisper | Whisper互換の認識API |
| CTranslate2 | CPU/CUDA推論ランタイム |
| NumPy | float32音声配列とミックス |
| SoundCard | ループバックと通常音声取得 |
| sounddevice | マイク代替入力 |

`ollama` は依存一覧にありますが、現在のアプリコードでは未使用です。

## Development and packaging

- pytest / pytest-cov: 回帰テストとカバレッジ
- Ruff: lintとformat
- PyInstaller: Windows EXE
- uv: 環境とlockfile管理

ライセンス詳細はルートの `THIRD_PARTY_LICENSES.md` を参照してください。音声認識
モデルはPython依存とは別のライセンス確認が必要で、配布物には含めません。
