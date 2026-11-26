"""Request size/shape guards and database-backed fixed-window rate limiting.
Counters are atomic and shared by warm processes through the existing database.
No request bodies, keys, passwords or query strings are logged.
"""
import hashlib
import json
import time
from starlette.responses import JSONResponse

SCHEMA = '''CREATE TABLE IF NOT EXISTS request_limits (id TEXT PRIMARY KEY, bucket INTEGER NOT NULL, count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (id TEXT PRIMARY KEY, actor TEXT NOT NULL, method TEXT NOT NULL, path TEXT NOT NULL, status INTEGER NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS request_limits_bucket ON request_limits(bucket);
CREATE INDEX IF NOT EXISTS audit_events_created ON audit_events(created);'''


def initialize():
    from . import db
    db.get_conn().executescript(SCHEMA)
    db.get_conn().commit()


def consume(key, limit, seconds=60):
    from . import db
    window = int(time.time()) // seconds
    if __import__('secrets').randbelow(100) == 0: db.execute('DELETE FROM request_limits WHERE bucket<?',(window-1440,))
    row = db.one('INSERT INTO request_limits(id,bucket,count) VALUES(?,?,1) ON CONFLICT(id) DO UPDATE SET count=CASE WHEN request_limits.bucket=excluded.bucket THEN request_limits.count+1 ELSE 1 END,bucket=excluded.bucket RETURNING count', (hashlib.sha256(key.encode()).hexdigest(), window))
    return row['count'] <= limit


def shape(value, depth=0):
    if depth > 24: raise ValueError('JSON nesting exceeds 24 levels.')
    if isinstance(value, str) and (len(value) > 1_500_000 or '\x00' in value): raise ValueError('Invalid or oversized string.')
    if isinstance(value, dict):
        if len(value) > 1000: raise ValueError('Too many object fields.')
        for k, v in value.items():
            if len(k) > 256 or '\x00' in k: raise ValueError('Invalid field name.')
            shape(v, depth + 1)
    elif isinstance(value, list):
        if len(value) > 2000: raise ValueError('Too many list entries.')
        for item in value: shape(item, depth + 1)


class RequestGuard:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope, receive, send)
        path = scope.get('path', '')
        async def reject(code, message):
            return await JSONResponse({'detail': message}, status_code=code, headers={'Cache-Control':'no-store', **({'Retry-After':'60'} if code == 429 else {})})(scope, receive, send)
        if len(path) > 2048 or len(scope.get('query_string', b'')) > 8192 or '\x00' in path:
            return await reject(400, 'Invalid request URL.')
        if path.startswith('/api/') or path in ('/', '/healthz'):
            headers = dict(scope.get('headers', []))
            ip = (scope.get('client') or ('unknown',))[0]
            if __import__('os').getenv('VERCEL') == '1': ip = headers.get(b'x-vercel-forwarded-for',b'').decode().split(',')[0].strip() or ip
            try:
                if not consume('ip:' + ip, 1200): return await reject(429, 'Request limit reached. Retry in one minute.')
                identity = headers.get(b'cookie', b'') + headers.get(b'authorization', b'')
                actor = hashlib.sha256(identity).hexdigest() if identity else ip
                expensive = path in ('/api/chat', '/api/image', '/api/models/benchmark') or path.endswith(('/generate', '/images', '/models'))
                limit = 12 if '/auth/' in path and scope['method'] == 'POST' else 30 if expensive else 600
                category = 'auth' if '/auth/' in path else 'ai' if expensive else 'api'
                if category == 'auth': actor = ip
                if not consume(category + ':' + actor, limit): return await reject(429, 'Rate limit reached. Retry in one minute.')
            except Exception:
                if path not in ('/', '/healthz'): return await reject(503, 'Request protection unavailable. Retry shortly.')
        body = b''
        if scope['method'] in ('POST', 'PUT', 'PATCH', 'DELETE'):
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect': return
                body += message.get('body', b'')
                if len(body) > 2_000_000: return await reject(413, 'Request exceeds the 2 MB limit.')
                if not message.get('more_body'): break
            content_type = dict(scope.get('headers', [])).get(b'content-type', b'').decode()
            if body and 'application/json' in content_type:
                try: shape(json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number.'))))
                except (ValueError, RecursionError): return await reject(422, 'Invalid JSON structure, string or size.')
            elif body and not content_type.startswith('multipart/form-data'):
                return await reject(415, 'Use application/json or multipart/form-data.')
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered: return await receive()
            delivered = True
            return {'type':'http.request', 'body':body, 'more_body':False}
        async def audit_send(message):
            if message['type'] == 'http.response.start' and path.startswith('/api/') and scope['method'] not in ('GET','HEAD','OPTIONS'):
                try:
                    from . import db
                    identity = scope.get('state', {}).get('identity', {})
                    safe_path = path[:512]
                    db.execute('INSERT INTO audit_events(id,actor,method,path,status,created) VALUES(?,?,?,?,?,?)', (db.new_id('audit'), identity.get('id', 'anonymous'), scope['method'], safe_path, message['status'], time.time()))
                    # Bounded retention; requests, not an imaginary serverless cron.
                    db.execute('DELETE FROM audit_events WHERE created<?', (time.time()-int(json.loads(db.kv_get('instance_configuration','{"retention_days":30}')).get('retention_days',30))*86400,))
                except Exception: pass  # Never turn a completed mutation into a failed response.
            await send(message)
        await self.app(scope, replay if scope['method'] in ('POST','PUT','PATCH','DELETE') else receive, audit_send)
