# DeskScribe Knowledge Base Index

この索引をAIアシスタントの主要コンテキストとして使用してください。質問や変更内容に
応じて、次の詳細文書を追加で参照します。

| 文書 | 用途 | 主なメタデータ |
|---|---|---|
| `codebase_info.md` | 規模、言語、ディレクトリ構造 | overview, structure |
| `architecture.md` | 層構造、スレッド、依存方向 | architecture, threading |
| `components.md` | モジュール別責務 | components, ownership |
| `interfaces.md` | Protocol、コールバック、外部境界 | interfaces, callbacks |
| `data_models.md` | 設定・録音・出力データ | models, persistence |
| `workflows.md` | 起動、録音、保存、配布の流れ | workflows, lifecycle |
| `dependencies.md` | 実行・開発依存 | dependencies, licenses |
| `review_notes.md` | 整合性確認と既知の不足 | review, gaps |

## 使い分け

- GUI変更: `architecture.md`、`components.md`、`workflows.md`
- 音声障害: `components.md`、`interfaces.md`
- 設定追加: `data_models.md`、`workflows.md`
- EXE配布: `dependencies.md`、ルートの `AGENTS.md`
- 実装前の全体把握: この索引、`AGENTS.md`、対象モジュールの順に読む

例: 「詳細設定を追加したい」なら `data_models.md` で永続化範囲を確認し、
`components.md` で `gui.py` と `settings.py` の責務を確認します。
