"""Replay Deepgram-like events through the frozen pre-change assembler and SpeechSegmenter.

No network, models, or audio. A live JSONL is optional; missing files are reported,
not invented.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

from src.speech_segmenter import SpeechSegmenter

ROOT = Path(__file__).resolve().parents[1]
LEGACY_STT = ROOT / 'output/segmentation-review-2026-09-17/before-implementation/stt_engine.py'
PROVIDED_PAIRS = ROOT / 'output/segmentation-review-2026-09-17/provided-log-pairs.json'
TRACE_LOG = ROOT / 'output/logs/translation.jsonl'

TERMINALS = ('.', '?', '!')


def lexical_join(texts):
    return re.sub(r'\s+', ' ', ' '.join(texts)).strip()


def result_event(text, start=0.0, speaker=0, final=True, endpoint=False, session='replay'):
    words = []
    cursor = float(start)
    for token in text.split():
        words.append({
            'word': token.rstrip('.?!,;:'),
            'punctuated_word': token,
            'start': cursor,
            'end': cursor + 0.1,
            'speaker': speaker,
            'confidence': 0.95,
        })
        cursor += 0.1
    duration = max(0.1, cursor - start)
    return {
        'type': 'Results',
        'session_id': session,
        'is_final': final,
        'speech_final': endpoint,
        'start': start,
        'duration': duration,
        'channel': {'alternatives': [{'transcript': text, 'words': words}]},
    }


_DETECTOR = None


def load_legacy_detector(path=LEGACY_STT):
    global _DETECTOR
    if _DETECTOR is not None and path == LEGACY_STT:
        return _DETECTOR
    tree = ast.parse(path.read_bytes(), filename=str(path))
    detector = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == 'SemanticClauseDetector')
    namespace = {'re': re}
    exec(compile(ast.Module(body=[detector], type_ignores=[]), str(path), 'exec'), namespace)
    loaded = namespace['SemanticClauseDetector']
    if path == LEGACY_STT:
        _DETECTOR = loaded
    return loaded


class LegacyAssembler:
    """Frozen 2026-09-17 Deepgram text callback + sentence_buffer policy."""

    def __init__(self, detector=None, max_clause_words=12):
        self.detector = detector or load_legacy_detector()
        self.max_clause_words = max_clause_words
        self.sentence_buffer = []
        self.current_speaker = None
        self.last_final_text = ''
        self.emitted = []

    def accept(self, event):
        kind = event.get('type')
        if kind == 'UtteranceEnd':
            return
        if kind != 'Results' or not event.get('is_final'):
            return
        alt = (event.get('channel', {}).get('alternatives') or [{}])[0]
        transcript = (alt.get('transcript') or '').strip()
        if not transcript:
            return
        if transcript == self.last_final_text:
            return
        self.last_final_text = transcript
        words = alt.get('words') or []
        speakers = [word.get('speaker') for word in words if word.get('speaker') is not None]
        speaker = Counter(speakers).most_common(1)[0][0] if speakers else event.get('speaker')
        self._on_final(transcript, speaker)

    def flush(self):
        text = ' '.join(self.sentence_buffer).strip()
        self.sentence_buffer = []
        if text:
            self.emitted.append(text)
        return list(self.emitted)

    def _on_final(self, text, speaker):
        mapped = None if speaker is None else (int(speaker) + 1, f'화자 {int(speaker) + 1}', '')
        if self.sentence_buffer and self.current_speaker and mapped:
            if self.current_speaker[0] != mapped[0]:
                previous = ' '.join(self.sentence_buffer).strip()
                if previous:
                    self.emitted.append(previous)
                self.sentence_buffer = []
                self.current_speaker = mapped
        if not self.sentence_buffer and mapped:
            self.current_speaker = mapped
        self.sentence_buffer.append(text)
        accumulated = ' '.join(self.sentence_buffer).strip()
        words = accumulated.split()
        has_terminal = accumulated.endswith(('.', '?', '!', '."', '?"', '!"', ".'", "?'", "!'"))
        dangling = self.detector.is_dangling(accumulated)
        complete = has_terminal and not dangling
        try:
            complete = complete or self.detector.is_complete_sentence(accumulated)
        except Exception:
            pass
        split = self.detector.check_clause_boundary(accumulated, text, max_words=self.max_clause_words)
        if (complete or split or len(words) >= self.max_clause_words) and not dangling:
            self.sentence_buffer = []
            self.emitted.append(accumulated)
            self.current_speaker = None


def replay_current(events, now_step=0.1, settle=0.4):
    segmenter = SpeechSegmenter()
    emitted = []
    now = 0.0
    for event in events:
        now += now_step
        received = event.get('received_at')
        if received is not None:
            now = max(now, float(received))
        emitted.extend(segmenter.accept(event, now=now))
        now += settle
        emitted.extend(segmenter.tick(now=now))
    emitted.extend(segmenter.flush(now=now + 5))
    return emitted


def replay_legacy(events, max_clause_words=12):
    assembler = LegacyAssembler(max_clause_words=max_clause_words)
    for event in events:
        assembler.accept(event)
    assembler.flush()
    return assembler.emitted


def events_from_pairs(pairs, session='pairs'):
    events = []
    position = 0.0
    for pair in pairs:
        text = pair['original']
        events.append(result_event(text, start=position, session=session))
        position += max(0.2, 0.1 * max(1, len(text.split())))
    return events


def events_from_jsonl(path):
    events = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        payload = record.get('payload', record)
        if record.get('event') not in (None, 'deepgram') and 'type' not in payload:
            continue
        if payload.get('type') in {'Results', 'UtteranceEnd', 'SpeechStarted', 'Disconnected', 'Closed'}:
            cleaned = {key: value for key, value in payload.items()
                       if 'key' not in key.lower() and 'token' not in key.lower()
                       and 'authorization' not in key.lower()}
            events.append(cleaned)
    return events


def shape_metrics(texts):
    no_terminal = []
    tail = []
    single_tail = []
    for index, text in enumerate(texts, start=1):
        stripped = text.strip()
        ends = stripped.endswith(TERMINALS) or stripped.endswith(('."', '?"', '!"', ".'", "?'", "!'"))
        mid = bool(re.search(r'[.?!]["\')\]]*\s+\S', stripped))
        if not ends:
            no_terminal.append(index)
        if mid and not ends:
            tail.append(index)
            remainder = re.split(r'[.?!]["\')\]]*\s+', stripped)[-1]
            if 0 < len(remainder.split()) <= 1:
                single_tail.append(index)
    return {
        'count': len(texts),
        'no_terminal': {'count': len(no_terminal), 'ids': no_terminal},
        'terminal_then_unterminated_tail': {'count': len(tail), 'ids': tail},
        'terminal_then_single_word_unterminated_tail': {'count': len(single_tail), 'ids': single_tail},
    }


def phrase_flags(texts):
    joined = lexical_join(texts)
    return {
        'never_thought_joined': bool(re.search(r'I never Thought', joined)),
        'come_out_joined': 'come Out' in joined,
        'token_count': len(joined.split()),
    }


def compare_runs(events, source_tokens=None, max_clause_words=12):
    old_texts = replay_legacy(events, max_clause_words=max_clause_words)
    new_segments = replay_current(events)
    new_texts = [item.text for item in new_segments]
    source = source_tokens or lexical_join(
        ((event.get('channel', {}).get('alternatives') or [{}])[0].get('transcript') or '')
        for event in events if event.get('type') == 'Results' and event.get('is_final'))
    new_join = lexical_join(new_texts)
    old_join = lexical_join(old_texts)
    mixed_speakers = 0
    for segment in new_segments:
        if isinstance(segment.speaker, (list, tuple, set, frozenset)) and len(set(segment.speaker)) > 1:
            mixed_speakers += 1
    return {
        'old': {'texts': old_texts, 'shape': shape_metrics(old_texts), 'phrases': phrase_flags(old_texts),
                'conserved': old_join == source if source else None},
        'new': {'texts': new_texts, 'shape': shape_metrics(new_texts), 'phrases': phrase_flags(new_texts),
                'conserved': new_join == source if source else None,
                'mixed_speaker_segments': mixed_speakers},
        'source_tokens': len(source.split()) if source else 0,
    }


def _utterance_end(marker, session='replay'):
    return {'type': 'UtteranceEnd', 'session_id': session, 'last_word_end': marker}


def synthetic_plan_events():
    return [
        result_event('Page.'),
        _utterance_end(0.1),
        result_event('That is the answer. I', start=1),
        result_event('think we should leave.', start=2),
        _utterance_end(2.8),
        result_event('We finally found the answer to the difficult question today. Tomorrow', start=4),
        _utterance_end(5.5),
        result_event('The team finally completed the difficult work after several attempts', start=7),
        _utterance_end(8.5),
        result_event('I know.', start=10),
        _utterance_end(10.3),
        result_event('After several attempts the team solved the problem,', start=12),
        _utterance_end(13.5),
        result_event('Yes.', start=15, speaker=0),
        result_event('Yes.', start=17, speaker=1),
        _utterance_end(18.0),
    ]


def load_provided_pairs():
    return json.loads(PROVIDED_PAIRS.read_text(encoding='utf-8'))['pairs']


def build_report(jsonl_path=None):
    pairs = load_provided_pairs()
    pair_events = events_from_pairs(pairs)
    pair_source = lexical_join(item['original'] for item in pairs)
    report = {
        'scope': 'Offline old-vs-new segmentation replay. Not live audio accuracy.',
        'provided_log_pairs': compare_runs(pair_events, source_tokens=pair_source, max_clause_words=12),
        'synthetic_plan_cases': compare_runs(synthetic_plan_events(), max_clause_words=12),
        'live_jsonl': None,
    }
    path = Path(jsonl_path) if jsonl_path else TRACE_LOG
    if path.is_file():
        events = events_from_jsonl(path)
        try:
            shown = str(path.relative_to(ROOT))
        except ValueError:
            shown = str(path)
        report['live_jsonl'] = {
            'path': shown,
            'events': len(events),
            'comparison': compare_runs(events) if events else None,
        }
    else:
        report['live_jsonl'] = {
            'path': str(path),
            'events': 0,
            'comparison': None,
            'note': 'No Deepgram JSONL on disk. Capture one live session to compare packet boundaries.',
        }
    return report
