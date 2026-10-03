# Third-Party Licenses

WiseEinstein itself is licensed under the **GNU General Public License v3.0** (see [LICENSE](LICENSE)).

This project depends on, and the Windows installer bundles, the third-party software listed below.
Each component remains under its own license. Full license texts are available from each project's
repository or, for installed Python packages, in the `*.dist-info` folder of each package.

## Python packages

| Package | License | Project |
|---|---|---|
| PyQt6 | GPL-3.0-only | https://www.riverbankcomputing.com/software/pyqt/ |
| Qt 6 (bundled via PyQt6) | LGPL-3.0 | https://www.qt.io/licensing/ |
| soundcard | BSD-3-Clause | https://github.com/bastibe/SoundCard |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| ctranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| deep-translator | MIT | https://github.com/nidhaloff/deep-translator |
| numpy | BSD-3-Clause | https://numpy.org |
| scipy | BSD-3-Clause | https://scipy.org |
| requests | Apache-2.0 | https://github.com/psf/requests |
| transformers | Apache-2.0 | https://github.com/huggingface/transformers |
| jinja2 | BSD-3-Clause | https://github.com/pallets/jinja |
| sherpa-onnx | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |
| hanja | See upstream (to be verified) | https://github.com/suminb/hanja |
| llama-cpp-python | MIT | https://github.com/abetlen/llama-cpp-python |
| llama.cpp (bundled via llama-cpp-python) | MIT | https://github.com/ggml-org/llama.cpp |
| rapidocr-onnxruntime | Apache-2.0 | https://github.com/RapidAI/RapidOCR |
| onnxruntime | MIT | https://github.com/microsoft/onnxruntime |
| pillow | MIT-CMU (HPND) | https://python-pillow.org |
| wordninja | MIT | https://github.com/keredson/wordninja |
| edge-tts | LGPL-3.0 | https://github.com/rany2/edge-tts |
| pygame | LGPL-2.1 | https://www.pygame.org |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| proc-tap | MIT | https://pypi.org/project/proc-tap/ |
| comtypes | MIT | https://github.com/enthought/comtypes |
| youtube-transcript-api | MIT | https://github.com/jdepoix/youtube-transcript-api |

NVIDIA CUDA runtime libraries, when bundled in the CUDA edition, are distributed under the
[NVIDIA CUDA Toolkit EULA](https://docs.nvidia.com/cuda/eula/).

## AI models

Model weights are **not** part of this repository. They are downloaded on demand from Hugging Face
(or bundled only in some installer editions) and are governed by their own licenses:

| Model | License |
|---|---|
| OpenAI Whisper / Systran faster-whisper conversions | MIT |
| Distil-Whisper (Systran faster-distil-whisper-*) | MIT |
| faster-whisper-large-v3-turbo | MIT |
| Moonshine (sherpa-onnx) | MIT |
| NVIDIA Parakeet TDT 0.6B v2 (sherpa-onnx) | CC-BY-4.0 |
| SenseVoice (sherpa-onnx) | FunASR Model License |
| pyannote segmentation 3.0 (sherpa-onnx) | MIT |
| Speaker embedding models (sherpa-onnx) | Varies per model; see upstream |
| LG AI EXAONE 3.5 (2.4B / 7.8B) | EXAONE AI Model License 1.1 – **Non-Commercial** |
| TranslateGemma | Gemma Terms of Use |

## Online services

Google Translate, MyMemory, DeepL, Gemini, Groq, Deepgram, Microsoft Edge TTS, and YouTube are used
under each provider's own terms of service. Some integrations (e.g. Edge TTS, YouTube transcripts,
keyless Google Translate) rely on unofficial endpoints. Users are responsible for complying with
the respective terms.
