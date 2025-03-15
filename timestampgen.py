import time
import random

from abc import ABC, abstractmethod
from ntpdatagram import NTPdatagram

UNIX_TO_NTP = 2208988800

class TimestampGenerator(ABC):
    @abstractmethod
    def apply_timestamps(self, request: NTPdatagram, reply: NTPdatagram) -> None:
        """modify reply datagram with appropriate timestamps"""
        pass

class OperationalTimestampGenerator(TimestampGenerator):
    def apply_timestamps(self, request: NTPdatagram, reply: NTPdatagram) -> None:
        """real NTP timestamps based on system clock"""
        reply.org_whole = request.xmt_whole
        reply.org_frac = request.xmt_frac
        current_time = time.time() + UNIX_TO_NTP
        reply.rec_whole = int(current_time)
        reply.rec_frac = int(((current_time % 1) + random.uniform(0.0001, 0.005)) * (2**32))
        reply.xmt_whole = reply.rec_whole
        if reply.xmt_whole == reply.rec_whole and request.xmt_frac < reply.rec_frac:
            reply.xmt_whole += 1  # ensure xmt_whole.xmt_frac is always >= rec_whole.rec_frac
        reply.xmt_frac = request.xmt_frac  # preserve ntpspy payload
        reply.reftime_whole = reply.rec_whole - random.randint(5, 10)
        reply.reftime_frac = request.reftime_frac  # Preserve sequence number

class MockTimestampGenerator(TimestampGenerator):
    def apply_timestamps(self, request: NTPdatagram, reply: NTPdatagram) -> None:
        """deterministic offset for testing"""
        reply.org_whole = request.xmt_whole
        reply.org_frac = request.xmt_frac
        reply.rec_whole = request.xmt_whole + 1
        reply.rec_frac = request.xmt_frac
        reply.xmt_whole = request.xmt_whole + 2
        reply.xmt_frac = request.xmt_frac
        reply.reftime_whole = reply.rec_whole - 5
        reply.reftime_frac = request.reftime_frac