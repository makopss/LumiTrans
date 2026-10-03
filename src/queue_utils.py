"""Atomic look-ahead for the standard FIFO queues used by the pipeline."""
import time


def take_matching(work_queue, predicate, timeout=0.0):
    """Remove only a matching head; never move an unmatched item to the tail.

    Uses Queue's condition and deque under the same mutex as put/get. Task
    accounting is unchanged, just as for Queue.get(). Predicates must not
    call back into this queue.
    """
    deadline = time.monotonic() + timeout
    with work_queue.not_empty:
        while not work_queue._qsize():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            work_queue.not_empty.wait(remaining)
        if not predicate(work_queue.queue[0]):
            return None
        item = work_queue._get()
        work_queue.not_full.notify()
        return item
