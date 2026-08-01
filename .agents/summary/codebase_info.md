# Codebase Information

- 名称: DeskScribe
- 種別: Python 3.14 / Flet デスクトップGUI
- ソース: `deskscribe/` の8 Pythonファイル
- テスト: `tests/` の8 Pythonファイル、現在77テスト
- エントリポイント: `main.py`
- パッケージ管理: uv / `pyproject.toml` / `uv.lock`
- 配布: PyInstallerによるWindows windowed one-file EXE

```mermaid
graph TD
    Root[deskscribe/] --> Src[deskscribe package]
    Root --> Tests[tests]
    Root --> Packaging[packaging/windows]
    Root --> Scripts[scripts]
    Root --> Docs[README and distribution docs]
    Src --> GUI[gui.py]
    Src --> Core[session.py]
    Src --> IO[audio.py and output.py]
    Src --> Config[settings.py]
    Src --> ASR[transcription.py]
    Src --> Text[text.py]
```

生成物、モデル、録音ファイル、キャッシュはコードベース分析対象外です。
