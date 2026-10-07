"""Exercise production subtitle methods with a manual timer, without Qt/devices.

This checks text lifecycle logic only; actual Qt rendering needs GUI validation.
"""
import ast
from pathlib import Path
import re
import time
import unittest
from unittest.mock import Mock


class ManualTimer:
    def __init__(self, parent=None):
        self.active = False
        self.callbacks = []
        self.timeout = Mock()
        self.timeout.connect.side_effect = self.callbacks.append

    def start(self, interval):
        self.active = True

    def stop(self):
        self.active = False

    def isActive(self):
        return self.active

    def tick(self):
        if self.active:
            for callback in self.callbacks:
                callback()


def load_subtitle_methods():
    source = Path(__file__).resolve().parents[1] / 'src' / 'overlay_window.py'
    tree = ast.parse(source.read_bytes(), filename=str(source))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == 'SubtitleOverlay')
    names = {'display_subtitle', 'fade_or_clear_subtitles',
             '_html_body', '_set_label_html', '_translated_color', '_original_color',
             '_get_subtitle_duration'}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in names]
    from src.subtitle_manager import smart_break_sentences, break_korean_sentences, break_subtitle_text
    namespace = {
        're': re, 'time': time, 'QTimer': ManualTimer,
        'smart_break_sentences': smart_break_sentences,
        'break_korean_sentences': break_korean_sentences,
        'break_subtitle_text': break_subtitle_text,
    }
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)
    return type('SubtitleHarness', (), {name: namespace[name] for name in names
                                       if name in namespace})


class TestOverlayTypewriter(unittest.TestCase):
    def setUp(self):
        self.overlay = load_subtitle_methods()()
        self.overlay._audio_paused = False
        self.overlay.config = {'typewriter_effect': True}
        self.overlay.label_original = Mock()
        self.overlay.label_translated = Mock()
        self.overlay._auto_fit_text = Mock()
        self.overlay.update_badge = Mock()
        self.overlay.update = Mock()
        self.overlay.clear_timer = ManualTimer()

    def display(self, text):
        self.overlay.display_subtitle('original', text)

    def assert_text(self, text):
        wrapped = self.overlay._html_body(text, self.overlay._translated_color(), center=True)
        self.overlay.label_translated.setText.assert_called_with(wrapped)

    def test_korean_is_shown_complete_immediately(self):
        text = '흥미로운 관점이네요 아직 출력 중입니다'
        self.display(text)
        self.assertFalse(hasattr(self.overlay, '_typewriter_timer'))
        self.assert_text(text)
        orig_wrapped = self.overlay._html_body('original', self.overlay._original_color(), center=True)
        self.overlay.label_original.setText.assert_called_with(orig_wrapped)

    def test_successive_subtitles_replace_immediately(self):
        for text in ('흥미로운 관점이네요', '이것은 새로운 자막입니다', '다음 문장도 유지됩니다'):
            self.display(text)
            self.assert_text(text)

    def test_clear_shows_ellipsis(self):
        self.display('흥미로운 관점이네요')
        self.overlay.fade_or_clear_subtitles()
        self.assert_text('...')

    def test_latest_speaker_tag_and_exact_spacing_are_preserved(self):
        self.display('<span style="color:red">[A]</span> 첫 번째 문장')
        text = '<span style="color:blue">[B]</span> 두 번째  문장입니다'
        self.display(text)
        self.assert_text(text)

    def test_english_and_korean_html_are_centered(self):
        body = self.overlay._html_body('Hello', '#CCCCCC', center=True)
        self.assertIn('text-align:center', body)
        self.assertIn('Hello', body)


if __name__ == '__main__':
    unittest.main()
