"""Durable small media files for the single-owner serverless deployment.

On Supabase these bytes are in the private Postgres schema, not a public bucket.
Local/Docker deployments retain their existing filesystem implementation.
"""
import mimetypes
import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import Response
from starlette.staticfiles import StaticFiles

from . import db
from .config import settings

MAX_FILE_BYTES = 10 * 1024 * 1024


def persist_file(path: Path):
    if not os.getenv('DATABASE_URL'): return
    key = path.resolve().relative_to(settings.media_dir.resolve()).as_posix()
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES: raise ValueError('Media files must be 10 MB or smaller.')
    content_type = mimetypes.guess_type(key)[0] or 'application/octet-stream'
    db.execute('INSERT INTO media_files(path, data, content_type, updated_at) VALUES(?,?,?,?) '
               'ON CONFLICT(path) DO UPDATE SET data=excluded.data, content_type=excluded.content_type, updated_at=excluded.updated_at',
               (key, data, content_type, db.now()))


def restore_file(path: Path):
    if not os.getenv('DATABASE_URL'): return
    key = path.resolve().relative_to(settings.media_dir.resolve()).as_posix()
    row = db.one('SELECT data FROM media_files WHERE path=?', (key,))
    if row:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(row['data']))


class DurableMedia(StaticFiles):
    async def get_response(self, path, scope):
        if not os.getenv('DATABASE_URL'): return await super().get_response(path, scope)
        # Never resolve arbitrary client paths on disk.
        key = Path(path)
        if key.is_absolute() or '..' in key.parts: raise HTTPException(404)
        row = db.one('SELECT data, content_type FROM media_files WHERE path=?', (key.as_posix(),))
        if not row: raise HTTPException(404)
        return Response(bytes(row['data']), media_type=row['content_type'], headers={
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        })
