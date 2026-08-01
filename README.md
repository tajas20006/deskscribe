# AutoTExtract

デスクトップ音声とマイク音声を同時に取得し、ローカルの
faster-whisperモデルで文字起こしするFlet製デスクトップGUIです。
音声・文字起こしテキストを外部サービスへ送信しません。

## 主な機能

- デスクトップ音声（ループバック）とマイク音声の同時録音
- GUIからのデバイス選択と、録音前・録音中の音量メーター
- 録音開始・停止、録音時間、最新内容へ自動追従する10行のライブキャプション
- ローカルモデルフォルダとCPU/GPU推論の選択
- 保存先、タイトル、音声保存有無の設定（音声保存はデフォルトOFF）
- `誤変換 => 正しい表記` 形式の保存時置換辞書
- 各発言区間を `[HH:MM:SS - HH:MM:SS] 発言` 形式で記録
- `YYYYMMDD-HHMMSS_タイトル.txt` 形式のUTF-8テキスト保存
- 保存完了後、GUIから生成された文字起こしファイルを直接開くリンク
- オプションで同名のモノラルPCM WAVを保存

タイトルが空の場合は `名称未設定` になります。

## セットアップ

Python 3.14と[uv](https://docs.astral.sh/uv/)を使用します。

```bash
uv sync
uv run python main.py
```

## 基本操作

1. アプリを起動し、画面右上の歯車ボタンを押して設定メニューを開きます。
2. 「保存・モデル設定」で、保存先フォルダとローカルの faster-whisper
   モデルフォルダを選択します。CPU/GPU、WAV保存、保存時置換辞書もここで設定します。
3. 必要に応じて「詳細設定」で、文字候補数、処理時間、CPUスレッド数、
   過去文脈の長さを調整し、「閉じる」でメイン画面へ戻ります。
4. メイン画面でデスクトップ音声とマイク音声を選び、両方の音量メーターが
   反応することを確認します。利用できないデバイスには赤い警告が表示されます。
5. 録音ごとのタイトルを入力し、モデルと音声入力の準備完了後に「録音開始」を押します。
6. 「録音停止」を押すと、置換辞書を適用した文字起こしファイルが保存されます。

設定メニューへ移動した項目は、メイン画面には表示されません。モデルを変更するときは
右上の歯車ボタンから設定メニューを開いてください。

LinuxのFletデスクトップ版でフォルダ選択を使う場合は、Zenityが必要です。

```bash
sudo apt install zenity
```

## ローカルモデル

faster-whisper用のCTranslate2モデルを、事前にローカルへ用意します。
GUIでは次のファイルを含むディレクトリを選択してください。

- `model.bin`
- `config.json`
- `tokenizer.json`

モデルフォルダは、画面右上の歯車ボタンから「保存・モデル設定」を開き、
「ローカルモデルフォルダ」のフォルダボタンで選択します。

モデルフォルダを選択すると、GUIを操作できる状態のままバックグラウンドで
モデルを読み込みます。音声入力とモデルの両方が準備できると「録音開始」が
有効になり、録音開始時は読み込み済みモデルをそのまま使用します。
推論デバイスを変更した場合は、選択したデバイス向けにモデルを再読み込みします。

アプリはモデル名による自動ダウンロードを行いません。
`local_files_only=True` を常に指定し、上記ファイルがローカルにない場合は
録音を開始せずエラーにします。選んだモデル自体のライセンスと商用利用条件は、
モデル配布元で別途確認してください。

CPUでは `int8`、NVIDIA GPUでは `float16` を選べます。GPU利用には
faster-whisper/CTranslate2が要求するCUDAランタイムが別途必要です。

## プラットフォーム上の注意

- Windows: SoundCardのWASAPIループバックでスピーカー出力を取得します。
- Linux: PulseAudio/PipeWireが公開するmonitor入力が必要です。
- macOS: 利用可能なループバック入力が一覧に出る構成が必要です。必要に応じて
  BlackHoleなど、組織で利用条件を確認済みの仮想オーディオデバイスを用意します。

OSのプライバシー設定でマイク権限が必要です。デスクトップ音声またはマイクが
一覧に出ない場合は、OS側の音声デバイスと権限を先に確認してください。

## プライバシー

- 録音と文字起こしは同じマシン内で処理します。
- アプリコードに外部API呼び出しやアップロード処理はありません。
- WAV保存はデフォルトで無効です。
- テキストと、明示的に有効にした場合のWAVだけが選択フォルダに残ります。

初回セットアップ時の `uv sync` と、利用者が別途行うモデル取得にはネットワークが
必要な場合があります。録音開始後の処理にはネットワークを使用しません。

## 依存ライブラリのライセンス

追加した主要ライブラリはいずれも商用利用可能な許諾です。

- SoundCard: BSD-3-Clause
- sounddevice: MIT
- faster-whisper: MIT
- NumPy: BSD-3-Clause
- Flet（既存依存）: Apache-2.0

再配布時は `uv.lock` に含まれる推移依存も含め、各ライセンス本文とNOTICE要件を
確認してください。今回確認したバージョン別の一覧は
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) に記録しています。

