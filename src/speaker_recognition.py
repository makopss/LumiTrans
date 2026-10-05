"""Speaker evidence, model lifecycle, and rolling-window identity linking.

SpeakerIdentifier supplies the UI names, lock and callbacks. Tuple ID 0 is
deliberately unassigned; downstream code must never treat it as a real person.
"""
import time
import numpy as np
from .speaker_tracking import SpeakerAudioWindow, partition_segments

UNKNOWN_COLOR = '#AAB2C0'


def _safe_hf_hub_download(repo_id: str, filename: str) -> str:
    from huggingface_hub import hf_hub_download
    try:
        return hf_hub_download(repo_id=repo_id, filename=filename, local_files_only=True)
    except Exception:
        return hf_hub_download(repo_id=repo_id, filename=filename)


class SpeakerRecognition:
    def _init_recognition(self):
        self._window = SpeakerAudioWindow(self.config.get('speaker_window_sec', 5.0))
        self._audio_context = (None, None)
        self._embedding_path = None
        self._embedding_retry_at = 0.0
        self._segmentation_retry_at = 0.0
        self._segmentation_signature = None
        self._status = '화자 모델 준비 중' if self.is_enabled else '화자 분리 꺼짐'
        self.last_decision = {'state': 'unknown', 'reason': 'not_started'}
        self._configure_recognition()

    def _configure_recognition(self):
        self.cluster_threshold = float(self.config.get('speaker_cluster_distance_threshold', 0.5))
        self.match_margin = float(self.config.get('speaker_match_margin', 0.08))
        self.min_register_sec = float(self.config.get('speaker_min_register_sec', 1.0))
        self._window.seconds = max(1.0, min(float(self.config.get('speaker_window_sec', 5.0)), 15.0))
        signature = (self.segmentation_enabled, self.cluster_threshold)
        if self._segmentation_signature is not None and signature != self._segmentation_signature:
            self.diarizer = None
            self.diarizer_loaded = False
            self._segmentation_retry_at = 0.0
            self._window.clear()
        if not self.is_enabled:
            self._window.clear()
            self._status = '화자 분리 꺼짐'
        self._segmentation_signature = signature

    def get_status(self):
        raw = self._status if self.is_enabled else '화자 분리 꺼짐'
        try:
            from .speaker_identifier import localize_speaker_status
            return localize_speaker_status(raw)
        except Exception:
            return raw

    def set_audio_context(self, start_sample=None, session_id=None):
        """Metadata belongs to the next captured chunk, not processing time."""
        with self.lock:
            self._audio_context = (start_sample, session_id)

    def _ensure_model_loaded(self):
        # Embedding and segmentation have independent retry states. A successful
        # embedding load must not permanently mask a failed segmentation load.
        with self.lock:
            now = time.monotonic()
            if not self.model_loaded:
                if now < self._embedding_retry_at:
                    return False
                try:
                    import sherpa_onnx
                    self._status = '화자 음성 모델 준비 중'
                    self._embedding_path = _safe_hf_hub_download(
                        repo_id='csukuangfj/speaker-embedding-models',
                        filename='3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx')
                    config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                        model=self._embedding_path, num_threads=1, debug=False, provider='cpu')
                    if not config.validate():
                        raise ValueError('invalid embedding configuration')
                    self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
                    self.manager = sherpa_onnx.SpeakerEmbeddingManager(self.extractor.dim)
                    self.model_loaded = True
                except Exception as error:
                    self._status = f'화자 모델 준비 실패 · 5초 후 재시도 ({type(error).__name__})'
                    self._embedding_retry_at = now + 5.0
                    return False
            if self.segmentation_enabled and not self.diarizer_loaded:
                if now < self._segmentation_retry_at:
                    return True
                try:
                    import sherpa_onnx
                    self._status = '화자 교대 모델 준비 중'
                    if not self._embedding_path:
                        self._embedding_path = _safe_hf_hub_download(
                            repo_id='csukuangfj/speaker-embedding-models',
                            filename='3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx')
                    model = _safe_hf_hub_download(
                        repo_id='csukuangfj/sherpa-onnx-pyannote-segmentation-3-0', filename='model.onnx')
                    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
                        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=model),
                            num_threads=2, debug=False, provider='cpu'),
                        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                            model=self._embedding_path, num_threads=2, debug=False, provider='cpu'),
                        # This is a DISTANCE. It is not the identity similarity.
                        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=self.cluster_threshold),
                        min_duration_on=0.1, min_duration_off=0.2)
                    if not config.validate():
                        raise ValueError('invalid segmentation configuration')
                    self.diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
                    self.diarizer_loaded = True
                except Exception as error:
                    self.diarizer = None
                    self.diarizer_loaded = False
                    self._segmentation_retry_at = now + 5.0
                    self._status = f'화자 교대 분석 불가 · 미확정 표시 / 재시도 ({type(error).__name__})'
                    return True
            self._status = ('화자 교대 분석 작동 중' if self.segmentation_enabled
                            else '단일 발화 판정 · 교대 분석 꺼짐')
            return True

    def _unknown(self, reason='uncertain', state='unknown'):
        self.last_decision = {'state': state, 'reason': reason}
        # Prevent OCR from assigning the preceding person's name to new speech.
        self.last_active_speaker = None
        from src.i18n import tr
        label = {'pending': tr('speaker_pending'), 'overlap': tr('speaker_overlap')}.get(state, tr('speaker_unconfirmed'))
        return 0, label, UNKNOWN_COLOR

    def _get_fallback_speaker(self):
        with self.lock:
            return self._unknown()

    def _extract_embedding(self, audio, sample_rate):
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if (len(audio) < round(sample_rate * 0.45) or not np.all(np.isfinite(audio))
                or float(np.sqrt(np.mean(audio ** 2))) < 0.005):
            return None
        stream = self.extractor.create_stream()
        stream.accept_waveform(sample_rate, audio)
        stream.input_finished()
        emb = np.asarray(self.extractor.compute(stream), dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(emb)
        return emb / norm if emb.size and np.isfinite(norm) and norm > 0 else None

    def _rank_matches(self, embedding):
        matches = []
        for name, profile in self.speaker_profiles_data.items():
            scores = [float(np.dot(embedding, profile['centroid']))]
            scores.extend(float(np.dot(embedding, ex)) for ex in profile.get('exemplars', []))
            matches.append((name, max(scores)))
        return sorted(matches, key=lambda pair: pair[1], reverse=True)

    def _find_best_match(self, emb):
        emb = np.asarray(emb, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(emb)
        if not np.isfinite(norm) or norm <= 0:
            return '', -1.0
        return next(iter(self._rank_matches(emb / norm)), ('', -1.0))

    def _find_closest_speaker(self, emb):
        return self._find_best_match(emb)[0]

    def _speaker_info(self, name):
        number = self._extract_speaker_number(name)
        return number, self.get_display_name(name), self.speaker_color_map[name]

    def _link_embedding(self, embedding, duration, excluded=(), fresh_duration=None):
        if embedding is None:
            return self._unknown('insufficient_voice', 'pending')
        ranked = self._rank_matches(embedding)
        name, score = ranked[0] if ranked else ('', -1.0)
        runner_up = ranked[1][1] if len(ranked) > 1 else -1.0
        margin = score - runner_up
        if name and score >= self.threshold:
            if name in excluded or margin < self.match_margin:
                return self._unknown('conflicting_identity')
            # Freeze references for weak/ambiguous/short evidence. Repeated old
            # context cannot continuously move a profile toward a wrong person.
            fresh = duration if fresh_duration is None else fresh_duration
            if fresh >= 1.5 and score >= max(0.75, self.threshold + 0.1) and margin >= 0.15:
                data = self.speaker_profiles_data[name]
                centroid = 0.95 * data['centroid'] + 0.05 * embedding
                data['centroid'] = centroid / np.linalg.norm(centroid)
                # Preserve enrollment as an anchor; adapt the other examples.
                refs = data.setdefault('exemplars', [])
                if len(refs) >= 5:
                    refs.pop(1)
                refs.append(embedding.copy())
            self.last_decision = dict(state='confirmed', score=score, margin=margin)
            return self._speaker_info(name)
        if duration < self.min_register_sec:
            return self._unknown('short_new_voice', 'pending')
        if len(self.speaker_profiles_data) >= self.max_speakers:
            return self._unknown('speaker_limit')
        if name and score >= max(0.0, self.threshold - 0.12):
            return self._unknown('borderline_new_voice')
        self.current_speaker_count += 1
        name = f'화자 {self.current_speaker_count}'
        self.speaker_profiles_data[name] = {'centroid': embedding.copy(), 'exemplars': [embedding.copy()]}
        from .speaker_identifier import SPEAKER_COLORS
        self.speaker_color_map[name] = SPEAKER_COLORS[(self.current_speaker_count - 1) % len(SPEAKER_COLORS)]
        self.last_decision = dict(state='confirmed', reason='new_voice', score=score)
        self._notify_speaker_updated()
        return self._speaker_info(name)

    def _activate_info(self, info):
        self.last_active_speaker = f'화자 {info[0]}' if info[0] > 0 else None
        self.last_active_time = time.time() if info[0] > 0 else 0.0

    def identify_speaker(self, audio_data, sample_rate=16000):
        if not self.is_enabled:
            return 1, '화자 1', '#00E5FF'  # legacy disabled API
        with self.lock:
            if audio_data is None or not self._ensure_model_loaded():
                return self._unknown('model_unavailable')
            try:
                audio = np.asarray(audio_data, dtype=np.float32).reshape(-1)
                info = self._link_embedding(self._extract_embedding(audio, sample_rate), len(audio) / sample_rate)
                self._activate_info(info)
                return info
            except Exception as error:
                return self._unknown(f'inference_{type(error).__name__}')

    def segment_audio_by_speaker(self, audio_data, sample_rate=16000):
        audio = np.asarray(audio_data, dtype=np.float32).reshape(-1)
        if not self.is_enabled:
            return [(audio, (1, '화자 1', '#00E5FF'))]
        with self.lock:
            start_sample, session_id = self._audio_context
            self._audio_context = (None, None)
            window, offset = self._window.append(audio, sample_rate, start_sample, session_id)
            if not self._ensure_model_loaded():
                return [(audio, self._unknown('model_unavailable'))]
            if not self.segmentation_enabled:
                return [(audio, self.identify_speaker(audio, sample_rate))]
            if not self.diarizer_loaded or self.diarizer is None:
                return [(audio, self._unknown('segmentation_unavailable'))]
            try:
                result = self.diarizer.process(window)
                spans = partition_segments(result.sort_by_start_time(), len(window), sample_rate)
                evidence = {}
                fresh = {}
                for span in spans:
                    if len(span.speakers) == 1:
                        label = next(iter(span.speakers))
                        evidence.setdefault(label, []).append(window[span.start:span.end])
                        fresh[label] = fresh.get(label, 0) + max(0, span.end - max(offset, span.start))
                # Classify the strongest evidence first; reserve an ID for at
                # most one local voice. Do not force unmatched voices into it.
                candidates = []
                for label, pieces in evidence.items():
                    combined = np.concatenate(pieces)
                    embedding = self._extract_embedding(combined, sample_rate)
                    ranks = self._rank_matches(embedding) if embedding is not None else []
                    score = ranks[0][1] if ranks else -1.0
                    candidates.append((label, embedding, len(combined) / sample_rate, score))
                candidates.sort(key=lambda item: (item[3] >= self.threshold, item[3], item[2]), reverse=True)
                identities, used = {}, set()
                for label, embedding, duration, _ in candidates:
                    info = self._link_embedding(embedding, duration, used, fresh[label] / sample_rate)
                    identities[label] = info
                    if info[0] > 0:
                        used.add(f'화자 {info[0]}')
                slices = []
                for span in spans:
                    start, end = max(offset, span.start), span.end
                    if end <= start:
                        continue
                    if len(span.speakers) == 1:
                        info = identities[next(iter(span.speakers))]
                    else:
                        info = self._unknown('overlapping_voice' if span.speakers else 'unassigned_interval',
                                             'overlap' if span.speakers else 'unknown')
                    # Every NEW sample is delivered exactly once, including
                    # interjections, silence gaps and overlaps. No 350ms cutoff.
                    slices.append((audio[start - offset:end - offset], info))
                if not slices:
                    return [(audio, self._unknown('no_segments'))]
                self._activate_info(slices[-1][1])
                return slices
            except Exception as error:
                self._status = f'화자 교대 분석 오류 · 미확정 표시 ({type(error).__name__})'
                return [(audio, self._unknown('segmentation_error'))]
