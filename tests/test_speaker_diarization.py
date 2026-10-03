import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import sys
import os
import time
import wave
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.speaker_identifier import SpeakerIdentifier, SPEAKER_COLORS
from src.config import DEFAULT_CONFIG

def test_speaker_identifier_loading_and_speed():
    print("[1] 3D-Speaker Cam++ 화자 지문 모델 로드 및 추론 속도 테스트...")
    cfg = DEFAULT_CONFIG.copy()
    cfg["speaker_diarization_enabled"] = True
    cfg["speaker_similarity_threshold"] = 0.50

    identifier = SpeakerIdentifier(config=cfg)
    assert identifier._ensure_model_loaded(), "화자 감별 모델이 정상적으로 로드되어야 합니다."
    assert identifier.extractor is not None, "Extractor 인스턴스가 존재해야 합니다."
    assert identifier.manager is not None, "Manager 인스턴스가 존재해야 합니다."
    assert identifier.extractor.dim in (192, 512), f"임베딩 차원이 192 또는 512여야 합니다. (실제: {identifier.extractor.dim})"

    # 1초 가상 오디오로 추론 속도 측정
    dummy_audio = np.random.randn(16000).astype(np.float32) * 0.1
    t0 = time.time()
    spk_num, spk_label, spk_color = identifier.identify_speaker(dummy_audio)
    elapsed_ms = (time.time() - t0) * 1000

    print(f"  -> 1초 오디오 음색 추출 및 화자 매칭 소요 시간: {elapsed_ms:.2f}ms (초저지연)")
    assert elapsed_ms < 50, f"임베딩 추출은 50ms 이하여야 합니다. (실제: {elapsed_ms:.2f}ms)"
    assert spk_num == 1, "첫 번째 발화자는 화자 1이어야 합니다."
    assert spk_label == "화자 1", "라벨은 '화자 1'이어야 합니다."
    assert spk_color == SPEAKER_COLORS[0], "색상은 화자 1 고유 색상(#00E5FF)이어야 합니다."
    print("  -> 모델 로드 및 추론 속도 검증 통과!")

def test_real_multi_speaker_separation():
    print("[2] 실제 2인 영어 대화 오디오(1-two-speakers-en.wav) 화자 분리 정확도 테스트...")
    from huggingface_hub import hf_hub_download

    wav_path = hf_hub_download(repo_id="csukuangfj/speaker-embedding-models", filename="1-two-speakers-en.wav")
    with wave.open(wav_path, "rb") as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        data = wf.readframes(n_frames)
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    cfg = DEFAULT_CONFIG.copy()
    cfg["speaker_diarization_enabled"] = True
    cfg["speaker_similarity_threshold"] = 0.55

    identifier = SpeakerIdentifier(config=cfg)
    identifier.reset()

    # 구간 1: 화자 A (0.5s ~ 3.5s)
    seg_a1 = audio[int(sample_rate * 0.5) : int(sample_rate * 3.5)]
    num1, label1, col1 = identifier.identify_speaker(seg_a1, sample_rate)
    print(f"  -> 구간 1(화자 A): {label1} ({col1})")
    assert num1 == 1 and label1 == "화자 1", "첫 발화자는 화자 1로 등록되어야 합니다."

    # 구간 2: 화자 A 계속 발화 (3.5s ~ 6.5s) -> 화자 1로 매칭되어야 함
    seg_a2 = audio[int(sample_rate * 3.5) : int(sample_rate * 6.5)]
    num2, label2, col2 = identifier.identify_speaker(seg_a2, sample_rate)
    print(f"  -> 구간 2(화자 A 재발화): {label2} ({col2})")
    assert num2 == 1 and label2 == "화자 1", "동일 인물은 기존 화자 1로 매칭되어야 합니다."

    # 구간 3: 화자 B 발화 (7.0s ~ 10.0s) -> 화자 2로 분리되어야 함
    seg_b = audio[int(sample_rate * 7.0) : int(sample_rate * 10.0)]
    num3, label3, col3 = identifier.identify_speaker(seg_b, sample_rate)
    print(f"  -> 구간 3(화자 B 발화): {label3} ({col3})")
    assert num3 == 2 and label3 == "화자 2", "다른 인물은 화자 2로 분리 등록되어야 합니다."
    assert col3 == SPEAKER_COLORS[1], "화자 2는 골드 색상이어야 합니다."
    print("  -> 2인 다중 화자 완벽 분리 검증 통과!")

