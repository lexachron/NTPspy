import socket
from ntpdatagram import NTPdatagram
from ntpspymessage import NTPspyMessage

class NTPspyClient:
    def __init__(self, remote="127.0.0.1", port=1234, timeout=2.0):
        self.server_addr = (remote, port)
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        print(f"Client socket initialized for {self.server_addr}")

    def send_ntp(self, ntp_msg: NTPdatagram):
        try:
            self.sock.sendto(ntp_msg.to_bytes(), self.server_addr)
            print(f"Sent NTPdatagram to {self.server_addr}")

            data, addr = self.sock.recvfrom(1024)
            response = NTPdatagram.from_bytes(data)
            print(f"Received response from {addr}: {response}")
            return response
        except socket.timeout:
            print("Timeout waiting for response.")
            return None

    def send_ntpspy(self, spy_msg: NTPspyMessage):
        ntp_msg = spy_msg.to_ntp()
        return self.send_ntp(ntp_msg)

    def close(self):
        self.sock.close()
        print("Client socket closed.")

if __name__ == "__main__":
    print("\nclient = NTPspyClient(), client.close()")
