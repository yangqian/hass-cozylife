# -*- coding: utf-8 -*-
import json
import socket
import time
from typing import Optional, Union, Any
import logging
try:
  from .utils import get_pid_list, get_sn
except:
  from utils import get_pid_list, get_sn

CMD_INFO = 0
CMD_QUERY = 2
CMD_SET = 3
CMD_LIST = [CMD_INFO, CMD_QUERY, CMD_SET]
_LOGGER = logging.getLogger(__name__)


class tcp_client(object):
    """
    Represents a device
    send:{"cmd":0,"pv":0,"sn":"1636463553873","msg":{}}
    receiver:{"cmd":0,"pv":0,"sn":"1636463553873","msg":{"did":"629168597cb94c4c1d8f","dtp":"02","pid":"e2s64v",
    "mac":"7cb94c4c1d8f","ip":"192.168.123.57","rssi":-33,"sv":"1.0.0","hv":"0.0.1"},"res":0}

    send:{"cmd":2,"pv":0,"sn":"1636463611798","msg":{"attr":[0]}}
    receiver:{"cmd":2,"pv":0,"sn":"1636463611798","msg":{"attr":[1,2,3,4,5,6],"data":{"1":0,"2":0,"3":1000,"4":1000,
    "5":65535,"6":65535}},"res":0}

    send:{"cmd":3,"pv":0,"sn":"1636463662455","msg":{"attr":[1],"data":{"1":0}}}
    receiver:{"cmd":3,"pv":0,"sn":"1636463662455","msg":{"attr":[1],"data":{"1":0}},"res":0}
    receiver:{"cmd":10,"pv":0,"sn":"1636463664000","res":0,"msg":{"attr":[1,2,3,4,5,6],"data":{"1":0,"2":0,"3":1000,
    "4":1000,"5":65535,"6":65535}}}
    """
    _ip = str
    _port = 5555
    _connect = None  # socket

    _device_id = 'temp_id'  # str
    # _device_key = str
    _pid = str
    _device_type_code = '01'
    _icon = str
    _device_model_name = 'light'
    _dpid = [3, 5]
    # last sn
    _sn = str

    def __init__(self, ip, timeout=3):
        self._ip = ip
        self.timeout = timeout

    def disconnect(self):
        if self._connect:
            try:
                #self._connect.shutdown(socket.SHUT_RDWR)
                self._connect.close()
            except:
                pass
        self._connect = None

    def __del__(self):
        self.disconnect()

    def _initSocket(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self._ip, self._port))
            self._connect = s

        except:
            _LOGGER.info(f'_initSocketerror,ip={self._ip}')
            self.disconnect()

    @property
    def check(self) -> bool:
        """
        Determine whether the device is filtered
        :return:
        """
        return True

    @property
    def dpid(self):
        return self._dpid

    @property
    def device_model_name(self):
        return self._device_model_name

    @property
    def icon(self):
        return self._icon

    @property
    def device_type_code(self) -> str:
        return self._device_type_code

    @property
    def device_id(self):
        return self._device_id

    def _device_info(self) -> None:
        """
        get info for device model
        :return:
        """
        self._only_send(CMD_INFO, {})
        try:
            try:
                resp = self._connect.recv(1024)
            except:
                self.disconnect()
                self._initSocket()
                return None
            resp_json = json.loads(resp.strip())
        except:
            _LOGGER.info('_device_info.recv.error')
            return None

        if resp_json.get('msg') is None or type(resp_json['msg']) is not dict:
            _LOGGER.info('_device_info.recv.error1')

            return None

        if resp_json['msg'].get('did') is None:
            _LOGGER.info('_device_info.recv.error2')

            return None
        self._device_id = resp_json['msg']['did']

        if resp_json['msg'].get('pid') is None:
            _LOGGER.info('_device_info.recv.error3')
            return None

        self._pid = resp_json['msg']['pid']

        pid_list = get_pid_list()
        for item in pid_list:
            match = False
            for item1 in item['device_model']:
                if item1['device_product_id'] == self._pid:
                    match = True
                    self._icon = item1['icon']
                    self._device_model_name = item1['device_model_name']
                    self._dpid = item1['dpid']
                    break

            if match:
                self._device_type_code = item['device_type_code']
                break

        # _LOGGER.info(pid_list)
        _LOGGER.info(self._device_id)
        _LOGGER.info(self._device_type_code)
        _LOGGER.info(self._pid)
        _LOGGER.info(self._device_model_name)
        _LOGGER.info(self._icon)

    def _get_package(self, cmd: int, payload: dict) -> bytes:
        """
        package message
        :param cmd:int:
        :param payload:
        :return:
        """
        self._sn = get_sn()
        if CMD_SET == cmd:
            message = {
                'pv': 0,
                'cmd': cmd,
                'sn': self._sn,
                'msg': {
                    'attr': [int(item) for item in payload.keys()],
                    'data': payload,
                }
            }
        elif CMD_QUERY == cmd:
            message = {
                'pv': 0,
                'cmd': cmd,
                'sn': self._sn,
                'msg': {
                    'attr': [0],
                }
            }
        elif CMD_INFO == cmd:
            message = {
                'pv': 0,
                'cmd': cmd,
                'sn': self._sn,
                'msg': {}
            }
        else:
            raise Exception('CMD is not valid')

        payload_str = json.dumps(message, separators=(',', ':',))
        _LOGGER.info(f'_package={payload_str}')
        return bytes(payload_str + "\r\n", encoding='utf8')

    def _send_receiver(self, cmd: int, payload: dict) -> Union[dict, Any]:
        """
        send & receiver
        :param cmd:
        :param payload:
        :return:
        """
        try:
            self._connect.send(self._get_package(cmd, payload))
        except:
            try:
                self.disconnect()
                self._initSocket()
                self._connect.send(self._get_package(cmd, payload))
            except:
                pass
        try:
            i = 10
            while i > 0:
                res = self._connect.recv(1024)
                # print(f'res={res},sn={self._sn},{self._sn in str(res)}')
                i -= 1
                # only allow same sn
                if self._sn in str(res):
                    payload = json.loads(res.strip())
                    if payload is None or len(payload) == 0:
                        return None

                    if payload.get('msg') is None or type(payload['msg']) is not dict:
                        return None

                    if payload['msg'].get('data') is None or type(payload['msg']['data']) is not dict:
                        return None

                    return payload['msg']['data']

            return None

        except Exception as e:
            # print(f'e={e}')
            _LOGGER.info(f'_only_send.recv.error:{e}')
            return None

    def _only_send(self, cmd: int, payload: dict) -> None:
        """
        send but not receiver
        :param cmd:
        :param payload:
        :return:
        """
        try:
            self._connect.send(self._get_package(cmd, payload))
        except:
            self._connect.send(self._get_package(cmd, payload))
            try:
                self.disconnect()
                self._initSocket()
                self._connect.send(self._get_package(cmd, payload))
            except:
                self.disconnect()

    def control(self, payload: dict) -> bool:
        """
        control use dpid
        :param payload:
        :return:
        """
        self._only_send(CMD_SET, payload)
        return True

    def query(self) -> dict:
        """
        query device state
        :return:
        """
        return self._send_receiver(CMD_QUERY, {})
