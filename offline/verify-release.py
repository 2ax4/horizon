#!/usr/bin/env python3
"""Verify a Horizon offline release: SHA256SUMS + its Ed25519 signature (SHA256SUMS.sig).

The launcher already verifies every release it downloads before it applies an
update; this script is for checking a file you downloaded by hand.

Usage:
    python3 verify-release.py <tag> [folder]

    <tag>     the release tag, e.g. launcher@0.2.37-offline
    [folder]  where SHA256SUMS, SHA256SUMS.sig and the downloaded assets are
              (defaults to the current folder)

Needs only Python 3.8+, no third-party packages. Exit code 0 = everything
verified; 1 = verification failed; 2 = missing files (checksums of the present
ones may still have passed, check the output).
"""

import base64
import hashlib
import os
import sys

# The fork's Ed25519 public key. It is added to
# crates/horizon-release-sign/release-keys.txt by offline/patches/0003.
FORK_KEY = "DfcWSiaD14ScBMxU0btrJMPDSspw+flKz43XoXHSsh4="

# --------------------------------------------------------------------------
# Ed25519 verification, transcribed from the RFC 8032 reference sketch
# (public domain). A built-in self-test (see _self_test) guards the math.
# --------------------------------------------------------------------------

_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493  # group order
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _inv(x):
    return pow(x, _P - 2, _P)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * _inv(5) % _P
_B = (_xrecover(_BY), _BY)
_IDENT = (0, 1)


def _on_curve(pt):
    x, y = pt
    return (-x * x + y * y - 1 - _D * x * x * y * y) % _P == 0


def _add(pt, qt):
    x1, y1 = pt
    x2, y2 = qt
    dxy = _D * x1 * x2 * y1 * y2 % _P
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + dxy) % _P
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - dxy) % _P
    return (x3, y3)


def _neg(pt):
    return ((_P - pt[0]) % _P, pt[1])


def _mul(pt, e):
    e %= _Q
    q = _IDENT
    while e > 0:
        if e & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        e >>= 1
    return q


def _decode(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if (x & 1) != ((s[31] >> 7) & 1):
        x = (_P - x) % _P
    pt = (x, y)
    if not _on_curve(pt):
        raise ValueError("point not on curve")
    return pt


def _ed25519_verify(pub32, msg, sig64):
    if len(pub32) != 32 or len(sig64) != 64:
        return False
    try:
        a = _decode(pub32)
        r = _decode(sig64[:32])
    except (ValueError, IndexError):
        return False
    s = int.from_bytes(sig64[32:], "little")
    if s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(sig64[:32] + pub32 + msg).digest(), "little")
    left = _mul(_B, s)
    right = _add(r, _mul(a, h))
    return left == right


def _self_test():
    """RFC 8032 test 1 + a sign/verify round trip. Aborts loudly if broken."""
    pub = bytes.fromhex(
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    )
    sig = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    if not _ed25519_verify(pub, b"", sig):
        print("FATAL: Ed25519 self-test failed (RFC 8032 vector 1).")
        print("The script is broken or was tampered with; do not trust it.")
        sys.exit(3)

    # round trip: sign with the reference scheme, verify with this file's math
    a = 0x5BF1E21C0B0F3B1D3E2F4A5B6C7D8E9F0A1B2C3D4E5F60718293A4B5C6D7E8F % _Q
    apt = _mul(_B, a)

    def enc(pt):
        x, y = pt
        b = bytearray(y.to_bytes(32, "little"))
        b[31] |= (x & 1) << 7
        return bytes(b)

    def sign(msg):
        r = int.from_bytes(hashlib.sha512(b"selftest" + msg).digest(), "little") % _Q
        r_pt = _mul(_B, r)
        h = int.from_bytes(
            hashlib.sha512(enc(r_pt) + enc(apt) + msg).digest(), "little"
        )
        s = (r + h * a) % _Q
        return enc(r_pt) + s.to_bytes(32, "little")

    msg = b"horizon offline self-test"
    if not _ed25519_verify(enc(apt), msg, sign(msg)):
        print("FATAL: Ed25519 self-test failed (sign/verify round trip).")
        print("The script is broken or was tampered with; do not trust it.")
        sys.exit(3)


# --------------------------------------------------------------------------
# Release checks
# --------------------------------------------------------------------------


def main() -> int:
    _self_test()

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 2
    tag = sys.argv[1]
    folder = sys.argv[2] if len(sys.argv) > 2 else "."
    sums_path = os.path.join(folder, "SHA256SUMS")
    sig_path = os.path.join(folder, "SHA256SUMS.sig")

    for path in (sums_path, sig_path):
        if not os.path.exists(path):
            print(f"FAIL: {path} not found (download it from the release)")
            return 1

    sums = open(sums_path, "rb").read()
    message = f"horizon release {tag}\n".encode() + sums

    pub = base64.b64decode(FORK_KEY)
    ok_sig = False
    lines = [ln.strip() for ln in open(sig_path, "rb").read().split(b"\n") if ln.strip()]
    for i, line in enumerate(lines, 1):
        try:
            sig = base64.b64decode(line, validate=True)
        except Exception:
            print(f"note: signature line {i} is not valid base64, skipping")
            continue
        if _ed25519_verify(pub, message, sig):
            ok_sig = True
            break
    if ok_sig:
        print(f"OK  signature: SHA256SUMS.sig is valid for {tag} (fork release key)")
    else:
        print(f"FAIL signature: no signature in SHA256SUMS.sig verifies for {tag}")
        return 1

    missing = 0
    checked = 0
    failed = 0
    for raw in sums.decode("utf-8", "replace").splitlines():
        raw = raw.rstrip("\r")
        if not raw or "  " not in raw:
            continue
        expected, name = raw.split("  ", 1)
        asset = os.path.join(folder, name)
        if not os.path.exists(asset):
            missing += 1
            continue
        digest = hashlib.sha256(open(asset, "rb").read()).hexdigest()
        if digest == expected:
            print(f"OK  sha256:   {name}")
            checked += 1
        else:
            print(f"FAIL sha256:  {name} (expected {expected}, got {digest})")
            failed += 1

    if checked == 0 and missing > 0:
        print(f"\nNo assets found in this folder: {missing} file(s) listed in SHA256SUMS are missing.")
        print("Download the assets you want, put them next to SHA256SUMS and run this again.")
        return 2
    if failed:
        return 1
    extra = f", {missing} listed file(s) not present" if missing else ""
    print(f"\nAll good: {checked} asset(s) verified{extra}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
