"""Transactional SQLite/PostgreSQL repository with reviewed descriptions."""
import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingredients(id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS aliases(ingredient_id TEXT NOT NULL REFERENCES ingredients(id), alias TEXT NOT NULL, PRIMARY KEY(ingredient_id,alias));
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, payload TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS descriptions(id TEXT PRIMARY KEY, ingredient_id TEXT NOT NULL REFERENCES ingredients(id), payload TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT);
"""

def now():
    return datetime.now(timezone.utc).isoformat()

class Database:
    """Portable parameter binding for the repository's static SQL statements."""
    def __init__(self, connection, postgres):
        self.connection, self.postgres = connection, postgres
    def execute(self, statement, parameters=()):
        return self.connection.execute(statement.replace('?', '%s') if self.postgres else statement, parameters)

class Repository:
    def __init__(self, path):
        self.path = str(path)
        self.postgres = self.path.startswith(('postgresql://', 'postgres://'))
        self.backend = 'postgresql' if self.postgres else 'sqlite-development'
        if not self.postgres:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            if self.postgres:
                db.execute('SELECT pg_advisory_xact_lock(84392301)')
            else:
                db.execute('BEGIN IMMEDIATE')
            for statement in SCHEMA.split(';'):
                if statement.strip():
                    db.execute(statement)
            db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            db.execute('INSERT INTO schema_migrations VALUES(?,?) ON CONFLICT DO NOTHING', (1, now()))
            self._migrate_reviews(db)
            self._migrate_contexts(db)

    def _migrate_reviews(self, db):
        if db.execute('SELECT version FROM schema_migrations WHERE version=2').fetchone():
            return
        db.execute('CREATE TABLE IF NOT EXISTS review_events(id TEXT PRIMARY KEY, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)')
        for table, subject in [('sources', 'source'), ('descriptions', 'description')]:
            db.execute("ALTER TABLE " + table + " ADD COLUMN review_state TEXT NOT NULL DEFAULT 'pending' CHECK(review_state IN ('pending','approved','rejected'))")
            db.execute("UPDATE " + table + " SET review_state='approved' WHERE reviewed_at IS NOT NULL")
            for row in db.execute("SELECT id,reviewed_by,reviewed_at FROM " + table + " WHERE review_state='approved'").fetchall():
                db.execute('INSERT INTO review_events VALUES(?,?,?,?,?,?,?)', (uuid.uuid4().hex, subject, row['id'], 'approved', row['reviewed_by'] or 'legacy review attribution unavailable', 'Approval preserved from schema v1', row['reviewed_at']))
        db.execute('CREATE INDEX IF NOT EXISTS review_events_subject ON review_events(subject_type,subject_id,created_at)')
        db.execute('CREATE INDEX IF NOT EXISTS descriptions_public ON descriptions(ingredient_id,review_state,reviewed_at)')
        db.execute('INSERT INTO schema_migrations VALUES(?,?)', (2, now()))

    def _migrate_contexts(self, db):
        if db.execute('SELECT version FROM schema_migrations WHERE version=3').fetchone():
            return
        db.execute("CREATE TABLE ingredient_contexts(ingredient_id TEXT NOT NULL REFERENCES ingredients(id), context TEXT NOT NULL CHECK(context IN ('general','food','cosmetics')), PRIMARY KEY(ingredient_id,context))")
        contexts = defaultdict(set)
        for row in db.execute('SELECT ingredient_id,payload FROM descriptions').fetchall():
            domain = json.loads(row['payload']).get('provenance', {}).get('context', 'general')
            if domain in {'general', 'food', 'cosmetics'}:
                contexts[row['ingredient_id']].add(domain)
        for row in db.execute('SELECT id FROM ingredients').fetchall():
            # Backfill the versioned adapters' namespaces, including identities without descriptions.
            if row['id'].startswith('cosing-'): contexts[row['id']].add('cosmetics')
            elif row['id'].startswith(('fda-food-', 'food-')): contexts[row['id']].add('food')
            for domain in contexts[row['id']] or {'general'}:
                db.execute('INSERT INTO ingredient_contexts VALUES(?,?) ON CONFLICT DO NOTHING', (row['id'], domain))
        db.execute('CREATE INDEX ingredient_context_filter ON ingredient_contexts(context,ingredient_id)')
        db.execute('INSERT INTO schema_migrations VALUES(?,?)', (3, now()))

    @contextmanager
    def connection(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            db = psycopg.connect(self.path, row_factory=dict_row, connect_timeout=10)
        else:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
        try:
            if self.postgres:
                with db.transaction():
                    yield Database(db, True)
            else:
                with db:
                    yield Database(db, False)
        finally:
            db.close()

    def import_document(self, document):
        if set(document) - {'sources', 'ingredients'}:
            raise ValueError('Unknown import fields')
        with self.connection() as db:
            for source in document.get('sources', []):
                required = {'id', 'url', 'licence', 'attribution', 'retrieved_at', 'content'}
                if set(source) != required or any(not isinstance(source[k], str) or not source[k].strip() for k in required):
                    raise ValueError('Sources require non-empty identity, URL, licence, attribution, retrieval date and content')
                parsed = urlparse(source['url'])
                if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                    raise ValueError('Source URL must be HTTP(S)')
                datetime.fromisoformat(source['retrieved_at'])
                payload = json.dumps(source, sort_keys=True)
                existing = db.execute('SELECT payload FROM sources WHERE id=?', (source['id'],)).fetchone()
                if existing and existing['payload'] != payload:
                    raise ValueError('Source records are immutable; use a new source ID')
                db.execute('INSERT INTO sources(id,payload) VALUES(?,?) ON CONFLICT DO NOTHING', (source['id'], payload))
            for item in document.get('ingredients', []):
                if set(item) - {'id', 'name', 'aliases', 'description', 'contexts'} or not item.get('id') or not item.get('name'):
                    raise ValueError('Ingredient requires id and name; unrecognized fields are rejected')
                if not isinstance(item['id'], str) or not isinstance(item['name'], str) or not item['name'].strip():
                    raise ValueError('Ingredient identity must be non-empty text')
                old = db.execute('SELECT name FROM ingredients WHERE id=?', (item['id'],)).fetchone()
                if old and old['name'] != item['name']:
                    raise ValueError('Ingredient identity cannot change on import')
                db.execute('INSERT INTO ingredients VALUES(?,?) ON CONFLICT DO NOTHING', (item['id'], item['name']))
                domains = item.get('contexts')
                if domains is not None:
                    if not isinstance(domains, list) or not domains or any(not isinstance(domain, str) or domain not in {'general','food','cosmetics'} for domain in domains):
                        raise ValueError('Ingredient contexts require a non-empty list of supported product types')
                elif item.get('description') is not None:
                    if not isinstance(item['description'], dict): raise ValueError('Description must be an object')
                    provenance = item['description'].get('provenance', {})
                    domains = [provenance.get('context', 'general')] if isinstance(provenance, dict) else []
                elif not old:
                    domains = ['general']
                for domain in domains or []:
                    if not isinstance(domain, str) or domain not in {'general','food','cosmetics'}: raise ValueError('Unsupported ingredient context')
                    db.execute('INSERT INTO ingredient_contexts VALUES(?,?) ON CONFLICT DO NOTHING', (item['id'], domain))
                for alias in item.get('aliases', []):
                    if not isinstance(alias, str) or not alias.strip():
                        raise ValueError('Aliases must be non-empty strings')
                    db.execute('INSERT INTO aliases VALUES(?,?) ON CONFLICT DO NOTHING', (item['id'], alias))
                if item.get('description') is not None:
                    desc = item['description']
                    if not {'text', 'citations'} <= set(desc) or set(desc) - {'text', 'citations', 'provenance'} or not isinstance(desc['text'], str) or not 1 <= len(desc['text'].strip()) <= 600 or not desc['citations']:
                        raise ValueError('Description requires short text and citations')
                    if 'provenance' in desc and (not isinstance(desc['provenance'], dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in desc['provenance'].items())):
                        raise ValueError('Description provenance must contain text fields')
                    if desc.get('provenance', {}).get('context', 'general') not in {'general', 'food', 'cosmetics'}:
                        raise ValueError('Unsupported description context')
                    for cite in desc['citations']:
                        if set(cite) != {'source_id', 'excerpt'} or not isinstance(cite['excerpt'], str) or not cite['excerpt'].strip():
                            raise ValueError('Citation requires source ID and excerpt')
                        source = db.execute('SELECT payload FROM sources WHERE id=?', (cite['source_id'],)).fetchone()
                        if not source or cite['excerpt'] not in json.loads(source['payload'])['content']:
                            raise ValueError('Supporting excerpt is absent from the source snapshot')
                    payload = json.dumps(desc, sort_keys=True)
                    desc_id = hashlib.sha256((item['id'] + payload).encode()).hexdigest()
                    db.execute('INSERT INTO descriptions(id,ingredient_id,payload) VALUES(?,?,?) ON CONFLICT DO NOTHING', (desc_id, item['id'], payload))

    def _review(self, subject, identity, reviewer, decision, reason):
        if subject not in {'source', 'description'} or decision not in {'approved', 'rejected'}:
            raise ValueError('Unsupported review decision')
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 200:
            raise ValueError('A named reviewer of at most 200 characters is required')
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError('A review reason of at most 1,000 characters is required')
        table = 'sources' if subject == 'source' else 'descriptions'
        with self.connection() as db:
            row = db.execute('SELECT * FROM ' + table + ' WHERE id=?', (identity,)).fetchone()
            if not row:
                raise ValueError(subject.capitalize() + ' not found')
            if decision == 'approved' and subject == 'description':
                for citation in json.loads(row['payload'])['citations']:
                    source = db.execute('SELECT review_state FROM sources WHERE id=?', (citation['source_id'],)).fetchone()
                    if not source or source['review_state'] != 'approved':
                        raise ValueError('Review source reuse permission before approving descriptions')
            if row['review_state'] == decision:
                return
            timestamp = now()
            db.execute('UPDATE ' + table + ' SET reviewed_by=?,reviewed_at=?,review_state=? WHERE id=?', (reviewer, timestamp if decision == 'approved' else None, decision, identity))
            db.execute('INSERT INTO review_events VALUES(?,?,?,?,?,?,?)', (uuid.uuid4().hex, subject, identity, decision, reviewer, reason, timestamp))

    def approve_source(self, source_id, reviewer):
        self._review('source', source_id, reviewer, 'approved', 'Reviewer attests that source reuse permission and attribution were checked')

    def approve_description(self, desc_id, reviewer):
        self._review('description', desc_id, reviewer, 'approved', 'Reviewer attests that the cited source supports the description')

    def reject_source(self, source_id, reviewer, reason):
        self._review('source', source_id, reviewer, 'rejected', reason)

    def reject_description(self, desc_id, reviewer, reason):
        self._review('description', desc_id, reviewer, 'rejected', reason)

    def pending(self, state='pending'):
        if state not in {'pending', 'approved', 'rejected'}:
            raise ValueError('Unknown review state')
        with self.connection() as db:
            return {table: [dict(row) for row in db.execute('SELECT * FROM ' + table + ' WHERE review_state=? ORDER BY id', (state,))] for table in ('sources', 'descriptions')}

    def review_history(self, subject, identity):
        if subject not in {'source', 'description'}:
            raise ValueError('Unknown review subject')
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM review_events WHERE subject_type=? AND subject_id=? ORDER BY created_at,id', (subject, identity))]

    def index(self, context='general'):
        if context not in {'general','food','cosmetics'}: raise ValueError('Unknown product context')
        with self.connection() as db:
            aliases = defaultdict(list)
            for row in db.execute('SELECT ingredient_id,alias FROM aliases ORDER BY alias'):
                aliases[row['ingredient_id']].append(row['alias'])
            if context == 'general':
                rows = db.execute('SELECT * FROM ingredients ORDER BY id').fetchall()
            else:
                rows = db.execute("SELECT * FROM ingredients WHERE id IN (SELECT ingredient_id FROM ingredient_contexts WHERE context IN (?, 'general')) ORDER BY id", (context,)).fetchall()
            return [{'id': row['id'], 'name': row['name'], 'aliases': aliases[row['id']]} for row in rows]

    def stats(self):
        with self.connection() as db:
            total = db.execute('SELECT COUNT(*) AS count FROM ingredients').fetchone()['count']
            approved_sources = {row['id'] for row in db.execute("SELECT id FROM sources WHERE review_state='approved'")}
            visible, seen = 0, set()
            for row in db.execute("SELECT ingredient_id,payload FROM descriptions WHERE review_state='approved' ORDER BY reviewed_at DESC,id"):
                if row['ingredient_id'] in seen:
                    continue
                seen.add(row['ingredient_id'])
                if all(citation['source_id'] in approved_sources for citation in json.loads(row['payload'])['citations']):
                    visible += 1
            return {'schema_version': 3, 'ingredients': total, 'aliases': db.execute('SELECT COUNT(*) AS count FROM aliases').fetchone()['count'], 'ingredients_with_published_descriptions': visible, 'ingredients_without_published_descriptions': total - visible, 'source_reviews': {state: db.execute('SELECT COUNT(*) AS count FROM sources WHERE review_state=?', (state,)).fetchone()['count'] for state in ('pending','approved','rejected')}, 'description_reviews': {state: db.execute('SELECT COUNT(*) AS count FROM descriptions WHERE review_state=?', (state,)).fetchone()['count'] for state in ('pending','approved','rejected')}}

    def ingredient(self, ingredient_id, context='general'):
        if context not in {'general', 'food', 'cosmetics'}:
            raise ValueError('Unknown product context')
        with self.connection() as db:
            row = db.execute('SELECT * FROM ingredients WHERE id=?', (ingredient_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result['description'] = None
            result['description_status'] = 'unavailable'
            candidates = db.execute("SELECT * FROM descriptions WHERE ingredient_id=? AND review_state='approved' ORDER BY reviewed_at DESC,id", (ingredient_id,)).fetchall()
            # Prefer the requested domain, then a domain-neutral identity description.
            # A cosmetic function is never a fallback for a food product (or vice versa).
            desc = next((item for domain in dict.fromkeys((context, 'general')) for item in candidates if json.loads(item['payload']).get('provenance', {}).get('context', 'general') == domain), None)
            result['product_context'] = context
            if desc:
                payload = json.loads(desc['payload'])
                sources = []
                for cite in payload['citations']:
                    record = db.execute("SELECT * FROM sources WHERE id=? AND review_state='approved'", (cite['source_id'],)).fetchone()
                    if not record:
                        return result
                    source = json.loads(record['payload'])
                    sources.append({k: source[k] for k in ('id', 'url', 'licence', 'attribution', 'retrieved_at')} | {'excerpt': cite['excerpt']})
                result.update(description_status='available', description={'text': payload['text'], 'sources': sources, 'reviewed_at': desc['reviewed_at'], 'reviewed_by': desc['reviewed_by'], 'provenance': payload.get('provenance', {})})
            return result