def test_speaker_identifier_reset_and_disabled():
    print("[3] 화자 감별기 리셋(초기화) 및 비활성화 동작 테스트...")
    cfg = DEFAULT_CONFIG.copy()
    cfg["speaker_diarization_enabled"] = True
    identifier = SpeakerIdentifier(config=cfg)

    # 1. 리셋 기능 검증
    identifier.reset()
    assert identifier.current_speaker_count == 0, "리셋 후 화자 수는 0이어야 합니다."
    assert len(identifier.speaker_color_map) == 0, "색상 맵이 비워져야 합니다."

    # 2. 비활성화 모드 검증
    cfg["speaker_diarization_enabled"] = False
    identifier.update_config(cfg)
    assert not identifier.is_enabled, "is_enabled가 False여야 합니다."

    dummy_audio = np.random.randn(16000).astype(np.float32) * 0.1
    num, label, col = identifier.identify_speaker(dummy_audio)
    assert num == 1 and label == "화자 1", "비활성화 상태에서는 단일 기본 화자로 반환해야 합니다."
    print("  -> 화자 리셋 및 비활성화 모드 검증 통과!")

def test_control_panel_and_persistence_integration():
    print("[4] ControlPanel 화자 분리 UI 조작 및 설정 영구 저장 테스트...")
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from src.control_panel import ControlPanel
    from src.overlay_window import SubtitleOverlay
    from src.stt_engine import STTWorker
    import queue

    app = QApplication.instance() or QApplication(sys.argv)

    saved_config = {}
    def mock_save(c):
        saved_config.clear()
        saved_config.update(c)

    test_cfg = DEFAULT_CONFIG.copy()
    test_cfg["speaker_diarization_enabled"] = False
    test_cfg["speaker_similarity_threshold"] = 0.50

    q = queue.Queue()
    stt_worker = STTWorker(audio_queue=q, config=test_cfg)
    audio_ov = SubtitleOverlay(test_cfg)

    cp = ControlPanel(
        config=test_cfg,
        overlay=audio_ov,
        audio_thread=None,
        stt_thread=stt_worker,
        save_config_cb=mock_save,
        screen_worker=None,
        screen_overlay=None,
        inplace_manager=None
    )

    # 1. 체크박스/토글 조작 및 동기화 확인
    assert not cp.cb_speaker_diarization.isChecked(), "초기 상태는 False여야 합니다."
    cp.cb_speaker_diarization.setChecked(True)
    assert test_cfg["speaker_diarization_enabled"] == True, "체크 시 설정값이 True여야 합니다."
    assert stt_worker.speaker_identifier.is_enabled == True, "STTWorker 화자 감별기가 활성화되어야 합니다."

    # 2. 슬라이더 조작 확인 (0.45로 변경)
    cp.slider_speaker_threshold.setValue(45)
    assert test_cfg["speaker_similarity_threshold"] == 0.45, "임계값이 0.45로 반영되어야 합니다."
    assert stt_worker.speaker_identifier.threshold == 0.45, "STTWorker 화자 감별기 임계값도 0.45여야 합니다."

    # 3. 최대 화자 수 콤보박스 조작 확인 (4명으로 변경)
    idx_4 = cp.combo_speaker_max_count.findData(4)
    if idx_4 >= 0:
        cp.combo_speaker_max_count.setCurrentIndex(idx_4)
        assert test_cfg["speaker_max_count"] == 4, "최대 화자 수가 4로 반영되어야 합니다."
        assert stt_worker.speaker_identifier.max_speakers == 4, "STTWorker 최대 화자 수도 4여야 합니다."

    # 4. 화자 리셋 버튼 클릭 핸들러 동작 확인
    orig_info = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *args, **kwargs: None)
    try:
        cp.on_reset_speakers_clicked()
        assert stt_worker.speaker_identifier.current_speaker_count == 0, "리셋 후 화자 수가 0이어야 합니다."
    finally:
        QMessageBox.information = orig_info

    # 5. 종료 전 일괄 저장 검증
    cp.save_all_settings_before_exit()
    assert saved_config.get("speaker_diarization_enabled") == True, "speaker_diarization_enabled가 True로 저장되어야 합니다."
    assert saved_config.get("speaker_similarity_threshold") == 0.45, "speaker_similarity_threshold가 0.45로 저장되어야 합니다."

    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    try:
        cp.close()
        audio_ov.close()
    finally:
        QMessageBox.question = orig_q

    print("  -> ControlPanel 화자 분리 UI 및 영구 보존 연동 테스트 통과!")

