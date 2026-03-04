"""
Generate VAPID keys for Web Push notifications.
Run once: python scripts/generate_vapid_keys.py
Add the output to your .env file.
"""

from py_vapid import Vapid
import base64
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, NoEncryption
from cryptography.hazmat.primitives.asymmetric.ec import ECDH

vapid = Vapid()
vapid.generate_keys()

# Public key as base64url (applicationServerKey format)
raw_pub = vapid.public_key.public_bytes(
    encoding=Encoding.X962,
    format=PublicFormat.UncompressedPoint
)
public_key_b64 = base64.urlsafe_b64encode(raw_pub).rstrip(b'=').decode()

# Private key as base64url (raw 32-byte scalar)
raw_priv = vapid.private_key.private_numbers().private_value.to_bytes(32, 'big')
private_key_b64 = base64.urlsafe_b64encode(raw_priv).rstrip(b'=').decode()

print('Add these to your .env file:\n')
print(f'VAPID_PUBLIC_KEY={public_key_b64}')
print(f'VAPID_PRIVATE_KEY={private_key_b64}')
print(f'VAPID_CLAIMS_EMAIL=mailto:noreply@thunderorders.cloud')
