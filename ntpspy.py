from ntpspyserver import NTPspyServer
from ntpspyclient import NTPspyClient
import argparse
import asyncio

DEFAULT_NTP_PORT = 1234
DEFAULT_MAGIC_NUMBER = "0xDEADBEEF"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NTPspy - data tunneling over NTP")
    parser.add_argument("-s", type=str, help="Server mode <storage path>")
    parser.add_argument("-p", type=int, default=DEFAULT_NTP_PORT, help="Port number")
    parser.add_argument("-m", type=lambda x: int(x,0), default=DEFAULT_MAGIC_NUMBER, help="Magic number (hex 1-FFFFFFFF)")
    parser.add_argument("-v", action="store_true", help="Verbose mode")
    parser.add_argument("-q", action="store_true", help="Query server for NTPspy protocol version")
    #parser.add_argument("-d", type=str, help="Transfer session ID (hex 1-FFFFFFFF)")
    parser.add_argument("-t", type=int, help="Minimum interval (sec) (client only)")
    parser.add_argument("remote", type=str, nargs='?', help="server IP (client only)")
    parser.add_argument("filename", type=str, nargs='?', help="Filename to transfer (client only)")
    args = parser.parse_args()

    # server mode
    if args.s:
        server = NTPspyServer(path = args.s, port = args.p, verbose = args.v, magic_number = args.m)
        asyncio.run(server.start())

    # client mode

    ## probe only
    elif args.remote and args.q:
        client = NTPspyClient(remote = args.remote, port = args.p, verbose = args.v, magic_number = args.m)
        client.probe()

    ## transfer file
    elif args.remote and args.filename:
        client = NTPspyClient(remote = args.remote, port = args.p, verbose = args.v, magic_number = args.m)
        client.transfer_file(filepath = args.filename)

    # print usage
    else:
        parser.print_help()
        exit(1)