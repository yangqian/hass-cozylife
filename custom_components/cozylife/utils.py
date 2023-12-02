import json
import time
import requests
import logging

_LOGGER = logging.getLogger(__name__)

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

    domain = 'api-us.doiting.com'
    protocol = 'http'
    url_prefix = protocol + '://' + domain
    try:
        res = requests.get(url_prefix + '/api/device_product/model', params={'lang': lang}, timeout=3)
        res.raise_for_status()  # Raise an HTTPError for bad responses
    except requests.exceptions.RequestException as e:
        _LOGGER.error(f'Error making API request: {e}')
        return []

    try:
        pid_list = res.json()
    except json.JSONDecodeError as e:
        _LOGGER.error(f'Error decoding JSON response: {e}')
        return []

    if pid_list.get('ret') is None or pid_list['ret'] != '1':
        _LOGGER.info('get_pid_list.result is not as expected')
        return []

    info = pid_list.get('info')
    if info is None or not isinstance(info, dict) or info.get('list') is None or not isinstance(info['list'], list):
        _LOGGER.info('get_pid_list.result structure is not as expected')
        return []

    _CACHE_PID = info['list']
    return _CACHE_PID