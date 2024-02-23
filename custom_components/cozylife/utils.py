# -*- coding: utf-8 -*-
import json
import time
import logging
import pathlib

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
    
    #domain = 'api-us.doiting.com'
    #protocol = 'http'
    #url_prefix = protocol + '://' + domain
    #import requests
    #url='http://api-us.doiting.com/api/device_product/model'
    #res = requests.get(url, timeout=3)
    fn = pathlib.Path(__file__).parent / 'model.json'
    with open(fn, 'r') as f:
        res= f.readlines()
    try:
        pid_list = json.loads(res[0])
    except:
        _LOGGER.info('get_pid_list.result is not json')
        return []
    
    if pid_list.get('ret') is None:
        return []
    
    if '1' != pid_list['ret']:
        return []
    
    if pid_list.get('info') is None or type(pid_list.get('info')) is not dict:
        return []
    
    if pid_list['info'].get('list') is None or type(pid_list['info']['list']) is not list:
        return []
    
    _CACHE_PID = pid_list['info']['list']
    return _CACHE_PID
