from dataclasses import dataclass
import queue
import numpy as np


@dataclass(frozen=True)
class CapturedAudio:
    """Capture-time isolation, never inferred later from mutable UI settings."""
    samples: np.ndarray
    channels_separated: bool = False
    start_sample: int | None = None
    session_id: str | None = None
    speech_end: bool = False
    stt_provider: str | None = None


def offer_queue(target, item) -> bool:
    """상한이 찬 큐는 가장 오래된 항목을 버리고 새 항목을 넣는다."""
    try:
        target.put_nowait(item)
        return True
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        try:
            target.put_nowait(item)
            return True
        except queue.Full:
            return False
