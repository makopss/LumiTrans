# 🎤 루미트랜스 (LumiTrans)

**한국어** | [English](README.md)

**AI 실시간 음성 & 화면 번역 자막 및 AI 더빙 (Windows)**

유튜브 영상, 넷플릭스, 게임 대화, 해외 강의, 미팅 등 **PC에서 재생되는 오디오와 화면의 모든 텍스트를 실시간으로 감지하여 다국어 자막과 자연스러운 AI 더빙**으로 출력해주는 올인원 데스크톱 프로그램입니다.

![루미트랜스 자막 오버레이](docs/images/overlay-audio.jpg)

---

## 🌟 최신 핵심 기능 (v1.1.1)

### 1. 🗗 미니 모드 (Mini Mode / Compact UI) [NEW!]
- **단축키 `Ctrl+M`**: 단축키 하나로 상세 설정 패널 ↔ 초소형 미니 모드를 즉시 상호 전환합니다.
- **초소형 콤팩트 제어**: 영상 시청, 게임, 인강, 회의 중 화면을 가리지 않고 핵심 기능(음성 번역, 화면 번역, AI 더빙 및 실시간 볼륨 조절, 자막창 노출 제어)을 원클릭으로 간편 조작합니다.
- **📌 항상 위에 고정(Pin) & 화면 이탈 방지**: 다른 창 위에 상시 띄워두고 직관적으로 제어할 수 있으며, 모니터 상단 밖으로 창이 벗어나지 않도록 화면 경계 보호(Clamping)를 지원합니다.
- **100% Windows Native Frame 복원**: 기본 모드에서 Windows Aero Snap, 스냅 레이아웃(Snap Layouts)을 완벽 지원하며 DWM 몰입형 다크 테마 타이틀바가 매끄럽게 연동됩니다.
- **초고해상도 High-DPI 벡터 아이콘**: 100% 일반 화면은 물론 125%, 150%, 4K 고배율 환경에서도 뭉개짐 없는 칼 같은 선명도의 SVG 아이콘을 제공합니다.
- **종료 상태 자동 기억**: 미니 모드 상태로 프로그램을 종료하면 다음 실행 시에도 자동으로 미니 모드로 즉시 기동됩니다.

### 2. 🌐 글로벌 15개국 다국어 및 i18n 완벽 지원 [NEW!]
- **15개 주요 언어 UI 지원**: 한국어, 영어, 일본어, 중국어(간체/번체), 스페인어, 프랑스어, 독일어, 러시아어, 포르투갈어, 이탈리아어, 베트남어, 태국어, 인도네시아어, 힌디어를 기본 제공합니다.
- **자동 언어 감지**: 첫 실행 시 시스템 언어를 자동으로 감지하며, 설정 탭에서 원클릭으로 언어를 전환할 수 있습니다.
- **다국어 음성 인식 & 번역**: 전 세계 다양한 언어의 소리와 화면을 원하는 언어로 실시간 동시통역합니다.

### 3. 🔊 AI 실시간 더빙 (Edge-TTS) [NEW!]
- **자연스러운 음성 합성**: 번역된 자막을 최신 신경망 기반 AI 음성으로 실시간 읽어줍니다.
- **독립 듀얼 제어**: 음성 번역 더빙과 화면 번역 더빙을 각각 독립적으로 켜고 끌 수 있습니다.
- **더빙 세부 조절**: 음성 합성 속도, 음량 조절 및 각 언어별 최적의 보이스 엔진을 지원합니다.

### 4. 🎯 인플레이스 화면 캡처 및 즉시 번역 (In-place OCR) [NEW!]
- **단축키 즉시 번역**:
  - `F4`: 지정 영역 및 활성 창 즉시 캡처 번역
  - `F9`: 전체 화면 즉시 캡처 번역
- **직관적인 인플레이스 컨트롤 패널**: 번개(즉시 번역), 카메라(전체화면), 닫기(X) 버튼 및 친절한 마우스 오버 툴팁 안내.
- **스마트 화자(Speaker) 분리 및 보존**: 게임이나 영상 대사에서 화자명(`Nora Treadwell:`, `Detective:` 등)을 정밀 인식하여 원문 인명 손상 없이 자연스럽게 분리·보존하여 번역합니다.

### 5. 🧠 다양한 번역 엔진 선택
- **Google 번역**: API 키 없이 바로 사용할 수 있는 기본 온라인 번역.
- **DeepL / Gemini / Groq**: 개인 API 키를 등록하여 최고 품질의 번역 이용 (Groq는 초저지연 클라우드 LPU 번역 지원).
- **로컬 번역 (오프라인)**: EXAONE 3.5 (2.4B/7.8B), TranslateGemma 및 Ollama 로컬 LLM 완전 연동.
- **스마트 폴백**: 번역 엔진 장애 발생 시 Google, MyMemory 순서로 자동 우회 복구.

