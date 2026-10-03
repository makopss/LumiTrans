"""Cached public-fixture smoke comparison; no capture, downloads or external API.

The sparse reference intervals come from the project's existing fixture test.
This is NOT an independent interview benchmark or a measured full-file DER.
"""
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1', QT_QPA_PLATFORM='offscreen')
import numpy as np
from huggingface_hub import hf_hub_download
from src.speaker_identifier import SpeakerIdentifier


def evaluate(cls, audio, sample_rate):
    cfg = dict(speaker_diarization_enabled=False, speaker_segmentation_enabled=True,
               speaker_similarity_threshold=.65, speaker_max_count=2, speaker_window_sec=5.0)
    identifier = cls(cfg)
    identifier.is_enabled = True
    started = time.perf_counter()
    ready = identifier._ensure_model_loaded()
    load_sec = time.perf_counter() - started
    if not ready or not identifier.diarizer_loaded:
        raise RuntimeError('Cached models could not be loaded')
    intervals, timings, consumed = [], [], 0
    for start in range(0, len(audio), int(2.5 * sample_rate)):
        chunk = audio[start:start + int(2.5 * sample_rate)]
        if hasattr(identifier, 'set_audio_context'):
            identifier.set_audio_context(start, 'public-fixture')
        began = time.perf_counter()
        slices = identifier.segment_audio_by_speaker(chunk, sample_rate)
        timings.append(time.perf_counter() - began)
        position = start
        for samples, info in slices:
            intervals.append(dict(start=position/sample_rate, end=(position+len(samples))/sample_rate, speaker=info[0]))
            position += len(samples)
            consumed += len(samples)
    references = [(1.58, 3.41, 'A'), (4.40, 6.46, 'A'), (9.35, 11.47, 'B'), (12.16, 14.64, 'B')]
    coverage, total = 0.0, sum(b-a for a, b, _ in references)
    assignments = []
    for permutation in itertools.permutations(('A', 'B')):
        correct, assigned = 0.0, 0.0
        for a, b, label in references:
            for interval in intervals:
                duration = max(0, min(b, interval['end'])-max(a, interval['start']))
                spk = interval['speaker']
                if spk in (1, 2):
                    assigned += duration
                    if permutation[spk-1] == label:
                        correct += duration
        assignments.append((correct, assigned, permutation))
    correct, assigned, mapping = max(assignments)
    return dict(load_sec=load_sec, audio_sec=len(audio)/sample_rate,
                input_samples=len(audio), output_samples=consumed,
                calls=len(timings), inference_total_sec=sum(timings),
                inference_p50_ms=float(np.percentile(timings, 50)*1000),
                inference_p95_ms=float(np.percentile(timings, 95)*1000),
                reference_sec=total, assigned_reference_sec=assigned,
                correct_reference_sec=correct, coverage=assigned/total,
                accuracy_when_assigned=correct/assigned if assigned else None,
                global_mapping=mapping, intervals=intervals)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    path = hf_hub_download('csukuangfj/speaker-embedding-models', '1-two-speakers-en.wav', local_files_only=True)
    with wave.open(path, 'rb') as file:
        assert file.getnchannels() == 1 and file.getsampwidth() == 2
        sr = file.getframerate()
        audio = np.frombuffer(file.readframes(file.getnframes()), np.int16).astype(np.float32)/32768
    output = ROOT / 'output/speaker-review-2026-09-16'
    sources = [ROOT / 'src' / name for name in ('speaker_identifier.py', 'speaker_recognition.py', 'speaker_tracking.py')]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report = dict(scope='Sparse existing public-fixture annotations; no live capture/STT/translation; not full DER',
                  fixture_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), source_sha256=hashes)
    # Baseline is retained only as a review artifact; never imported by the app.
    baseline = output / 'before-structure/src/speaker_identifier.py'
    if baseline.exists():
        spec = importlib.util.spec_from_file_location('speaker_baseline', baseline)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report['before'] = evaluate(module.SpeakerIdentifier, audio, sr)
    report['after'] = evaluate(SpeakerIdentifier, audio, sr)
    report['sources_unchanged'] = all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[p.name] for p in sources)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'cached-model-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: {k:v for k,v in value.items() if k != 'intervals'} if isinstance(value, dict) else value
                      for key, value in report.items()}, ensure_ascii=False, indent=2))
    return 0 if report['sources_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