## 開発時の確認

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Windows配布用EXE

Windows上で次を実行すると、Pythonを別途必要としない配布ZIPを `dist/` に生成します。

```powershell
.\scripts\build_windows.ps1
```

生成物には `AutoTExtract.exe`、利用手順、依存ライブラリのライセンス、SHA-256
チェックサムが含まれます。音声認識モデルは同梱されないため、利用者が起動後にローカル
モデルフォルダーを選択します。詳しくは
[`WINDOWS_DISTRIBUTION.md`](WINDOWS_DISTRIBUTION.md)を参照してください。

## 設定キャッシュと設定メニュー

GUIで選択した保存先フォルダ、ローカルモデルフォルダ、デスクトップ音声
デバイス、マイク音声デバイスは、次回起動時にも自動的に復元されます。
設定は標準の `XDG_CACHE_HOME` が指定されている場合はその配下へ保存し、未指定時は
ユーザーのホームディレクトリ配下へ保存します。

```text
$XDG_CACHE_HOME/autotextract/settings.json
~/.cache/autotextract/settings.json
```

保存済みのモデルフォルダが存在する場合は、起動後にバックグラウンドで
モデルを読み込みます。移動または削除されたフォルダや、接続されていない
音声デバイスは安全に無視され、現在利用できる候補へ切り替わります。

画面右上の歯車ボタンを押すと設定メニューが開き、「保存・モデル設定」と
「詳細設定」が常時展開された状態で表示されます。必須設定が不足している場合は
「保存・モデル設定」の見出し横に赤い警告アイコンが表示され、マウスを重ねると
不足項目を確認できます。

| 設定グループ | 設定できる内容 |
|---|---|
| 保存・モデル設定 | 保存先、ローカルモデル、CPU/GPU、WAV保存、保存時置換辞書 |
| 詳細設定 | beam size、処理時間、CPUスレッド数、過去文脈の最大文字数 |

## 詳細設定

設定メニューの「詳細設定」では、次の文字起こし設定を変更できます。

- 文字候補数（beam size）: 既定値1。大きいほど複数候補を比較しますが、処理が重くなります。
- 一度に処理する時間: 既定値15秒。長いほど固定処理を減らせますが、ライブ表示は遅くなります。
- CPUスレッド数: 既定値8。CPU環境に合わせて調整できます。
- 過去文脈の最大文字数: 既定値300。長いほど文脈を引き継ぎますが、処理量が増えます。

変更内容は設定キャッシュへ保存され、次回起動時にも復元されます。置換辞書はライブ表示には適用せず、文字起こしファイルの保存時に適用します。

## モデルのダウンロード

音声認識モデルは、プロジェクトのルートからダウンロードして、ダウンロード後に GUI で該当フォルダを選択してください。

### Windows PowerShell

```powershell
mkdir models

uv run hf download Systran/faster-whisper-small `
  --local-dir .\models\faster-whisper-small
```

GUI では次のフォルダを選択します。

```text
.\models\faster-whisper-small
```

精度を優先する場合は、`medium` モデルを使用できます。

```powershell
uv run hf download Systran/faster-whisper-medium `
  --local-dir .\models\faster-whisper-medium
```

`uv run hf` が見つからない場合は、先に次を実行してください。

```powershell
uv sync
```

### Bash

```bash
mkdir -p models

uv run hf download Systran/faster-whisper-small \
  --local-dir ./models/faster-whisper-small
```

GUI では次のフォルダを選択します。

```text
./models/faster-whisper-small
```

精度を優先する場合は、`medium` モデルを使用できます。

```bash
uv run hf download Systran/faster-whisper-medium \
  --local-dir ./models/faster-whisper-medium
```

`uv run hf` が見つからない場合は、先に次を実行してください。

```bash
uv sync
```

### ブラウザから取得する場合

[faster-whisper-small の Files](https://huggingface.co/Systran/faster-whisper-small/tree/main) から、すべてのファイルを同じフォルダへ保存してください。特に `model.bin`、`config.json`、`tokenizer.json` が必要です。
