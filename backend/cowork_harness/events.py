"""Coalesce answer fragments while flushing lifecycle events immediately."""
import asyncio


class DeltaBuffer:
    def __init__(self, sink, interval=0.05, max_chars=2048):
        self.sink, self.interval, self.max_chars = sink, interval, max_chars
        self.parts = []
        self.size = 0
        self.timer = None
        self.error = None

    def emit(self, event):
        if self.error:
            raise self.error
        if event['type'] != 'step.delta':
            self.flush()
            self.sink(event)
            return
        self.parts.append(event['delta'])
        self.size += len(event['delta'])
        if self.size >= self.max_chars:
            self.flush()
        elif self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(self.interval, self._tick)

    def _tick(self):
        try:
            self.flush()
        except Exception as exc:
            self.error = exc

    def flush(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.parts:
            text = ''.join(self.parts)
            self.parts.clear()
            self.size = 0
            self.sink({'type': 'step.delta', 'delta': text})

    def close(self):
        self.flush()
        if self.error:
            raise self.error

    def discard(self):
        if self.timer:
            self.timer.cancel()
        self.timer = None
        self.parts.clear()
        self.size = 0
        self.error = None
