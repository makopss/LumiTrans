# 🎤 루미트랜스 (LumiTrans)

**AI 실시간 음성 & 화면 번역 자막기**

유튜브 영상, 넷플릭스, 해외 강의, 트위치 등 **PC에서 재생되는 모든 영어 소리를 실시간으로 감지하여 한국어 자막으로 번역**해 화면 최상단에 띄워주는 독립형 데스크톱 프로그램입니다.

---

## 🌟 최신 핵심 기능

### 1. 번역 엔진 선택
- **Google 번역**: API 키 없이 요청하는 기본 온라인 경로.
- **DeepL / Gemini / Groq**: 해당 서비스의 API 키를 등록해 사용. Groq는 초저지연 클라우드 LPU 번역을 제공합니다.
- **로컬 번역**: EXAONE 3.5 2.4B·7.8B, TranslateGemma 및 Ollama 연동. 모델 파일과 실행 환경 준비가 필요합니다.
- 선택한 엔진이 실패하면 Google, MyMemory 순서로 폴백합니다. 모두 실패하면 원문을 표시하며 실패 결과는 장기 캐시에 저장하지 않습니다.
- 온라인 서비스의 이용 한도와 가용성은 공급자 정책 및 연결 상태에 따라 달라집니다.

### 2. 강력한 트리플 하드웨어 가속
- **NVIDIA GPU (CUDA)**: 호환 드라이버와 추론 라이브러리가 준비된 환경에서 사용.
- **CPU**: 로컬 음성 인식과 번역을 CPU로 실행할 수 있습니다. 모델별 속도와 메모리 사용량은 기기에 따라 다릅니다.
- **Groq Cloud STT**: 음성 인식을 외부 API로 요청합니다. 네트워크 지연과 서비스 제한의 영향을 받습니다.

### 3. 문장 단위 완결형 번역 & 실시간 타이핑 프리뷰
- **문장 단위 완결**: 마침표(`.`), 물음표(`?`)를 추적하여 토막 나지 않은 자연스러운 완결형 한국어 문장 출력.
- **실시간 타이핑 프리뷰**: 완결 번역을 기다리는 동안 인식한 원문을 먼저 표시합니다.

### 4. 넷플릭스 스타일 스마트 자막 오버레이
- **마우스 클릭 관통 (Click-Through)**: 자막 창 뒤의 유튜브 재생 버튼이나 브라우저 클릭 가능.
- **공간 맞춤형 자동 보정 (Auto-Fit)**: 자막 길이에 맞춰 폰트 크기 및 높이 스마트 자동 보정.
- 드래그 이동 및 크기 조절, 불투명도 및 글자 크기 실시간 조절.

### 5. 👁️ 실시간 화면 영문 텍스트 번역 (Screen OCR) [NEW!]
- **게임 대화창 / 자막 실시간 자동 번역**: 소리가 나오지 않는 게임 대사, 퀘스트창, 해외 문서, 영상 속 자막을 실시간으로 읽어 전용 오버레이 창에 즉시 번역 표출.
- **프레임 변동 감지 (Frame Diff)**: 정지 화면의 반복 OCR을 줄입니다. 번역 실패 시에는 정지 화면에서도 재시도합니다.
- **스마트 영역 지정 (ROI Selector)**: 윈도우 캡처 도구처럼 마우스로 원하는 영역을 슥 드래그하여 간편하게 지정.
- **오디오 + 화면 동시 듀얼 번역**: 소리 자막과 화면 자막을 동시에 띄워두거나 필요에 따라 개별 토글 가능.

---

## 🚀 실행 방법

Windows 및 Python 3.12 환경을 기준으로 검증하고 있습니다. 프로젝트 루트에서 먼저 의존성을 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

GPU용 추론 라이브러리와 모델 파일은 별도로 준비해야 할 수 있습니다. 현재 PC의 기존 설치 환경 검증과 새 PC 설치 검증은 별개입니다. 프로세스 전용 캡처에는 `proc-tap`이 필요하며, 초기화 실패 시 전체 장치 루프백으로 자동 전환하지 않고 오류를 표시합니다.

### 방법 1: 배치 파일 실행
폴더 내 **`run.bat`** 파일을 더블클릭합니다.

### 방법 2: 터미널 실행
```bash
python run.py
```

### 방법 3: 윈도우 설치 버전 (Setup.exe) 빌드 및 배포
탐색기에서 **`build_installer.bat`** 파일을 더블클릭하거나 아래 명령을 실행합니다:
```powershell
python scripts/build_windows_installer.py
```
기본으로 Lite와 Full 두 에디션을 모두 빌드합니다(`--edition lite` / `--edition full`로 하나만 빌드 가능). 빌드가 완료되면 **`installer_output/`** 폴더에 다음 설치 프로그램이 생성됩니다:
- `LumiTrans_Lite_Setup_v1.0.0.exe`: 모델은 첫 실행 시 다운로드
- `LumiTrans_Full_Setup_v1.0.0.exe`: STT 모델 및 CUDA 12 가속 라이브러리 내장

설치 파일 하나로 바로가기, 아이콘, 언인스톨러를 포함한 완전한 데스크톱 애플리케이션 설치가 가능합니다.


---

## 🔑 API 키 등록 방법 (선택 사항)
컨트롤 패널의 **`[🔑 무료 API 키 등록 및 관리]`** 버튼을 클릭하여 입력하실 수 있습니다:
- **DeepL API Key**: [DeepL API](https://www.deepl.com/pro-api)
- **Gemini API Key**: [Google AI Studio](https://aistudio.google.com)
- **Groq API Key**: [Groq Console](https://console.groq.com)

키는 개인 `config.json`에 저장됩니다. 배포 시 이 파일과 로그·음성·자막 기록을 제외하고, 키가 비어 있는 `config.example.json`을 사용하세요. `.gitignore`는 Git 추가를 막지만 폴더 전체 압축에는 적용되지 않습니다.

## 검증

```powershell
python scripts/run_offline_tests.py
```

선택한 기존 테스트와 출시 회귀 테스트를 오프스크린 UI 및 mock 엔진으로 실행합니다. 실제 모델·GPU·오디오·외부 API를 사용한 종단 간 검증은 별도입니다. 자동 검증 결과에는 검사한 소스 해시와 실행 중 파일 변경 여부를 기록합니다.

성능을 비교할 때는 모델 준비 시간, 원음 시작부터 자막 표시까지의 지연, 더빙 시작 지연, RAM/VRAM, 게임 프레임 영향을 각각 측정하세요. 특정 지연이나 자원 사용량을 모든 PC에 보장하지 않습니다.

---

## 📜 라이선스

이 프로젝트는 [GNU General Public License v3.0](LICENSE)에 따라 배포됩니다.

```
Copyright (C) 2026 makopss

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
```

사용한 오픈소스 라이브러리와 AI 모델의 라이선스는 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)를 참고하세요. 모델 가중치는 이 저장소에 포함되지 않으며 각 모델의 라이선스를 따릅니다. 특히 EXAONE 3.5는 **비상업적 용도**로만 사용할 수 있습니다.

### ⚠️ 면책 조항

이 프로그램은 개인 학습 및 접근성 향상 목적으로 제작되었습니다. Google 번역(키 없는 요청), Microsoft Edge TTS, YouTube 자막 등 일부 기능은 공식 API가 아닌 경로를 사용하며, 각 서비스의 약관 준수 책임은 사용자에게 있습니다. 번역 자막은 저작권이 있는 콘텐츠의 개인 시청 보조용으로만 사용하세요.
