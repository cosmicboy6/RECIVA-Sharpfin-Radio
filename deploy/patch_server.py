#!/usr/bin/env python3
"""Patch the Reciva server binary so stations_only never returns >30 details.

Known binaries (verified on the DNT IPdio patchserver):
  original  SHA256 94ae9c257cbcca04e7739e0cd216271a61c670bdd04673e7e2c1e465b2a23a41
  patched   SHA256 2d899b010d4f5544a62183fe401a34e7970b189a4ddaaf99d6808b63f31689d0

The patch replaces the count handling at file offset 0x1E1836 (vaddr 0x5E16E2):
  cmp dword [rsp],0 / jg ... / test r12b,r12b / ... / cmp rax,rdx
  -> mov dword [rsp+4],0x1e ; jmp 0x5E1711 ; NOPs
"""
import argparse
import hashlib
import os
import shutil
import stat
import sys

ORIGINAL_SHA = "94ae9c257cbcca04e7739e0cd216271a61c670bdd04673e7e2c1e465b2a23a41"
PATCHED_SHA = "2d899b010d4f5544a62183fe401a34e7970b189a4ddaaf99d6808b63f31689d0"
OFF = 0x1E1836
OLD = bytes.fromhex(
    "833c24007f294584e40f84de0000004c89efe8d3650100"
    "4889c7e84b79010021c048635424044839d00f8ebe000000")
NEW = bytes.fromhex("c74424041e000000eb25" + "90" * 37)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    with open(path, "rb") as f:
        return sha_bytes(f.read())


def die(msg):
    print("patch_server: FEHLER: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def patch_in_place(path):
    digest = sha_file(path)
    if digest == PATCHED_SHA:
        print("patch_server: bereits gepatcht (%s)" % digest[:12])
        return False
    if digest != ORIGINAL_SHA:
        die("unbekannte Binary-Version: %s" % digest)

    data = bytearray(open(path, "rb").read())
    if len(OLD) != len(NEW) or len(OLD) != 47:
        die("interne Patch-Laenge ungueltig")
    if data[OFF:OFF + len(OLD)] != OLD:
        die("Patch-Offset %s enthaelt nicht die erwarteten Bytes" % hex(OFF))

    backup = path + ".bak-noClamp"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print("patch_server: Backup -> %s" % backup)

    data[OFF:OFF + len(OLD)] = NEW
    if sha_bytes(data) != PATCHED_SHA:
        die("Patch-Ergebnis hat unerwarteten SHA256")

    tmp = path + ".patched.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
    os.replace(tmp, path)
    print("patch_server: gepatcht -> %s" % PATCHED_SHA)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default="RecivaServer/server",
                    help="Pfad zur server-Binary (Default: RecivaServer/server)")
    args = ap.parse_args()
    if not os.path.isfile(args.path):
        die("Datei nicht gefunden: %s" % args.path)
    patch_in_place(args.path)


if __name__ == "__main__":
    main()
