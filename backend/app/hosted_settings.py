"""Refresh server-side provider settings across warm serverless instances."""
import os

from .config import settings, PROVIDER_PRESETS


def refresh():
    from . import db
    from .vault import decrypt, sensitive
    saved = {row['key']: decrypt(row['value']) if sensitive(row['key']) else row['value'] for row in db.query('SELECT key,value FROM settings_kv')}
    for key in PROVIDER_PRESETS:
        creds = settings.provider_creds.setdefault(key, {})
        for prefix, field in [('token', 'token'), ('model', 'model'), ('base', 'base_url'), ('image', 'image_model')]:
            if prefix + '_' + key in saved: creds[field] = saved[prefix + '_' + key]
    if saved.get('active_provider') in PROVIDER_PRESETS:
        settings.active_provider = saved['active_provider']
    active = settings.provider_creds.get(settings.active_provider, {})
    settings.api_token = active.get('token', '')
    settings.api_base_url = active.get('base_url') or settings.api_base_url
    settings.text_model = active.get('model') or settings.text_model
    if saved.get('image_model'): settings.image_model = saved['image_model']
    if saved.get('demo_mode') in ('true', 'false', 'auto'): settings.demo_mode = saved['demo_mode']
