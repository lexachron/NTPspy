
# NTPSpy

This project is designed to act as a data tunnel through typical NTP traffic. This is done via inserting said data into the datagaram of NTP. The user can select the directory and machine to send the transferred data to along with a variety of other modes to customize the experience.

  
  

## System Requirements

-python 3.7 or later installed

-Tested and verified functionality on linux and windows OS

  

## Usage

-**python3 ntpspy.py -h** for help options (different inputs, flags, and basic information)

### Server Mode

-**python3 ntpspy.py -s [storage path]** will run the program in server mode and store the transferred files with in the provided storage path

-**python3 ntpspy.py -s [storage path] -o** will run the program in server mode and allow for files to be overridden with in the storage directory should the transferred files have the same name

-**python3 ntpspy.py -s [storage path] -p [Port Number]** will run the program in server mode and with a selected port

### Client Mode

-**python3 ntpspy.py [IP Address] -p [Port Number] [file to transfer]** will run a client instance of the program transferring the designated file to the IP address and port number specified in the command line

	-as a note the port number can be set additionally by using the format *[IP address]:[Port number]*

	-the default port number is set to 123 as that is standard for NTP traffic. This port can be admin only on some operating systems.

-**python3 ntpspy.py [IP Address] -q** will run the program in client mode and query the server instance at the specified ip address. The program will exit after the query is complete

-**python3 ntpspy.py [IP Address] [file to transfer] -t [Time interval]** will run the program in client mode, sending the specified file to the designated IP address, but will send data on a minimum interval set in the command line. This interval is set in seconds

### Arguments Across both Server and Client

**-m [Magic Number]** this value is set to differentiate the sent messages from typical NTP traffic

	-while this number can be in the range of 0x1 to 0xFFFFFFFF it is recommended to select a higher number as this will decrease the chances of colliding with other NTP traffic

**-v** will run the program in verbose mode allowing the user to see the output of the info and debug logs

**-vv** will run the program in verbose mode allowing the user to see the output of info, debug, and warning logs 

**-vvv** will run the program in verbose mode allowing the user to see the most output of info, debug, warning, and error logs 

  
  

## Notes

-Multiple instances of the program running and outputting to the same directory can cause file deletion as on start up the server will clean any in progress or incomplete data transfers. It is not recommended to have multiple instances pointing to the same directory.

