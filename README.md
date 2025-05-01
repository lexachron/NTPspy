# NTPspy - data tunneling over NTP

Transfer files disguised in simulated NTP traffic.  

## System Requirements

- Python 3.7 or later

## Usage

`python ntpspy.py -h` for usage help (options, flags, and modes)

### Server Mode

`python ntpspy.py [-m magic] [-s storage_path]` will run the program in server mode and store the transferred files with in the provided storage path

`python ntpspy.py [-m magic] [-s storage_path] [-o]` allows overwriting existing files, else duplicate files will be automatically renamed

`python ntpspy.py [-m magic] [-s storage_path] [-p Port]` will run the program in server mode and with a selected port, default 123

### Client Mode

`python ntpspy.py [-q] [-m magic] remote` queries the server to check the presence of NTPspy and protocol version using the specified magic number. The program will exit after the query is complete.

`python ntpspy.py [-p Port] [-m magic] remote [file ...]` will run a client instance of the program transferring the designated file(s) to the remote host

- port number can also be set using the *host:port* convention
- without filename, will read from stdin

`python ntpspy.py [-t Time_interval] remote [file ...]` sends the specified file(s) to the remote host, but with minimum interval (in seconds) between datagrams

### Arguments Across both Server and Client

`-m magic_number` this value is set to differentiate the sent messages from typical NTP traffic

	- the higher the value, the less chance of a normal NTP datagram being processed as a NTPspy message

`-v` verbose mode, increase level of log detail

## Known limits/issues

- Multiple instances of the server running and saving to the same directory will overwrite each other's temporary buffer files.

