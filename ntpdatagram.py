import struct
from enum import IntEnum

class NTPmode(IntEnum):
    RESERVE = 0
    ACTIVE = 1
    PASSIVE = 2
    CLIENT = 3
    SERVER = 4
    BROADCAST = 5
    CONTROL = 6

class NTPdatagram:
    _FORMAT = "!B B b b I I I I I I I I I I I"
    _SIZE = struct.calcsize(_FORMAT)
    _RANGES = {
        'leap': (0, 3), # 2 bits
        'version': (0, 7), # 3 bits, always 3
#        'mode': (0, 7), # 3 bits, 3: client, 4: server # now handled by enum
        'stratum': (0, 255), # 8 bits, unsigned. valid range: 1-15
        'poll': (-128, 127), # 8 bits, signed. log(poll) seconds
        'precision': (-128, 127), # 8 bits, signed. log(precision) seconds
        'rootdelay': (0, 0xFFFFFFFF), # 32 bits, unsigned
        'rootdispersion': (0, 0xFFFFFFFF), # 32 bit
        'refid': (0, 0xFFFFFFFF), # 32 bit string or IP address
        'reftime_whole': (0, 0xFFFFFFFF), # 32 bit half of 64-bit timestamp, whole number of seconds since epoch
        'reftime_frac': (0, 0xFFFFFFFF), # 32 bit, fractional seconds
        'org_whole': (0, 0xFFFFFFFF),
        'org_frac': (0, 0xFFFFFFFF),
        'rec_whole': (0, 0xFFFFFFFF),
        'rec_frac': (0, 0xFFFFFFFF),
        'xmt_whole': (0, 0xFFFFFFFF),
        'xmt_frac': (0, 0xFFFFFFFF),
    }

    def __init__(
        self,
        leap=0,
        version=3,
        mode=NTPmode.CLIENT,
        stratum=0,
        poll=0,
        precision=0,
        rootdelay=0,
        rootdispersion=0,
        refid=0,
        reftime_whole=0,
        reftime_frac=0,
        org_whole=0,
        org_frac=0,
        rec_whole=0,
        rec_frac=0,
        xmt_whole=0,
        xmt_frac=0,
    ):
        # range check
        args = locals()
        args.pop('self')
        for field, (min_val, max_val) in self._RANGES.items():
            value = args[field]
            if not (min_val <= value <= max_val):
                raise ValueError(f"{field}: {value} outside valid range ({min_val}-{max_val})")

        for field, value in args.items():
            setattr(self, field, value)

    def to_bytes(self):
        li_vn_mode = (self.leap << 6) | (self.version << 3) | self.mode.value
        return struct.pack(
            self._FORMAT,
            li_vn_mode,
            self.stratum,
            self.poll,
            self.precision,
            self.rootdelay,
            self.rootdispersion,
            self.refid,
            self.reftime_whole,
            self.reftime_frac,
            self.org_whole,
            self.org_frac,
            self.rec_whole,
            self.rec_frac,
            self.xmt_whole,
            self.xmt_frac,
        )

    @classmethod
    def from_bytes(cls, data):
        if len(data) != cls._SIZE:
            raise ValueError(f"Invalid datagram size. Expected: {cls._SIZE}, got: {len(data)}")
        unpacked = struct.unpack(cls._FORMAT, data)
        li_vn_mode = unpacked[0]
        return cls(
            leap=(li_vn_mode >> 6) & 0b11,
            version=(li_vn_mode >> 3) & 0b111,
            mode=NTPmode(li_vn_mode & 0b111),
            stratum=unpacked[1],
            poll=unpacked[2],
            precision=unpacked[3],
            rootdelay=unpacked[4],
            rootdispersion=unpacked[5],
            refid=unpacked[6],
            reftime_whole=unpacked[7],
            reftime_frac=unpacked[8],
            org_whole=unpacked[9],
            org_frac=unpacked[10],
            rec_whole=unpacked[11],
            rec_frac=unpacked[12],
            xmt_whole=unpacked[13],
            xmt_frac=unpacked[14],
        )

    def is_ntpspy(self, magic):
        return self.rootdelay == magic
    
    def __eq__(self, other):
        if not isinstance(other, NTPdatagram):
            return False
        return vars(self) == vars(other)