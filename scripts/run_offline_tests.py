"""Run the release regressions and selected existing tests without devices/services.

The excluded manual/integration scripts load models, capture the desktop, play
audio or call paid services and must be exercised separately on target hardware.
"""
import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(QT_QPA_PLATFORM='offscreen', HF_HUB_OFFLINE='1',
                  TRANSFORMERS_OFFLINE='1', PYGAME_HIDE_SUPPORT_PROMPT='1')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'output' / 'review-2026-09-16' / 'after-fixes.json'
    sources = list((ROOT / 'src').glob('*.py')) + [ROOT / 'run.py']
    tests = list((ROOT / 'tests').glob('test_*.py'))
    syntax_errors = []
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for path in sources + tests:
        try:
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        except SyntaxError as error:
            syntax_errors.append(f'{path.name}: {error}')
    if syntax_errors:
        print(json.dumps({'syntax_errors': syntax_errors}, ensure_ascii=False))
        return 1

    from PyQt6.QtWidgets import QApplication, QMessageBox
    from src.stt_engine import STTWorker
    from src.speaker_identifier import SpeakerIdentifier
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    groups = {}
    with ExitStack() as guards:
        for guard in (
            patch.object(STTWorker, '_load_model'),
            patch.object(SpeakerIdentifier, '_ensure_model_loaded', return_value=False),
            patch('src.process_volume.set_process_volume'),
            patch('socket.socket.connect', side_effect=AssertionError('Network disabled for offline tests')),
            patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes),
            patch.object(QMessageBox, 'information', return_value=QMessageBox.StandardButton.Ok),
        ):
            guards.enter_context(guard)
        regression = load('release_regressions', ROOT / 'tests/test_release_regressions.py')
        tempo = load('existing_tempo', ROOT / 'tests/test_tempo_presets.py')
        streaming = load('streaming_segmentation', ROOT / 'tests/test_streaming_segmentation.py')
        replay = load('segmentation_replay', ROOT / 'tests/test_segmentation_replay.py')
        overlay = load('typewriter_overlay', ROOT / 'tests/test_typewriter_and_dangling.py')
        overlay_geom = load('overlay_geometry', ROOT / 'tests/test_overlay_resize_and_monitor.py')
        panel_layout = load('control_panel_layout', ROOT / 'tests/test_control_panel_layout.py')
        test_audio_ducking = load('test_audio_ducking', ROOT / 'tests/test_audio_ducking.py')
        test_subtitle_history = load('test_subtitle_history', ROOT / 'tests/test_subtitle_history.py')
        test_screen_ocr = load('test_screen_ocr', ROOT / 'tests/test_screen_ocr.py')
        existing = unittest.TestSuite([
            unittest.defaultTestLoader.loadTestsFromModule(tempo),
            unittest.defaultTestLoader.loadTestsFromModule(test_audio_ducking),
            unittest.defaultTestLoader.loadTestsFromModule(overlay),
            unittest.defaultTestLoader.loadTestsFromModule(overlay_geom),
            unittest.defaultTestLoader.loadTestsFromModule(panel_layout),
        ])
        for name in ('test_time_formatters', 'test_manager_core_operations', 'test_export_srt_and_txt'):
            existing.addTest(unittest.FunctionTestCase(getattr(test_subtitle_history, name)))
        excluded_screen = {'test_ocr_and_translation', 'test_inplace_overlay_and_hotkey'}
        for name, function in vars(test_screen_ocr).items():
            if name.startswith('test_') and callable(function) and name not in excluded_screen:
                existing.addTest(unittest.FunctionTestCase(function))
        segmentation = unittest.TestSuite([
            unittest.defaultTestLoader.loadTestsFromModule(streaming),
            unittest.defaultTestLoader.loadTestsFromModule(replay),
        ])
        for name, suite in (
            ('release_regressions', unittest.defaultTestLoader.loadTestsFromModule(regression)),
            ('segmentation', segmentation),
            ('existing_selected', existing),
        ):
            log = io.StringIO()
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            groups[name] = dict(run=result.testsRun,
                passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                failed=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                log=log.getvalue())
            print(name, {k: v for k, v in groups[name].items() if k != 'log'})
    changed = [name for name, digest in hashes.items()
               if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    report = dict(syntax_passed=len(sources)+len(tests), groups=groups,
                  source_sha256=hashes, sources_changed_during_run=changed,
                  scope='Offline selected tests; no real model, GPU, audio or external API validation.')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Results: {dest}')
    return int(bool(changed) or any(g['failed'] or g['errors'] for g in groups.values()))


if __name__ == '__main__':
    raise SystemExit(main())