def test_two_speaker_dialogue_robustness():
    print("[5] 2인 대화 환경에서 화자 증식(화자 3~8) 방지 및 클러스터 고정 테스트...")
    from huggingface_hub import hf_hub_download

    wav_path = hf_hub_download(repo_id="csukuangfj/speaker-embedding-models", filename="1-two-speakers-en.wav")
    with wave.open(wav_path, "rb") as wf:
        sample_rate = wf.getframerate()
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    cfg = DEFAULT_CONFIG.copy()
    cfg["speaker_diarization_enabled"] = True
    cfg["speaker_similarity_threshold"] = 0.42
    cfg["speaker_max_count"] = 2

    identifier = SpeakerIdentifier(config=cfg)
    identifier.reset()

    # 8개의 다양한 발화 슬라이스(다양한 억양, 길이, 교대 발화)
    slices = [
        (1.58, 3.41, "화자 A"),
        (2.0, 3.2, "화자 A (짧은 발화)"),
        (4.40, 6.46, "화자 A (톤 변조)"),
        (9.35, 11.47, "화자 B (새 화자 등장)"),
        (10.0, 11.2, "화자 B (짧은 발화)"),
        (12.16, 14.64, "화자 B (감정 고조)"),
        (1.6, 2.8, "화자 A (재발화)"),
        (12.5, 14.0, "화자 B (재발화)"),
    ]

    assigned_history = []
    for s, e, desc in slices:
        chunk = audio[int(s * sample_rate) : int(e * sample_rate)]
        spk_num, spk_label, col = identifier.identify_speaker(chunk, sample_rate)
        assigned_history.append((spk_num, spk_label))
        print(f"  -> {desc} ({s:.2f}s~{e:.2f}s): {spk_label}")
        assert spk_num in (1, 2), f"화자 번호는 1 또는 2만 허용됩니다. (실제: {spk_num})"

    assert identifier.current_speaker_count == 2, f"총 화자 수는 정확히 2명이어야 합니다. (실제: {identifier.current_speaker_count})"
    print("  -> 2인 대화 화자 증식 방지 검증 통과! (화자 3~8 생성 100% 차단)")

if __name__ == "__main__":
    print("=" * 60)
    print("[TEST] 실시간 오디오 화자 감별기(Speaker Diarization) 단위 테스트 시작")
    print("=" * 60)
    test_speaker_identifier_loading_and_speed()
    test_real_multi_speaker_separation()
    test_speaker_identifier_reset_and_disabled()
    test_control_panel_and_persistence_integration()
    test_two_speaker_dialogue_robustness()
    print("\n[SUCCESS] 모든 화자 감별기 단위 테스트 성공적으로 통과!")
