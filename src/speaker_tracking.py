"""Bounded audio context and lossless speaker intervals, independent of models/Qt."""
from dataclasses import dataclass
import re
import numpy as np


@dataclass(frozen=True)
class SpeakerSpan:
    start: int
    end: int
    speakers: frozenset


def partition_segments(segments, length, sample_rate):
    """Cover every input sample once, including gaps and simultaneous speech.

    A set of two or more local labels means overlap, never two copies of audio.
    """
    intervals = []
    boundaries = {0, length}
    for segment in segments:
        if not np.isfinite(segment.start) or not np.isfinite(segment.end):
            continue
        start = max(0, min(length, round(segment.start * sample_rate)))
        end = max(0, min(length, round(segment.end * sample_rate)))
        if end > start:
            intervals.append((start, end, segment.speaker))
            boundaries.update((start, end))
    points = sorted(boundaries)
    spans = []
    for start, end in zip(points, points[1:]):
        labels = frozenset(label for a, b, label in intervals if a < end and b > start)
        if spans and spans[-1].speakers == labels:
            spans[-1] = SpeakerSpan(spans[-1].start, end, labels)
        else:
            spans.append(SpeakerSpan(start, end, labels))
    return spans


class SpeakerAudioWindow:
    """Retain recent capture-time audio; never emit old context a second time."""
    def __init__(self, seconds=5.0):
        self.seconds = max(1.0, min(float(seconds), 15.0))
        self.clear()

    def clear(self):
        self.audio = np.empty(0, dtype=np.float32)
        self.end_sample = None
        self.sample_rate = None
        self.session_id = None

    def append(self, audio, sample_rate, start_sample=None, session_id=None):
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if sample_rate <= 0:
            raise ValueError('sample_rate must be positive')
        if (self.sample_rate != sample_rate or self.session_id != session_id):
            self.clear()
        start = (self.end_sample or 0) if start_sample is None else int(start_sample)
        gap = 0 if self.end_sample is None else start - self.end_sample
        limit = max(len(audio), int(self.seconds * sample_rate))
        if gap < 0 or gap >= limit:
            self.audio = np.empty(0, dtype=np.float32)
            gap = 0
        # Capture can omit silence; retain its position rather than joining words.
        context = np.concatenate((self.audio, np.zeros(gap, np.float32)))
        keep = max(0, limit - len(audio))
        context = context[-keep:] if keep else context[:0]
        offset = len(context)
        self.audio = np.concatenate((context, audio))
        self.end_sample = start + len(audio)
        self.sample_rate = sample_rate
        self.session_id = session_id
        return self.audio, offset


def align_transcript(text, words, slices, sample_rate=16000):
    """Attribute complete ASR output to the sample timeline without cutting words.

    Missing/incomplete word timing is not permission to discard transcript text
    or assign a mixed-speaker sentence to its first speaker.
    """
    unknown = (0, '화자 미확정', '#AAB2C0')
    intervals, cursor = [], 0.0
    for audio, info in slices:
        end = cursor + len(audio) / sample_rate
        intervals.append((cursor, end, info or unknown))
        cursor = end
    parsed = []
    for word in words or []:
        try:
            token = str(word.get('punctuated_word') or word.get('word') or '').strip()
            start, end = float(word['start']), float(word['end'])
            if not token or not np.isfinite(start + end) or start < 0 or end <= start or end > cursor + 0.05:
                raise ValueError('invalid word timing')
            if parsed and start < parsed[-1][1]:
                raise ValueError('out of order words')
            parsed.append((token, start, end))
        except (KeyError, TypeError, ValueError):
            parsed = []
            break
    normalize = lambda value: re.sub(r'\W+', '', value).lower()
    if not parsed or normalize(' '.join(w[0] for w in parsed)) != normalize(text):
        voiced = [info or unknown for audio, info in slices
                  if len(audio) and np.sqrt(np.mean(np.asarray(audio) ** 2)) >= 0.005]
        identities = {info[0] for info in voiced}
        info = voiced[0] if len(identities) == 1 and next(iter(identities)) > 0 else unknown
        return [(text, info, cursor)] if text else []
    turns = []
    for token, start, end in parsed:
        scores, infos = {}, {}
        for a, b, info in intervals:
            overlap = max(0.0, min(b, end) - max(a, start))
            if overlap:
                key = info[0]
                scores[key] = scores.get(key, 0.0) + overlap
                infos[key] = info
        winner = max(scores, key=scores.get) if scores else 0
        info = infos[winner] if winner > 0 and scores[winner] / (end - start) >= 0.6 else unknown
        if turns and turns[-1][1] == info:
            old_text, _, duration = turns[-1]
            # CJK(일본어/중국어) 문자 및 문장부호 결합 시 불필요한 공백 분리 방지
            needs_no_space = bool(
                re.search(r'[\u3040-\u30ff\u4e00-\u9fff]$', old_text) and
                re.search(r'^[\u3040-\u30ff\u4e00-\u9fff、。！？]', token)
            ) or token in ('、', '。', '！', '？', '…', '」', '』', ')', ']', '}', ':', ';', ',', '.')
            sep = '' if needs_no_space else ' '
            turns[-1] = (old_text + sep + token, info, duration + end - start)
        else:
            turns.append((token, info, end - start))
    return turns
