"""Shared anonymous capabilities and bounded request counters; no label retention."""
import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException

class SharedOperations:
    def __init__(self, repository, secret):
        self.repository, self.secret = repository, secret.encode()
        with repository.connection() as db:
            if repository.postgres: db.execute('SELECT pg_advisory_xact_lock(84392302)')
            else: db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS scan_sessions(id TEXT PRIMARY KEY, capability_hash TEXT NOT NULL, expires_at BIGINT NOT NULL, ocr_quality DOUBLE PRECISION)')
            columns = {row['column_name'] for row in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='scan_sessions'").fetchall()} if repository.postgres else {row['name'] for row in db.execute('PRAGMA table_info(scan_sessions)').fetchall()}
            if 'parsing_mode' not in columns: db.execute("ALTER TABLE scan_sessions ADD COLUMN parsing_mode TEXT NOT NULL DEFAULT 'structured'")
            db.execute('CREATE INDEX IF NOT EXISTS scan_session_expiry ON scan_sessions(expires_at)')
            db.execute('CREATE TABLE IF NOT EXISTS request_buckets(key TEXT PRIMARY KEY, expires_at BIGINT NOT NULL, hits INTEGER NOT NULL)')
    def cleanup(self):
        with self.repository.connection() as db:
            instant=int(time.time())
            db.execute('DELETE FROM scan_sessions WHERE expires_at<=?',(instant,))
            db.execute('DELETE FROM request_buckets WHERE expires_at<=?',(instant,))
    def _hash(self, value):
        return hmac.new(self.secret,value.encode(),hashlib.sha256).hexdigest()
    def create(self, confidence=None, parsing_mode="structured"):
        instant=int(time.time())
        identity,capability=secrets.token_urlsafe(24),secrets.token_urlsafe(32)
        with self.repository.connection() as db:
            if self.repository.postgres: db.execute('SELECT pg_advisory_xact_lock(84392303)')
            else: db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM scan_sessions WHERE expires_at<=?',(instant,))
            count=db.execute('SELECT COUNT(*) AS count FROM scan_sessions').fetchone()['count']
            if count>=10000: raise HTTPException(503,'Scan capacity reached; retry later')
            db.execute('INSERT INTO scan_sessions VALUES(?,?,?,?,?)',(identity,self._hash(capability),instant+1800,confidence,parsing_mode))
        return identity,capability
    def authorize(self, identity, capability, include_mode=False):
        with self.repository.connection() as db:
            row=db.execute('SELECT capability_hash,expires_at,ocr_quality,parsing_mode FROM scan_sessions WHERE id=?',(identity,)).fetchone()
        if not row or row['expires_at']<=int(time.time()) or not capability or not secrets.compare_digest(row['capability_hash'],self._hash(capability)):
            raise HTTPException(404,'Scan not found or expired')
        return (row['ocr_quality'], row['parsing_mode']) if include_mode else row['ocr_quality']
    def allow(self, client, group, limit, seconds=60):
        instant=int(time.time());window=instant//seconds
        key=self._hash(str(window)+':'+group+':'+client)
        with self.repository.connection() as db:
            db.execute('DELETE FROM request_buckets WHERE expires_at<=?',(instant,))
            row=db.execute('INSERT INTO request_buckets VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET hits=request_buckets.hits+1 RETURNING hits',(key,(window+1)*seconds)).fetchone()
        return row['hits']<=limit
