import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from kyp.cosing import build_document, transform_record, valid_cas
from kyp.repository import Repository, SCHEMA

FIXTURE=json.loads(Path(__file__).with_name('fixtures').joinpath('cosing.json').read_text(encoding='utf-8'))

class CosIngTests(unittest.TestCase):
 def test_recorded_snapshots_produce_cited_drafts(self):
  document,report=build_document(FIXTURE)
  self.assertEqual(report['matched'],3)
  self.assertFalse(report['review_required'])
  with tempfile.TemporaryDirectory() as folder:
   repo=Repository(Path(folder)/'test.db');repo.import_document(document);repo.import_document(document)
   self.assertEqual(len(repo.index()),3)
   self.assertEqual(repo.stats()['ingredients_with_published_descriptions'],0)
   for item in document['ingredients']:
    if 'description' in item:self.assertEqual(item['description']['provenance']['context'],'cosmetics')
   retinol=next(item for item in document['ingredients'] if item['name']=='RETINOL')
   self.assertNotIn('description',retinol)
 def test_duplicate_identity_is_quarantined(self):
  snapshot=copy.deepcopy(FIXTURE)
  extra=copy.deepcopy(snapshot['ingredients'][0]);extra['substanceId']=['999999999'];snapshot['ingredients'].append(extra)
  document,report=build_document(snapshot)
  self.assertIn(extra['inciName'][0],report['ambiguous'])
  self.assertEqual(report['matched'],2)
 def test_wrong_crosswalk_is_rejected(self):
  snapshot=copy.deepcopy(FIXTURE)
  aqua=next(row for row in snapshot['ingredients'] if row['inciName']==['AQUA']);aqua['casNo']=['56-81-5']
  document,report=build_document(snapshot)
  self.assertEqual(report['review_required'][0]['name'],'AQUA')
  self.assertFalse(any(item['id']=='chebi-15377' for item in document['ingredients']))
 def test_inactive_and_inexact_names_are_rejected(self):
  record=copy.deepcopy(FIXTURE['ingredients'][0]);record['status']=['Inactive']
  with self.assertRaises(ValueError):transform_record(record,{},FIXTURE['retrieved_at'])
  record['status']=['Active'];record['inciName']=['NOT A CANDIDATE']
  with self.assertRaises(ValueError):transform_record(record,{},FIXTURE['retrieved_at'])
 def test_cas_checksum_and_ambiguous_cas_aliases(self):
  self.assertTrue(valid_cas('7732-18-5'));self.assertFalse(valid_cas('7732-18-6'))
  record=copy.deepcopy(next(row for row in FIXTURE['ingredients'] if row['inciName']==['NIACINAMIDE']))
  record['casNo']=['7732-18-5 / 56-81-5']
  _,ingredient=transform_record(record,{},FIXTURE['retrieved_at'])
  self.assertFalse(any(valid_cas(alias) for alias in ingredient['aliases']))

class SchemaMigrationTests(unittest.TestCase):
 def test_schema_one_approvals_are_preserved_and_audited_once(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'legacy.db'
   with sqlite3.connect(path) as db:
    db.executescript(SCHEMA)
    db.execute('INSERT INTO sources VALUES(?,?,?,?)',('legacy','{}','previous reviewer','2025-01-01T00:00:00+00:00'))
   db.close()
   repo=Repository(path);Repository(path)
   events=repo.review_history('source','legacy')
   self.assertEqual(len(events),1)
   self.assertEqual(events[0]['reviewer'],'previous reviewer')
   self.assertEqual(events[0]['decision'],'approved')
   self.assertEqual(len(repo.pending('approved')['sources']),1)
