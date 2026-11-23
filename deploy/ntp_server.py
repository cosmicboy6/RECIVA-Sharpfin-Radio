#!/usr/bin/env python3
"""Minimal NTPv4 server for the Reciva radio (ntp.reciva.com -> local time)."""
import socket
import struct
import time

NTP_EPOCH_OFFSET = 2208988800
LISTEN = ("0.0.0.0", 123)


def ntp_time(t=None):
    if t is None:
        t = time.time()
    sec = int(t) + NTP_EPOCH_OFFSET
    frac = int((t - int(t)) * 2**32)
    return (sec << 32) | frac


def build_response(req, now):
    version = (req[0] >> 3) & 0x07
    poll = req[2] if 4 <= req[2] <= 17 else 6
    li_vn_mode = (0 << 6) | (min(version, 4) << 3) | 4
    originate = req[40:48]
    return struct.pack(
        "!BBBBIIIQQQQ",
        li_vn_mode, 2, poll, 0xEC,
        0, 0, 0x7F7F0100,
        ntp_time(now - 1),
        struct.unpack("!Q", originate)[0] if len(originate) == 8 else 0,
        ntp_time(now),
        ntp_time(now),
    )


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(LISTEN)
    print("ntp server listening on %s:%d" % LISTEN, flush=True)
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if len(data) < 48:
                continue
            sock.sendto(build_response(data, time.time()), addr)
        except Exception as exc:
            print("ntp error: %r" % exc, flush=True)


if __name__ == "__main__":
    main()
