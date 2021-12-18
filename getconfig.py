# -*- coding: utf-8 -*-
import sys
from io import StringIO
import time
from custom_components.cozylife.tcp_client import tcp_client

from ipaddress import ip_address


def ips(start, end):
    '''Return IPs in IPv4 range, inclusive. from stackoverflow'''
    start_int = int(ip_address(start).packed.hex(), 16)
    end_int = int(ip_address(end).packed.hex(), 16)
    return [ip_address(ip).exploded for ip in range(start_int, end_int)]


print(f'light:')
print(f'- platform: cozylife')
print(f'  lights:')
buf = StringIO()

#for i in range(214, 192, -1):
start = '192.168.1.193'
end = '192.168.1.254'
if len(sys.argv) > 2:
  end = sys.argv[2]
  start = sys.argv[1]
for ip in ips(start, end):
  a = tcp_client(ip, timeout=0.1)
  a._initSocket()
  if a._connect:
    a._device_info()
    if a._device_type_code == '01':
      print(f'  - ip: {ip}')
      print(f'    did: {a._device_id}')
      print(f'    pid: {a._pid}')
      print(f'    dmn: {a._device_model_name}')
      print(f'    dpid: {a._dpid}')
    elif a._device_type_code == '00':
      buf.write(f'  - ip: {ip}')
      buf.write(f'    did: {a._device_id}')
      buf.write(f'    pid: {a._pid}')
      buf.write(f'    dmn: {a._device_model_name}')
      buf.write(f'    dpid: {a._dpid}')
print(f'switch:')
print(f'- platform: cozylife')
print(f'  switchs:')
print(buf.getvalue())
