from ntpspyserver import NTPspyServer
from ntpspyclient import NTPspyClient
import argparse
import asyncio
import logging
import sys

DEFAULT_NTP_PORT = 123
DEFAULT_MAGIC_NUMBER = 0xdeadbeef
DEFAULT_PATH = "."

formatter = logging.Formatter(
    fmt='%(asctime)s - %(levelname)s - %(name)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logconsole = logging.StreamHandler()
logconsole.setLevel(logging.DEBUG)
logconsole.setFormatter(formatter)
logger = logging.getLogger("NTPspy")
logger.addHandler(logconsole)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NTPspy - data tunneling over NTP")
    parser.add_argument("-s", type=str, nargs='?', const=DEFAULT_PATH, help="Server mode [storage path] (default CWD)")
    parser.add_argument("-p", type=int, default=DEFAULT_NTP_PORT, help="Port number")
    parser.add_argument("-m", type=lambda x: int(x,0), default=DEFAULT_MAGIC_NUMBER, help="Magic number (hex 1-FFFFFFFF)")
    parser.add_argument("-v", action="count", default=0, help="Verbose mode (repeatable)")
    parser.add_argument("-o", action="store_true", help="Allow overwrite existing files (server only)")
    parser.add_argument("-q", action="store_true", help="Query server version and exit (client only)")
    parser.add_argument("-t", type=int, default=0, help="Minimum interval (sec) (client only)")
    parser.add_argument("remote", type=str, nargs='?', help="Remote host (client only)")
    parser.add_argument("filename", type=str, nargs='?', help="Filename to transfer (client only)")
    args = parser.parse_args()

    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    logger.setLevel(levels[min(args.v, len(levels)-1)])

    hostname = None
    port = args.p
    if args.remote:
        # tentative support for RFC 3986 style host:port authority
        hostname, _, port_string = args.remote.partition(":")
        try:
            port = int(port_string) if port_string else args.p 
        except ValueError:
            logger.error("Invalid port")
            exit(1)
        hostname = hostname or None
    else:
        hostname = None
        port = args.p
    if not 1 <= port <= 65535:
        logger.error("Invalid port number")
        exit(1)

    # server mode
    if args.s:
        logger.debug("Starting NTPspy in server mode.")
        server = NTPspyServer(
            path = args.s, 
            port = args.p, 
            verbose = args.v, 
            magic_number = args.m, 
            allow_overwrite = args.o
        )
        asyncio.run(server.start())

    # client mode
    elif hostname:
        client = NTPspyClient(
            remote = hostname, 
            port = port, 
            verbose = args.v, 
            magic_number = args.m, 
            interval = args.t
        )

        ## probe only
        if args.q:
            client.probe()
        ## transfer named file
        elif args.filename and args.filename != "-":
            client.transfer_file(filepath = args.filename)
        ## transfer anonymous hunk of data
        else: 
            data = sys.stdin.buffer.read()
            if not data:
                logger.error("No data to send")
                exit(1)
            logger.debug(f"Read {len(data)} bytes of unnamed data")
            client.transfer_data(data, None)

    # usage
    else:
        parser.print_help()
        exit(1)