#!/usr/bin/env python3
"""DNS proxy: Reciva domains -> patch server, everything else -> upstream."""
import os
import socket
import struct

LISTEN = ("0.0.0.0", 53)
SUFFIX = ".7803986842.com"
RECIVA_SUFFIX = ".reciva.com"


def env_ip(name, default):
    value = os.environ.get(name, default).strip()
    if not value or value.startswith("<"):
        raise SystemExit("dnsproxy: %s ist nicht gesetzt" % name)
    try:
        socket.inet_aton(value)
    except OSError:
        raise SystemExit("dnsproxy: %s ist keine gueltige IP: %r" % (name, value))
    return value


UPSTREAM = (env_ip("UPSTREAM_DNS", "192.168.0.1"), 53)
LOCAL_A = env_ip("PATCHSERVER_IP", "192.168.0.240")


def parse_question(data):
    if len(data) < 12:
        raise ValueError("short dns packet")
    qd = struct.unpack("!H", data[4:6])[0]
    if qd < 1:
        raise ValueError("no question")
    off = 12
    labels = []
    while True:
        if off >= len(data):
            raise ValueError("truncated name")
        n = data[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0:
            raise ValueError("compressed question")
        off += 1
        if off + n > len(data):
            raise ValueError("truncated label")
        labels.append(data[off:off + n].decode("ascii", "ignore"))
        off += n
    if off + 4 > len(data):
        raise ValueError("truncated qtype")
    qtype, qclass = struct.unpack("!HH", data[off:off + 4])
    return ".".join(labels).lower(), qtype, qclass, off + 4


def response(data, off, qtype, local):
    tid = data[:2]
    flags = b"\x81\x80"
    question = data[12:off]
    if qtype == 1 and local:
        answer = (b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4)
                  + socket.inet_aton(LOCAL_A))
        header = tid + flags + struct.pack("!HHHH", 1, 1, 0, 0)
        return header + question + answer
    header = tid + flags + struct.pack("!HHHH", 1, 0, 0, 0)
    return header + question


def is_reciva_name(name):
    return (name == SUFFIX[1:] or name.endswith(SUFFIX)
            or name == RECIVA_SUFFIX[1:] or name.endswith(RECIVA_SUFFIX))


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(LISTEN)
    print("dnsproxy: listening on %s:%d, upstream %s:%d, local %s"
          % (LISTEN[0], LISTEN[1], UPSTREAM[0], UPSTREAM[1], LOCAL_A), flush=True)

    while True:
        try:
            data, addr = s.recvfrom(2048)
        except Exception as exc:
            print("dnsproxy: recv error %r" % exc, flush=True)
            continue

        name = "?"
        try:
            name, qtype, _qclass, off = parse_question(data)
            if is_reciva_name(name):
                s.sendto(response(data, off, qtype, True), addr)
                print("dnsproxy: %s type %d -> %s" % (name, qtype, LOCAL_A), flush=True)
                continue
        except Exception as exc:
            print("dnsproxy: parse error %r" % exc, flush=True)

        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.settimeout(3.0)
            u.sendto(data, UPSTREAM)
            reply, _ = u.recvfrom(4096)
            u.close()
            s.sendto(reply, addr)
            print("dnsproxy: %s -> upstream" % name, flush=True)
        except Exception as exc:
            print("dnsproxy: upstream error for %s: %r" % (name, exc), flush=True)
            try:
                fail = data[:2] + b"\x81\x82" + struct.pack("!HHHH", 1, 0, 0, 0) + data[12:]
                s.sendto(fail, addr)
            except Exception:
                pass


if __name__ == "__main__":
    main()
