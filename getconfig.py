import sys
from io import StringIO
from custom_components.cozylife.tcp_client import tcp_client
from ipaddress import ip_address

def ips(start, end):
    '''Return IPs in IPv4 range, inclusive. from stackoverflow'''
    start_int = int(ip_address(start).packed.hex(), 16)
    end_int = int(ip_address(end).packed.hex(), 16)
    return [ip_address(ip).exploded for ip in range(start_int, end_int + 1)]

start = '192.168.1.193'
end = '192.168.1.254'

if len(sys.argv) == 2:
    end = sys.argv[1]
    start = sys.argv[1]

if len(sys.argv) > 2:
    end = sys.argv[2]
    start = sys.argv[1]

probelist = ips(start, end)
print("IP scan from {0}, end with {1}".format(probelist[0], probelist[-1]))

lights_buf = StringIO()
switches_buf = StringIO()

for ip in probelist:
    a = tcp_client(ip, timeout=0.1)

    a._initSocket()

    if a._connect:
        device_info = a._device_info()
        device_info_str = f'  - ip: {ip}\n'
        device_info_str += f'    did: {a._device_id}\n'
        device_info_str += f'    pid: {a._pid}\n'
        device_info_str += f'    dmn: {a._device_model_name}\n'
        device_info_str += f'    dpid: {a._dpid}\n'
      #  device_info_str += f'    device_type: {a._device_type_code}\n'

        if a._device_type_code == '01':
            lights_buf.write(device_info_str)
        elif a._device_type_code == '00':
            switches_buf.write(device_info_str)

print(f'lights:')
print(f'- platform: cozylife')
print(f'  lights:')
print(lights_buf.getvalue())

print(f'switch:')
print(f'- platform: cozylife')
print(f'  switches:')
print(switches_buf.getvalue())
