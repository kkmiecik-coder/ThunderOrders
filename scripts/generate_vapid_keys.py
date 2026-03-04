"""
Generate VAPID keys for Web Push notifications.
Run once: python scripts/generate_vapid_keys.py
Add the output to your .env file.
"""

from py_vapid import Vapid

vapid = Vapid()
vapid.generate_keys()

print('Add these to your .env file:\n')
print(f'VAPID_PRIVATE_KEY={vapid.private_pem().decode().strip()}')
print()

import base64
raw_pub = vapid.public_key.public_bytes(
    encoding=__import__('cryptography').hazmat.primitives.serialization.Encoding.X962,
    format=__import__('cryptography').hazmat.primitives.serialization.PublicFormat.UncompressedPoint
)
application_server_key = base64.urlsafe_b64encode(raw_pub).rstrip(b'=').decode()
print(f'VAPID_PUBLIC_KEY={application_server_key}')
print(f'\nVAPID_CLAIMS_EMAIL=mailto:noreply@thunderorders.cloud')
