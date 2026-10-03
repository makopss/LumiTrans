"""Single-owner, dependency-free segmentation of finalized streaming words.

ASR finality, acoustic endpoints, and translation boundaries are separate.
Interim text never enters a committed segment. All clocks are monotonic.
"""
from dataclasses import dataclass, asdict
import re
import time


@dataclass
class Word:
    text: str
    speaker: object = None
    start: float | None = None
    end: float | None = None
    arrived: float = 0.0


@dataclass
class SpeechSegment:
    id: str
    session: str
    text: str
    speaker: object
    start: float | None
    end: float | None
    reason: str
    partial: bool
    committed_at: float

    def as_dict(self):
        return asdict(self)


def lexical(text):
    return re.sub(r"[^a-z0-9']", '', text.lower().replace('’', "'"))


class SpeechSegmenter:
    # Strong dependencies only. "know", "up", "do", "this" are NOT banned.
    DEPENDENT = set(('a an the my your his her our their of to in for with on at '
                     'from by about into between without and but or because although '
                     'if unless while than which whose i he she we they is are was '
                     'were be been being have has had will would shall should can could may might must '
                     'not never very so').split()) | {"i'm", "you're", "we're", "they're"}
    NONTERMINAL = {'come', 'comes', 'coming', 'new', 'such', 'those', 'these'}
    ABBREVIATIONS = {'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'vs.',
                     'etc.', 'e.g.', 'i.e.', 'st.'}
    CONNECTORS = {'and', 'but', 'so', 'because', 'while', 'although', 'yet'}
    SUBJECTS = {'i', 'you', 'he', 'she', 'we', 'they', 'it', 'the', 'this', 'that'}
    SHORT_RESPONSES = {'yes', 'no', 'yeah', 'yep', 'okay', 'ok', 'right', 'sure',
                       'hello', 'hi', 'bye', 'thanks', 'thank you', 'sorry', 'please',
                       'wow', 'really', 'why', 'what', 'stop', 'help', 'run', 'go',
                       'exactly', 'great', 'cool', 'i know', 'i grew up', 'i do',
                       'i did', 'i can', 'i will'}

    @classmethod
    def short_response(cls, words):
        return ' '.join(lexical(w.text) for w in words) in cls.SHORT_RESPONSES

    def __init__(self, short_wait=0.35, soft_seconds=3.0, hard_seconds=5.0,
                 target_words=16, max_words=28):
        self.short_wait = short_wait
        self.soft_seconds = soft_seconds
        self.hard_seconds = hard_seconds
        self.target_words = target_words
        self.max_words = max_words
        self.session = ''
        self.pending = []
        self.sequence = 0
        self.final_word_end = -1.0
        self.audio_end = 0.0
        self.endpoint = None
        self.interim_since = None
        self.activity_end = -1.0

    @staticmethod
    def terminal(text):
        token = text.rstrip('"\'”’)]}')
        if not token.endswith(('.', '?', '!')) or token.endswith('...'):
            return False
        if token.lower() in SpeechSegmenter.ABBREVIATIONS:
            return False
        if re.fullmatch(r'(?:[A-Za-z]\.)+', token):
            return False
        return True

    @classmethod
    def safe_end(cls, words, right=None):
        if not words:
            return False
        last = lexical(words[-1].text)
        if cls.terminal(words[-1].text) and cls.short_response(words):
            return True
        if last in cls.DEPENDENT:
            return False
        if last in cls.NONTERMINAL and not cls.terminal(words[-1].text):
            return False
        if len(words) > 1 and lexical(words[-2].text) in {'and', 'or', 'because'}:
            return False
        if right:
            # Keep names, negatives, numbers/units and common phrasal verbs intact.
            first = lexical(right[0].text)
            if (last, first) in {('come', 'out'), ('comes', 'out'), ('came', 'out'),
                                 ('coming', 'out'), ('look', 'up'), ('looked', 'up'),
                                 ('give', 'up'), ('gave', 'up'), ('find', 'out'),
                                 ('found', 'out'), ('not', 'only')}:
                return False
            if first in {'not', 'never'} or (last.isdigit() and first in
                    {'percent', 'dollars', 'meters', 'miles', 'kg', 'km', 'million', 'billion'}):
                return False
            if words[-1].text.istitle() and right[0].text.istitle():
                return False
        return True

    @staticmethod
    def render(words):
        return re.sub(r'\s+([,.;:?!])', r'\1', ' '.join(w.text for w in words)).strip()

    def _complete_turn(self, words):
        return bool(words) and self.terminal(words[-1].text) and self.safe_end(words)

    @staticmethod
    def _majority_speaker(words):
        votes = {}
        for word in words:
            votes[word.speaker] = votes.get(word.speaker, 0) + 1
        return max(votes, key=votes.get)

    def _hold_speaker(self, word):
        previous = self.pending[-1].speaker
        if previous is None:
            for held in self.pending:
                if held.speaker is None:
                    held.speaker = word.speaker
            return
        word.speaker = previous

    def _emit(self, count, reason, now):
        words, self.pending = self.pending[:count], self.pending[count:]
        self.sequence += 1
        partial = not self.safe_end(words) or reason == 'deadline'
        return SpeechSegment(f'{self.session}:{self.sequence}', self.session,
                             self.render(words), self._majority_speaker(words),
                             words[0].start, words[-1].end, reason, partial, now)

    def flush(self, reason='stop', now=None):
        now = time.monotonic() if now is None else now
        self.endpoint = None
        return [self._emit(len(self.pending), reason, now)] if self.pending else []

    def _sentence_count(self, now):
        ends = [i + 1 for i, w in enumerate(self.pending)
                if self.terminal(w.text) and self.safe_end(self.pending[:i + 1])]
        if not ends:
            return 0
        first = ends[0]
        if first >= 4:
            return first if first <= self.max_words else 0
        # Combine adjacent short reactions, never a short reply with a long sentence.
        count = first
        for end in ends[1:]:
            if end - count >= 4:
                if self.short_response(self.pending[:first]):
                    return count
                return end if end <= self.max_words else 0
            count = end
            if count >= 4:
                return count
        if now - self.pending[0].arrived >= self.short_wait and all(
                self.short_response(self.pending[a:b])
                for a, b in zip([0] + ends[:-1], ends)):
            return count
        return 0

    def _age(self, now):
        first = self.pending[0]
        audio_age = self.audio_end - first.start if first.start is not None else 0
        return max(now - first.arrived, audio_age)

    def _clause_count(self):
        candidates = []
        for i in range(4, min(len(self.pending), self.max_words) + 1):
            left, right = self.pending[:i], self.pending[i:]
            if not self.safe_end(left, right):
                continue
            punctuation = left[-1].text.rstrip('"\'”’').endswith((',', ';', ':', '—'))
            connector = (len(right) >= 3 and lexical(right[0].text) in self.CONNECTORS
                         and lexical(right[1].text) in self.SUBJECTS)
            gap = (right and left[-1].end is not None and right[0].start is not None
                   and right[0].start - left[-1].end >= 0.45)
            if punctuation or connector or gap:
                candidates.append(i)
        return min(candidates, key=lambda i: abs(i - self.target_words)) if candidates else 0

    def _drain(self, now):
        output = []
        while self.pending:
            count = self._sentence_count(now)
            if count:
                output.append(self._emit(count, 'sentence', now))
                continue
            age = self._age(now)
            if len(self.pending) >= self.target_words or age >= self.soft_seconds:
                count = self._clause_count()
                if count:
                    output.append(self._emit(count, 'clause', now))
                    continue
            if len(self.pending) >= self.max_words or age >= self.hard_seconds:
                # Preserve a dependent tail for the next segment when possible.
                limit = min(len(self.pending), self.max_words)
                count = next((i for i in range(limit, 3, -1)
                              if self.safe_end(self.pending[:i], self.pending[i:])), 0)
                if count:
                    output.append(self._emit(count, 'deadline', now))
                    continue
                # Small unfinished phrases get a bounded grace period; never dropped.
                if age >= self.hard_seconds + 1.0 or len(self.pending) >= self.max_words + 4:
                    output.append(self._emit(limit, 'deadline', now))
                    continue
            break
        return output

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        output = self._drain(now)
        if self.endpoint and now >= self.endpoint[1]:
            cutoff, _ = self.endpoint
            self.endpoint = None
            count = 0
            for word in self.pending:
                if word.end is not None and cutoff is not None and word.end > cutoff + 1e-6:
                    break
                count += 1
            if count:
                output.append(self._emit(count, 'speech_end', now))
        return output

    def accept(self, event, now=None):
        now = time.monotonic() if now is None else now
        output = []
        session = str(event.get('session_id', self.session or 'local'))
        if session != self.session:
            output.extend(self.flush('session_change', now))
            self.session = session
            self.final_word_end = -1.0
            self.audio_end = 0.0
            self.interim_since = None
            self.activity_end = -1.0
        kind = event.get('type')
        if kind in {'Disconnected', 'Closed'}:
            output.extend(self.flush('connection_end', now))
            self.interim_since = None
            return output
        if kind == 'SpeechStarted':
            self.endpoint = None
            self.activity_end = max(self.activity_end, event.get('timestamp', -1))
            return output
        if kind == 'UtteranceEnd':
            marker = event.get('last_word_end', -1)
            if marker is not None and marker >= 0 and self.pending:
                if self.activity_end > marker + 1e-6:
                    return output + self.tick(now)
                # A late endpoint must not flush words spoken after its marker.
                if self.pending[0].start is None or self.pending[0].start <= marker:
                    self.endpoint = (marker, now + (0 if self.safe_end(self.pending) else 0.35))
            return output + self.tick(now)
        if kind != 'Results':
            return output
        alt = (event.get('channel', {}).get('alternatives') or [{}])[0]
        transcript = alt.get('transcript', '').strip()
        raw_words = alt.get('words') or []
        if not event.get('is_final'):
            if transcript:
                self.interim_since = self.interim_since if self.interim_since is not None else now
                if raw_words and self.endpoint:
                    newest = max((w.get('end', -1) for w in raw_words), default=-1)
                    if self.endpoint[0] is None or newest > self.endpoint[0]:
                        self.endpoint = None
                if raw_words:
                    self.activity_end = max(self.activity_end,
                                            max((w.get('end', -1) for w in raw_words), default=-1))
            return output + self.tick(now)
        self.interim_since = None
        if raw_words:
            incoming = [Word(w.get('punctuated_word') or w.get('word', ''),
                             w.get('speaker'), w.get('start'), w.get('end'), now)
                        for w in raw_words if w.get('punctuated_word') or w.get('word')]
            incoming = [w for w in incoming if w.end is None or w.end > self.final_word_end + 1e-6]
        else:
            incoming = [Word(t, event.get('speaker'), arrived=now) for t in transcript.split()]
        if incoming:
            self.endpoint = None
        for word in incoming:
            if self.pending and word.speaker != self.pending[-1].speaker:
                if self._complete_turn(self.pending):
                    output.extend(self._drain(now))
                    output.extend(self.flush('speaker_change', now))
                else:
                    self._hold_speaker(word)
            self.pending.append(word)
            if word.end is not None:
                self.final_word_end = max(self.final_word_end, word.end)
                self.audio_end = max(self.audio_end, word.end)
        output.extend(self._drain(now))
        if event.get('speech_final') and self.pending:
            if raw_words:
                cutoff = max((w.get('end', -1) for w in raw_words), default=-1)
            elif 'start' in event and 'duration' in event:
                cutoff = event['start'] + event['duration']
            else:
                cutoff = self.final_word_end if self.final_word_end >= 0 else None
            if cutoff is None or self.activity_end <= cutoff + 1e-6:
                self.endpoint = (cutoff, now + (self.short_wait if self.safe_end(self.pending) else 1.0))
        return output
