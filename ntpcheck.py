"""
Test script to verify NTPspy responds correctly to ordinary NTP requests
"""
import socket
import struct
import sys
import datetime

NTP_SERVER = sys.argv[1]
NTP_PORT = 123
NTP_PACKET_FORMAT = "!12I"
NTP_DELTA = 2208988800

def get_ntp_time(host):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(5)
    ntp_packet = b'\x1b' + 47 * b'\0'
    
    try:
        client.sendto(ntp_packet, (host, NTP_PORT))
        data, addr = client.recvfrom(1024)
    except socket.timeout:
        print("Request timed out")
        return None
    finally:
        client.close()
    
    if data:
        unpacked_data = struct.unpack(NTP_PACKET_FORMAT, data[0:48])
        timestamp = unpacked_data[10] - NTP_DELTA
        return datetime.datetime.fromtimestamp(timestamp).isoformat(timespec='minutes')
    return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: ntpcheck.py <NTP_SERVER>")
        sys.exit(1)
    
    ntp_time = get_ntp_time(NTP_SERVER)
    if ntp_time:
        print(ntp_time)
    else:
        print("Failed to get NTP time")