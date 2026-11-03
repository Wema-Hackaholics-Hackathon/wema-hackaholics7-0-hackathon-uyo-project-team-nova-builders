"""python -m foid keygen  — make a key pair for private_key_jwt."""

import json
import sys

from .keypair import generate_keypair

if __name__ == "__main__":
    if sys.argv[1:] != ["keygen"]:
        print("usage: python -m foid keygen", file=sys.stderr)
        sys.exit(2)
    pem, jwk = generate_keypair()
    with open("foid_private_key.pem", "x") as f:
        f.write(pem)
    print("Private key written to foid_private_key.pem — keep it on your server, never commit it.\n")
    print("Public key (paste into FOID Console → Sign-in apps → Edit → Key pair):\n")
    print(json.dumps(jwk, indent=2))
