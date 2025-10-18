import json
import time
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).with_name('model.json')


def get_sn() -> str:
    """
    message sn
    :return: str
    """
    return str(int(round(time.time() * 1000)))

# cache get_pid_list result for many calls
_CACHE_PID = []

def get_pid_list(lang='en') -> list:
    """
    http://doc.doit/project-12/doc-95/
    :param lang:
    :return:
    """
    global _CACHE_PID
    if len(_CACHE_PID) != 0:
        return _CACHE_PID

    try:
        raw = MODEL_PATH.read_text(encoding='utf-8')
    except FileNotFoundError:
        _LOGGER.error('Local device model cache not found: %s', MODEL_PATH)
        return []
    except OSError as err:
        _LOGGER.error('Unable to read local device model cache %s: %s', MODEL_PATH, err)
        return []

    try:
        pid_list = json.loads(raw)
    except json.JSONDecodeError as err:
        _LOGGER.error('Error decoding local device model cache %s: %s', MODEL_PATH, err)
        return []

    if isinstance(pid_list, dict):
        info = pid_list.get('info')
        if isinstance(info, dict):
            pid_list = info.get('list')

    if not isinstance(pid_list, list):
        _LOGGER.info('Local device model cache structure is not as expected')
        return []

    _CACHE_PID = pid_list
    return _CACHE_PID
