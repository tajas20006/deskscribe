# Third-party license review

This is an engineering inventory, not legal advice. Versions are those resolved
in `uv.lock` on 2026-07-31.

## Direct dependencies added for this application

| Package | Version | License | Commercial use |
|---|---:|---|---|
| SoundCard | 0.4.6 | BSD-3-Clause | Permitted, subject to license terms |
| sounddevice | 0.5.5 | MIT | Permitted, subject to license terms |
| faster-whisper | 1.2.1 | MIT | Permitted, subject to license terms |
| NumPy | 2.5.1 | BSD-3-Clause and bundled permissive notices | Permitted, subject to license terms |

Flet was already present and is Apache-2.0. Ollama was already present but is
not imported or used by this application.

## Noteworthy resolved transitive dependencies

| Package | Version | Declared license |
|---|---:|---|
| CTranslate2 | 4.8.1 | MIT |
| PyAV | 18.0.0 | BSD-3-Clause |
| ONNX Runtime | 1.28.0 | MIT |
| huggingface-hub | 1.26.0 | Apache-2.0 |
| tokenizers | 0.23.1 | Apache-2.0 |
| cffi | 2.1.0 | MIT-0 |
| pycparser | 3.0 | BSD-3-Clause |
| filelock | 3.32.2 | MIT |
| flatbuffers | 25.12.19 | Apache-2.0 |
| fsspec | 2026.7.0 | BSD-3-Clause |
| hf-xet | 1.5.2 | Apache-2.0 |
| protobuf | 7.35.1 | BSD-3-Clause |
| tqdm | 4.70.0 | MPL-2.0 and MIT notices |

These licenses allow commercial use, but redistribution can require copyright
notices, license texts, source-file obligations under MPL-2.0, and notices for
bundled native components. Review the installed distributions and their bundled
notices when packaging the application.

The speech-recognition model is not a Python package and is intentionally not
bundled. Its data/model license must be reviewed separately before commercial
use.
