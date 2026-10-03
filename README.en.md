# 🎤 LumiTrans

[한국어](README.md) | **English**

**AI real-time audio & screen subtitle translator for Windows**

LumiTrans is a standalone desktop app that **listens to any English audio playing on your PC — YouTube, Netflix, online lectures, Twitch, and more — and translates it into Korean subtitles in real time**, displayed in an always-on-top overlay.

---

## 🌟 Key Features

### 1. Choice of translation engines
- **Google Translate**: Default online route; no API key required.
- **DeepL / Gemini / Groq**: Use your own API key for each service. Groq offers ultra-low-latency cloud LPU translation.
- **Local translation**: EXAONE 3.5 (2.4B / 7.8B), TranslateGemma, and Ollama integration. Requires model files and a suitable runtime.
- If the selected engine fails, LumiTrans falls back to Google, then MyMemory. If all fail, the original text is shown, and failed results are never stored in the long-term cache.
- Usage limits and availability of online services depend on each provider's policy and your connection.

### 2. Triple hardware acceleration
- **NVIDIA GPU (CUDA)**: Available when compatible drivers and inference libraries are present.
- **CPU**: Local speech recognition and translation can run on the CPU. Speed and memory usage vary by model and machine.
- **Groq Cloud STT**: Speech recognition via an external API. Subject to network latency and service limits.

### 3. Sentence-level translation & live typing preview
- **Complete sentences**: Tracks periods (`.`) and question marks (`?`) to output natural, complete Korean sentences instead of fragments.
- **Live typing preview**: Shows the recognized source text while the full translation is on its way.

### 4. Netflix-style smart subtitle overlay
- **Click-through**: Click YouTube controls or your browser right through the subtitle window.
- **Auto-fit**: Automatically adjusts font size and height to fit the subtitle length.
- Drag to move and resize; adjust opacity and font size in real time.

### 5. 👁️ Real-time on-screen text translation (Screen OCR) [NEW!]
- **Game dialogue & on-screen subtitles**: Reads silent game dialogue, quest windows, foreign documents, and burned-in video subtitles in real time and shows the translation in a dedicated overlay.
- **Frame-diff detection**: Avoids repeated OCR on static frames; retries on static frames only when a translation fails.
- **ROI selector**: Drag to select the area to watch, just like the Windows Snipping Tool.
- **Dual audio + screen translation**: Show audio and screen subtitles together, or toggle each independently.

---

## 📥 Download

Prebuilt Windows installers are available on the [Releases](https://github.com/makopss/LumiTrans/releases) page:

| Edition | Size | Contents |
|---|---|---|
| **Lite** | ~194 MB | STT/LLM models are downloaded on first run |
| **Full** | ~790 MB | Bundles the STT model and CUDA 12 acceleration libraries |

---

## 🚀 Running from Source

Tested on Windows with Python 3.12. Install the dependencies from the project root first:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

GPU inference libraries and model files may need to be set up separately. Verifying an existing setup on one PC is not the same as verifying a fresh install on another. Per-process audio capture requires `proc-tap`; if it fails to initialize, LumiTrans shows an error instead of silently falling back to whole-device loopback.

### Option 1: Batch file
Double-click **`run.bat`** in the project folder.

### Option 2: Terminal
```bash
python run.py
```

### Option 3: Build the Windows installer (Setup.exe)
Double-click **`build_installer.bat`** in Explorer, or run:
```powershell
python scripts/build_windows_installer.py
```
Both the Lite and Full editions are built by default (use `--edition lite` or `--edition full` to build only one). Building requires [PyInstaller](https://pyinstaller.org) and [Inno Setup 6](https://jrsoftware.org/isinfo.php). When the build finishes, the following installers are created in **`installer_output/`**:
- `LumiTrans_Lite_Setup_v1.0.0.exe`: Models are downloaded on first run
- `LumiTrans_Full_Setup_v1.0.0.exe`: Bundles the STT model and CUDA 12 acceleration libraries

Each installer sets up a complete desktop application with shortcuts, an icon, and an uninstaller.

---

## 🔑 API Keys (optional)
Click the **`[🔑 무료 API 키 등록 및 관리]`** (Manage free API keys) button in the control panel to enter your keys:
- **DeepL API Key**: [DeepL API](https://www.deepl.com/pro-api)
- **Gemini API Key**: [Google AI Studio](https://aistudio.google.com)
- **Groq API Key**: [Groq Console](https://console.groq.com)

Keys are stored in your personal `config.json`. When redistributing, exclude this file along with logs, audio, and subtitle history, and ship `config.example.json` (with empty keys) instead. Note that `.gitignore` only prevents Git from adding these files; it does not apply when you zip the whole folder.

## Testing

```powershell
python scripts/run_offline_tests.py
```

Runs selected existing tests and release regression tests with an offscreen UI and mock engines. End-to-end verification with real models, GPUs, audio, and external APIs is done separately. The report records the hashes of the checked sources and whether any files changed during the run.

When comparing performance, measure each of these separately: model preparation time, latency from source audio to subtitle display, dubbing start latency, RAM/VRAM usage, and impact on game frame rate. No specific latency or resource usage is guaranteed on every PC.

---

## 📜 License

This project is distributed under the [GNU General Public License v3.0](LICENSE).

```
Copyright (C) 2026 makopss

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
```

See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for the licenses of the open-source libraries and AI models used. Model weights are not included in this repository and are governed by their own licenses. In particular, EXAONE 3.5 may be used for **non-commercial purposes only**.

### ⚠️ Disclaimer

This program was created for personal learning and accessibility. Some features — keyless Google Translate requests, Microsoft Edge TTS, YouTube transcripts, and others — use unofficial endpoints rather than official APIs; users are responsible for complying with each service's terms. Use translated subtitles only as a personal viewing aid for copyrighted content.