### 6. ⚡ 강력한 하드웨어 가속
- **NVIDIA GPU (CUDA)**: TensorRT / CTranslate2 기반 초고속 로컬 추론.
- **CPU**: 고효율 멀티스레딩 최적화로 외장 그래픽카드 없는 PC에서도 안정적으로 구동.
- **Groq Cloud STT**: 고성능 클라우드 음성 인식을 통해 저사양 PC에서도 지연 없는 자막 생성.

### 7. 🎬 넷플릭스 스타일 스마트 자막 오버레이
- **마우스 클릭 관통 (Click-Through)**: 자막 창 뒤의 게임 조작, 유튜브 버튼, 웹 브라우저를 방해 없이 자유롭게 클릭.
- **공간 맞춤형 자동 보정 (Auto-Fit)**: 문장 길이에 맞춰 폰트 크기 및 높이를 스마트하게 자동 계산.
- 실시간 타이핑 프리뷰, 투명도 조절, 드래그 이동 및 크기 조절 완벽 지원.

---

## 📸 스크린샷

| 음성 번역 | 화면 번역 (OCR) |
|---|---|
| ![음성 번역 탭](docs/images/panel-audio.png) | ![화면 번역 탭](docs/images/panel-screen.png) |
| **자막 탐색기** | **자막 설정** |
| ![자막 탐색기 탭](docs/images/panel-history.png) | ![자막 설정 탭](docs/images/panel-subtitles.png) |

<details>
<summary>더 보기: 설정 탭 · 화면 번역 오버레이</summary>

![설정 탭](docs/images/panel-settings.png)

![화면 번역 오버레이](docs/images/overlay-screen.jpg)

</details>

---

## 📥 다운로드 (Windows 설치 파일)

공식 릴리즈는 [GitHub Releases](https://github.com/makopss/LumiTrans/releases) 페이지에서 다운로드할 수 있습니다:

| 에디션 | 파일명 | 크기 | 권장 환경 및 특징 |
|---|---|---|---|
| **Korean Lite** | `LumiTrans_Lite_Setup_v1.0.0.exe` | 약 194MB | 한국어 특화 가벼운 패키지 (모델은 첫 실행 시 자동 다운로드) |
| **Korean Full** | `LumiTrans_Full_Setup_v1.0.0.exe` | 약 790MB | 한국어 오프라인 STT 모델 및 CUDA 12 가속 라이브러리 기본 내장 |
| **Global Lite** | `LumiTrans_Global_Lite_Setup_v1.0.0.exe` | 약 194MB | 15개국 다국어 UI 지원 글로벌 에디션 (첫 실행 시 모델 다운로드) |
| **Global Full** | `LumiTrans_Global_Full_Setup_v1.0.0.exe` | 약 968MB | 15개국 다국어 UI + 다국어 STT 모델 + CUDA 12 가속 라이브러리 완전 내장 |

---

## 🚀 소스코드 실행 방법

Windows 및 Python 3.12 환경을 기준으로 개발되었습니다.

```powershell
# 가상환경 생성 및 활성화
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 의존성 패키지 설치
pip install -r requirements.txt

# 프로그램 실행
python run.py
```

### 배치 파일로 간편 실행
프로젝트 루트의 **`run.bat`** 파일을 더블클릭하면 즉시 실행됩니다.

### 윈도우 설치 파일 (Setup.exe) 직접 빌드
```powershell
# 한국어 에디션 전체 빌드
python scripts/build_windows_installer.py --product kr --edition all

# 글로벌 에디션 전체 빌드
python scripts/build_windows_installer.py --product global --edition all
```
빌드가 완료되면 **`installer_output/`** 폴더에 원클릭 인스톨러가 생성됩니다.

---

## 🔑 API 키 등록 방법 (선택 사항)

무료 온라인 번역(Google)은 API 키 등록 없이 바로 작동합니다. 더 높은 품질과 빠른 속도를 위해 개인 API 키를 등록할 수 있습니다:
- **컨트롤 패널 → 설정 → `[🔑 무료 API 키 등록 및 관리]`**
  - **DeepL API Key**: [DeepL API](https://www.deepl.com/pro-api) (월 50만 자 무료)
  - **Gemini API Key**: [Google AI Studio](https://aistudio.google.com) (무료 티어 제공)
  - **Groq API Key**: [Groq Console](https://console.groq.com) (초고속 LPU 클라우드 무료 티어)

API 키는 사용자 PC의 로컬 `config.json`에만 안전하게 저장됩니다.

---

## 🩺 문제 해결 및 로그 확인

- 설치 버전은 백그라운드 데스크톱 모드로 실행되며, 로그는 `%APPDATA%\LumiTrans` 폴더(`stdout.log`, `stderr.log`, `crash.log`)에 자동 보관됩니다.
- **설정 → 문제 진단 → 📂 로그 폴더 열기** 버튼으로 손쉽게 확인할 수 있습니다.
- 실시간 콘솔 출력을 원할 경우 **시작 메뉴 → LumiTrans (디버그 모드)** 또는 `LumiTrans.exe --console`로 실행할 수 있습니다.

---

## 📜 라이선스

이 프로젝트는 [GNU General Public License v3.0](LICENSE)에 따라 배포됩니다.

```
Copyright (C) 2026 makopss

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.
```
