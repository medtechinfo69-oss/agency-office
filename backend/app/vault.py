"""Authenticated encryption at rest. The encryption key never leaves the server.
Back up CREDENTIAL_ENCRYPTION_KEY (or SESSION_SECRET) with the database. Changing
it without re-encrypting existing records makes those credentials unreadable.
"""
import base64
import hashlib
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

PREFIX = 'enc:v1:'


def sensitive(key):
    return key.startswith('token_') or key in {'api_token', 'image_token', 'totp_secret'} or key.startswith('totp_')


def cipher():
    secret = os.getenv('CREDENTIAL_ENCRYPTION_KEY') or os.getenv('SESSION_SECRET')
    if not secret:
        if os.getenv('VERCEL') == '1' or os.getenv('APP_ENV') == 'production':
            raise RuntimeError('Server credential encryption requires a stable secret.')
        from .config import settings
        path = settings.data_dir / '.credential-key'
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as f: f.write(base64.urlsafe_b64encode(os.urandom(32)).decode())
        except FileExistsError: pass
        secret = path.read_text()
    key = hashlib.sha256(('agency-office-vault-v1:' + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value):
    if not value or value.startswith(PREFIX): return value
    return PREFIX + cipher().encrypt(value.encode()).decode()


def decrypt(value):
    if not value or not value.startswith(PREFIX): return value
    try: return cipher().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken: raise RuntimeError('Stored credential cannot be decrypted. Restore the original server encryption secret.') from None


def migrate():
    from . import db
    for row in db.query('SELECT key,value FROM settings_kv'):
        if sensitive(row['key']) and row['value'] and not row['value'].startswith(PREFIX):
            # Compare-and-swap avoids overwriting a concurrent credential rotation.
            db.execute('UPDATE settings_kv SET value=? WHERE key=? AND value=?', (encrypt(row['value']), row['key'], row['value']))
