"""Bounded local JSONL diagnostics. Only callers' explicit fields are recorded."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
import uuid


class PipelineTrace:
    def __init__(self, enabled=False, directory=None):
        self.session = uuid.uuid4().hex[:12]
        self.logger = None
        self.path = None
        if enabled:
            try:
                import sys
                if not directory:
                    if getattr(sys, "frozen", False):
                        directory = Path(sys.executable).resolve().parent / 'output' / 'logs'
                    else:
                        directory = Path(__file__).resolve().parents[1] / 'output' / 'logs'
                else:
                    directory = Path(directory)
                directory.mkdir(parents=True, exist_ok=True)
                self.path = directory / 'translation.jsonl'
                self.logger = logging.Logger(f'pipeline-{self.session}')
                handler = RotatingFileHandler(self.path, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(message)s'))
                self.logger.addHandler(handler)
            except OSError as error:
                print(f'[기록] 번역 로그를 열 수 없습니다: {error}')

    def record(self, kind, **fields):
        if self.logger:
            self.logger.info(json.dumps(dict(trace_session=self.session, event=kind,
                wall_time=time.time(), monotonic=time.monotonic(), **fields), ensure_ascii=False))

    def close(self):
        if self.logger:
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)
            self.logger = None
