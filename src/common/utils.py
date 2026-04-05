from aqt import mw
from aqt.utils import showCritical


LOGGING_ON = 1


def ensure_main_window():
    if mw:
        return mw
    showCritical("Main window not found")
    return None
