import threading


class BaseWorker:
    def __init__(self, callbacks=None):
        self.callbacks = callbacks or {}
        self._lock = threading.Lock()
        self._is_cancelled = False
        self._thread = None

    def cancel(self):
        with self._lock:
            self._is_cancelled = True

    @property
    def is_cancelled(self):
        with self._lock:
            return self._is_cancelled

    def _emit_progress(self, value, maximum):
        cb = self.callbacks.get('on_progress')
        if cb:
            cb(value, maximum)

    def _emit_chunk_progress(self, value, maximum):
        cb = self.callbacks.get('on_chunk_progress')
        if cb:
            cb(value, maximum)

    def _emit_status(self, text, color='#333333'):
        cb = self.callbacks.get('on_status')
        if cb:
            cb(text, color)

    def _emit_error(self, message):
        cb = self.callbacks.get('on_error')
        if cb:
            cb(message)

    def _emit_complete(self, result):
        cb = self.callbacks.get('on_complete')
        if cb:
            cb(result)

    def _emit_file_info(self, info):
        cb = self.callbacks.get('on_file_info')
        if cb:
            cb(info)

    def _ask_retry(self, title, message):
        cb = self.callbacks.get('on_ask_retry')
        if cb:
            return cb(title, message)
        return False