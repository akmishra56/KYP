import copy
import json
import os
import re
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlencode, quote
from kyp.repository import Repository
from kyp.parser import parse_label
from kyp.matcher import match
from kyp.ingest import transform, POLICY
import test_stage1

class SourceAdapterTests(unittest.TestCase):
 def setUp(self):
  fixtures=Path(__file__).parent/'fixtures'
  self.chebi=json.loads((fixtures/'chebi-water.json').read_text(encoding='utf-8'))
  self.wikidata=json.loads((fixtures/'wikidata-water.json').read_text(encoding='utf-8'))
 def test_recorded_sources_produce_cited_drafts(self):
  sources, ingredient=transform(POLICY['seeds'][0],self.chebi,self.wikidata)
  with tempfile.TemporaryDirectory() as folder:
   repo=Repository(Path(folder)/'source.sqlite3')
   repo.import_document({'sources':sources,'ingredients':[ingredient]})
   self.assertIsNone(repo.ingredient(ingredient['id'])['description'])
   self.assertEqual(len(repo.pending()['sources']),2)
 def test_changed_cross_reference_rejected(self):
  data=json.loads(self.wikidata['content']);data['entities']['Q283']['claims']['P683']=[]
  self.wikidata['content']=json.dumps(data)
  with self.assertRaises(ValueError):transform(POLICY['seeds'][0],self.chebi,self.wikidata)
 def test_unsupported_alias_rejected(self):
  seed=copy.deepcopy(POLICY['seeds'][0]);seed['aliases'].append('unsupported-name')
  with self.assertRaises(ValueError):transform(seed,self.chebi,self.wikidata)
 def test_composite_alias_requires_every_component(self):
  sources,ingredient=transform(POLICY['seeds'][0],self.chebi,self.wikidata)
  with tempfile.TemporaryDirectory() as folder:
   repo=Repository(Path(folder)/'source.sqlite3');repo.import_document({'sources':sources,'ingredients':[ingredient]})
   self.assertEqual(match(parse_label('Water (Aqua/Eau)')[0],repo)['match_method'],'composite_alias')
   self.assertEqual(match(parse_label('Water (Mystery)')[0],repo)['match_status'],'unmatched')

@unittest.skipUnless(os.getenv('KYP_TEST_POSTGRES_URL'), 'Set KYP_TEST_POSTGRES_URL for isolated PostgreSQL integration tests')
class PostgreSQLTests(test_stage1.FoundationTests):
 def setUp(self):
  import psycopg
  from psycopg import sql
  self.schema='kyp_test_'+uuid.uuid4().hex
  self.url=os.environ['KYP_TEST_POSTGRES_URL']
  with psycopg.connect(self.url) as db:db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
  self.addCleanup(self.remove_schema)
  self.path=self.url+('\u0026' if '?' in self.url else '?')+urlencode({'options':'-c search_path='+self.schema},quote_via=quote)
  self.repo=Repository(self.path)
  from test_stage1 import DOCUMENT
  self.repo.import_document(DOCUMENT)
 def test_sqlite_migration_preserves_review_and_is_idempotent(self):
  from kyp.migrate import migrate
  document=copy.deepcopy(test_stage1.DOCUMENT)
  document['sources'][0]['id']='migration-source'
  document['ingredients'][0]['id']='migration-ingredient'
  document['ingredients'][0]['contexts']=['food']
  document['ingredients'][0]['description']['citations'][0]['source_id']='migration-source'
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'migration.sqlite3';old=Repository(path);old.import_document(document)
   old.approve_source('migration-source','migration-source-reviewer')
   old.approve_description(old.pending()['descriptions'][0]['id'],'migration-description-reviewer')
   migrate(str(path),self.path)
   self.assertIn('migration-ingredient',[item['id'] for item in self.repo.index('food')])
   self.assertNotIn('migration-ingredient',[item['id'] for item in self.repo.index('cosmetics')])
   first=self.repo.ingredient('migration-ingredient')
   self.assertEqual(first['description']['reviewed_by'],'migration-description-reviewer')
   migrate(str(path),self.path)
   self.assertEqual(self.repo.ingredient('migration-ingredient'),first)
   self.assertEqual(len(self.repo.review_history('description',old.pending('approved')['descriptions'][0]['id'])),1)
 def tearDown(self):
  # PostgreSQL schemas are removed by addCleanup, including failed setup.
  pass
 def remove_schema(self):
  import psycopg
  from psycopg import sql
  assert re.fullmatch(r'kyp_test_[0-9a-f]{32}',self.schema)
  with psycopg.connect(self.url) as db:db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
