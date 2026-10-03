import json
from pathlib import Path
import unittest

from src.segmentation_replay import (
    build_report, compare_runs, events_from_pairs, load_provided_pairs,
    replay_current, result_event, shape_metrics,
)


class SegmentationReplayTests(unittest.TestCase):
    def test_provided_pairs_new_path_conserves_tokens_and_joins_failures(self):
        pairs = load_provided_pairs()
        report = compare_runs(events_from_pairs(pairs),
                              source_tokens=' '.join(item['original'] for item in pairs))
        self.assertTrue(report['new']['conserved'])
        self.assertTrue(report['new']['phrases']['never_thought_joined'])
        self.assertTrue(report['new']['phrases']['come_out_joined'])
        self.assertEqual(report['new']['mixed_speaker_segments'], 0)
        self.assertLess(report['new']['shape']['terminal_then_unterminated_tail']['count'],
                        report['old']['shape']['terminal_then_unterminated_tail']['count'])

    def test_sentence_plus_tail_split_only_on_new_path(self):
        events = [result_event('That is the answer. I'), result_event('think we should leave.', start=1)]
        report = compare_runs(events)
        self.assertEqual(report['new']['texts'], ['That is the answer.', 'I think we should leave.'])
        self.assertTrue(any('That is the answer. I' in text for text in report['old']['texts']))

    def test_build_report_records_missing_live_jsonl(self):
        report = build_report(jsonl_path=str(Path('output/logs/translation.jsonl')))
        self.assertIn('provided_log_pairs', report)
        if report['live_jsonl']['events'] == 0:
            self.assertIsNone(report['live_jsonl']['comparison'])

    def test_shape_metrics_match_historical_pair_counts(self):
        texts = [item['original'] for item in load_provided_pairs()]
        metrics = shape_metrics(texts)
        saved = json.loads((Path(__file__).resolve().parents[1]
                            / 'output/segmentation-review-2026-09-17/log-metrics.json').read_text(encoding='utf-8'))
        self.assertEqual(metrics['no_terminal']['count'], saved['no_terminal']['count'])
        self.assertEqual(metrics['terminal_then_unterminated_tail']['count'],
                         saved['terminal_then_unterminated_tail']['count'])


if __name__ == '__main__':
    unittest.main()
