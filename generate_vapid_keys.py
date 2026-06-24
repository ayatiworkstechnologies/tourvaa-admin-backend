"""Run once: python generate_vapid_keys.py
Generates VAPID keys, saves vapid_private.pem, and prints .env values.
"""
import base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

pub_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)
priv_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
)

pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()

pem_file = Path(__file__).parent / "vapid_private.pem"
pem_file.write_bytes(priv_pem)

print(f"Saved private key to: {pem_file}")
print()
print("Add to backend/.env:")
print(f"VAPID_PUBLIC_KEY={pub_b64}")
print("VAPID_PRIVATE_KEY_FILE=vapid_private.pem")
print()
print("Add to frontend .env files:")
print(f"NEXT_PUBLIC_VAPID_PUBLIC_KEY={pub_b64}")
