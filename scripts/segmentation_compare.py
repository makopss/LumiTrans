"""Write old-vs-new segmentation comparison JSON. No live services."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.segmentation_replay import build_report


def main():
    parser = argparse.ArgumentParser(description='Replay Deepgram-like events through old and new segmenters.')
    parser.add_argument('--jsonl', help='Optional PipelineTrace or raw Deepgram JSONL')
    parser.add_argument('--out', default=str(ROOT / 'output/segmentation-review-2026-09-17/comparison.json'))
    args = parser.parse_args()
    report = build_report(args.jsonl)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pairs = report['provided_log_pairs']
    print(json.dumps({
        'wrote': str(dest),
        'pairs_old_segments': pairs['old']['shape']['count'],
        'pairs_new_segments': pairs['new']['shape']['count'],
        'pairs_old_tail': pairs['old']['shape']['terminal_then_unterminated_tail']['count'],
        'pairs_new_tail': pairs['new']['shape']['terminal_then_unterminated_tail']['count'],
        'new_conserved': pairs['new']['conserved'],
        'never_thought': pairs['new']['phrases']['never_thought_joined'],
        'come_out': pairs['new']['phrases']['come_out_joined'],
        'live_jsonl_events': report['live_jsonl']['events'],
        'live_jsonl_note': report['live_jsonl'].get('note'),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    raise SystemExit(main() or 0)
