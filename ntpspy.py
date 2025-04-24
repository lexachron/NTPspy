from ntpspyserver import NTPspyServer
from ntpspyclient import NTPspyClient
from ntpspymessage import NTPspyStatus
from pathlib import Path
import argparse
import asyncio
import logging
import sys

DEFAULT_NTP_PORT = 123
DEFAULT_MAGIC_NUMBER = 0xdeadbeef
DEFAULT_PATH = "."

try:
    __version__ = Path(__file__).parent.joinpath("VERSION").read_text().strip()
except FileNotFoundError:
    __version__ = "version ???" # VERSION file missing or unreadable

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
    parser.add_argument("-s", "--server", type=str, nargs='?', const=DEFAULT_PATH, help="Server mode [storage path] (default CWD)")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_NTP_PORT, help="Port number")
    parser.add_argument("-m", "--magic", type=lambda x: int(x,0), default=DEFAULT_MAGIC_NUMBER, help="Magic number (hex 1-FFFFFFFF)")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Verbose mode (repeatable)")
    parser.add_argument("-o", "--overwrite", action="store_true", help="Allow overwrite existing files (server only)")
    parser.add_argument("-q", "--query", action="store_true", help="Query server version and exit (client only)")
    parser.add_argument("-t", "--time", type=int, default=0, help="Minimum interval (sec) (client only)")
    parser.add_argument("remote", type=str, nargs='?', help="Remote host (client only)")
    parser.add_argument("files", type=str, nargs='*', help="Filename to transfer (client only)")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}", help="Show version and exit")
    args = parser.parse_args()

    logger.setLevel(logging.DEBUG if args.verbose > 0 else logging.INFO)

    hostname = None
    port = args.port
    if args.remote:
        # tentative support for RFC 3986 style host:port authority
        hostname, _, port_string = args.remote.partition(":")
        try:
            port = int(port_string) if port_string else args.port 
        except ValueError:
            logger.error(f"Invalid port: '{port_string}'")
            exit(1)
        hostname = hostname or None
    else:
        hostname = None
        port = args.port
    if not 1 <= port <= 65535:
        logger.error("Invalid port number")
        exit(1)

    # server mode
    if args.server:
        if args.remote or args.files:
            logger.error("Server mode does not accept remote host or filenames")
            parser.print_help()
            exit(1)
        logger.info(f"NTPspy {__version__} starting in server mode.")
        if args.server == DEFAULT_PATH:
            logger.warning(f"Storing files in default path: '{DEFAULT_PATH}'")
        server = NTPspyServer(
            path = args.server, 
            port = port, 
            verbose = args.verbose, 
            magic_number = args.magic, 
            allow_overwrite = args.overwrite,
        )
        asyncio.run(server.start())

    # client mode
    elif hostname:
        client = NTPspyClient(
            remote = hostname, 
            port = port, 
            verbose = args.verbose, 
            magic_number = args.magic, 
            interval = args.time
        )

        ## probe only
        if args.query:
            probe = client.probe()
            if not probe:
                logger.error("Probe failed. Server unreachable, not NTPspy, or wrong magic number.")
                exit(1)
            else:
                logger.debug(f"{probe}")
                logger.info(f"Server version: {probe.version}, Status: {NTPspyStatus(probe.status).name}")
                exit(0)
            exit(0)

        ## process files
        if args.files:
            for filename in args.files:
                if filename != "-":
                    client.transfer_file(filename)
                else:
                    print("Reading input from terminal, send EOF (Ctrl+d or Ctrl+z on Win) to finish.")
                    data = sys.stdin.buffer.read()
                    if not data:
                        logger.warning("No data to send. Skipping.")
                        continue
                    logger.debug(f"Read {len(data)} bytes of unnamed data")
                    client.transfer_session(data, None)
        
        ## read piped input
        elif not sys.stdin.isatty():
            data = sys.stdin.buffer.read()
            if not data:
                logger.error("Empty pipe")
                exit(1)
            logger.debug(f"Read {len(data)} bytes of unnamed data")
            client.transfer_session(data, None)

        ## no filenames or pipe input
        else:
            logger.error("No filenames or piped data detected.")
            parser.print_help()
            exit(1)

    # no remote and not -s
    else:
        logger.error("Remote host required in client mode.")
        parser.print_help()
        exit(1)