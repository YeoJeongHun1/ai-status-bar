"""
오류 로그 — --windowed 빌드는 예외가 화면에 안 보이므로 파일에 남긴다.

- 위치: %LOCALAPPDATA%\\AIStatusBar\\logs\\error.log (256KB × 3개 회전). macOS 는 ~/Library/Logs/AIStatusBar/error.log
- 남기는 것: 잡히지 않은 예외(메인·스레드·tk 콜백)와 코드가 명시적으로 warn() 한 것뿐. 요청·응답·사용량 값은 남기지 않는다.
- 마스킹: 토큰처럼 보이는 문자열(sk-ant-…, eyJ… JWT, Bearer …)과 경로의 사용자 이름(C:\\Users\\<이름>)을 가린 뒤 쓴다.
"""
import logging
import logging.handlers
import os
import re
import sys
import threading

if sys.platform == "darwin":
    LOG_DIR = os.path.expanduser("~/Library/Logs/AIStatusBar")
else:
    LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AIStatusBar", "logs")
LOG_PATH = os.path.join(LOG_DIR, "error.log")

_MASKS = (
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "sk-ant-***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}"), "<jwt>"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
    (re.compile(r"(?i)([A-Z]:\\Users\\)[^\\/\s\"']+"), r"\1<user>"),
    (re.compile(r"(/Users/|/home/)[^/\s\"']+"), r"\1<user>"),
)


def mask(text):
    s = str(text)
    for rx, rep in _MASKS:
        s = rx.sub(rep, s)
    return s


class _MaskingFormatter(logging.Formatter):
    def format(self, record):
        return mask(super().format(record))


_logger = None


def get():
    global _logger
    if _logger:
        return _logger
    lg = logging.getLogger("aistatusbar")
    lg.setLevel(logging.WARNING)
    lg.propagate = False
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=256 * 1024, backupCount=3, encoding="utf-8")
        h.setFormatter(_MaskingFormatter("%(asctime)s %(levelname)s %(message)s"))
        lg.addHandler(h)
    except Exception:
        lg.addHandler(logging.NullHandler())
    _logger = lg
    return lg


def warn(where, exc=None):
    """조용히 삼키던 예외를 한 줄로 남긴다. exc 가 없으면 메시지만."""
    try:
        if exc is not None:
            get().warning("%s: %s: %s", where, type(exc).__name__, exc)
        else:
            get().warning("%s", where)
    except Exception:
        pass


def install_crash_handlers(tk_root=None):
    """잡히지 않은 예외를 파일로: sys.excepthook · threading.excepthook · tk 콜백."""
    lg = get()

    def _hook(exc_type, exc, tb):
        lg.error("uncaught: %s", "".join(_format(exc_type, exc, tb)))
    sys.excepthook = _hook

    def _thook(args):
        lg.error("uncaught in thread %s: %s", args.thread.name if args.thread else "?",
                 "".join(_format(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = _thook

    if tk_root is not None:
        def _tk(exc_type, exc, tb):
            lg.error("uncaught in tk callback: %s", "".join(_format(exc_type, exc, tb)))
        tk_root.report_callback_exception = _tk


def _format(exc_type, exc, tb):
    import traceback
    return traceback.format_exception(exc_type, exc, tb)
