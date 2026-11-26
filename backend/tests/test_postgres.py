"""Adapter unit tests plus optional local-only PostgreSQL wire integration."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.postgres import Connection, Row, postgres_schema, qmark_sql


def test_bind_markers_do_not_rewrite_sql_literals_or_comments():
    assert qmark_sql("SELECT ?, '?', 'it''s ?' -- ?\n, ?") == "SELECT %s, '?', 'it''s ?' -- ?\n, %s"
    assert qmark_sql("SELECT ? WHERE name LIKE '%s%' OR name LIKE ?") == "SELECT %s WHERE name LIKE '%%s%%' OR name LIKE %s"


def test_schema_types_and_numeric_row_access():
    schema = postgres_schema('CREATE TABLE x(id INTEGER PRIMARY KEY AUTOINCREMENT, cost REAL, data BLOB);')
    assert 'AUTOINCREMENT' not in schema and 'DOUBLE PRECISION' in schema and 'BYTEA' in schema
    row = Row(id='first', value=2)
    assert row[0] == row['id'] == 'first'
    assert dict(row) == {'id': 'first', 'value': 2}


def test_reject_unknown_schema_before_connect():
    with pytest.raises(ValueError): Connection('public; DROP SCHEMA public')


@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'), reason='Set TEST_POSTGRES_URL to a disposable local database')
def test_local_postgres_persistence_and_sitebuilder(monkeypatch):
    url = os.environ['TEST_POSTGRES_URL']
    # Never run this integration test against a production/Supabase connection.
    assert 'host=/tmp/' in url or '@localhost' in url or '@127.0.0.1' in url
    monkeypatch.setenv('DATABASE_URL', url)
    from app import db, agents
    monkeypatch.setattr(db, '_conn', None)
    pid = db.new_id('pgtest')
    db.get_conn()
    agents.seed_agents()
    assert len(agents.list_agents()) >= 10
    db.execute('INSERT INTO projects(id,name,brief,created_at,updated_at) VALUES(?,?,?,?,?)',
               (pid, "Unicode مرحبا café ' ? %s", 'brief', db.now(), db.now()))
    db.execute('INSERT INTO media_files(path,data,content_type,updated_at) VALUES(?,?,?,?)',
               (pid, b'\x00\xff\x01', 'application/octet-stream', db.now()))
    db._conn.close()
    assert db.one('SELECT name FROM projects WHERE id=?', (pid,))['name'] == "Unicode مرحبا café ' ? %s"
    assert bytes(db.one('SELECT data FROM media_files WHERE path=?', (pid,))['data']) == b'\x00\xff\x01'
    from app import sitebuilder
    sitebuilder.init()
    sitebuilder.set_setting(pid, 'saved')
    assert sitebuilder.get_setting(pid) == 'saved'
    assert sitebuilder.project('demo')['files']['index.html']
    with sitebuilder.db() as conn:
        conn.execute('DELETE FROM settings WHERE key=?', (pid,))
    db.execute('DELETE FROM projects WHERE id=?', (pid,))
    db.execute('DELETE FROM media_files WHERE path=?', (pid,))
    db._conn.close()


def test_supabase_pooler_uses_bundled_ca_and_preserves_hostname_verification(monkeypatch):
    import hashlib
    import ssl
    from pathlib import Path
    from unittest.mock import Mock
    import psycopg
    connect = Mock()
    monkeypatch.setattr(psycopg, 'connect', connect)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://test:fake@aws-1-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=verify-full&sslrootcert=system')
    Connection('agency_office')
    options = connect.call_args.kwargs
    assert options['sslmode'] == 'verify-full'
    assert options['prepare_threshold'] is None
    pem = Path(options['sslrootcert']).read_text()
    assert hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest() == '807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
    monkeypatch.setenv('DATABASE_URL', 'postgresql://test:fake@other.example/postgres?sslmode=verify-full&sslrootcert=system')
    Connection('agency_office')
    assert connect.call_args.kwargs['sslrootcert'] == 'system'
