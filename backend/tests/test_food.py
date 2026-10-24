import copy
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from kyp.food import build_document, decode_rows, transform, POLICY, add_staples, add_code_aliases, add_oils

FIXTURE=json.loads(Path(__file__).with_name('fixtures').joinpath('fda-food.json').read_text(encoding='utf-8'))

class FoodAdapterTests(unittest.TestCase):
 def test_recorded_food_records_have_supported_descriptions(self):
  document,report=build_document(FIXTURE)
  self.assertEqual(report['matched'],6);self.assertFalse(report['review_required'])
  sources={s['id']:s for s in document['sources']}
  for item in document['ingredients']:
   desc=item['description'];self.assertEqual(desc['provenance']['context'],'food')
   for cite in desc['citations']:self.assertIn(cite['excerpt'],sources[cite['source_id']]['content'])
  salt=next(i for i in document['ingredients'] if i['name']=='SODIUM CHLORIDE')
  self.assertIn('salt',salt['aliases'])
  sugar=next(i for i in document['ingredients'] if i['name']=='SUCROSE')
  self.assertIn('sugar',sugar['aliases'])
 def test_crosswalk_cas_drift_is_quarantined(self):
  snapshot=copy.deepcopy(FIXTURE)
  salt=next(r for r in snapshot['rows'] if r['Substance'].strip()=='SODIUM CHLORIDE')
  salt['CAS Reg No (or other ID)']='77-92-9'
  _,report=build_document(snapshot)
  self.assertEqual(report['review_required'][0]['name'],'SODIUM CHLORIDE')
 def test_duplicates_are_not_chosen_arbitrarily(self):
  snapshot=copy.deepcopy(FIXTURE);snapshot['rows'].append(copy.deepcopy(snapshot['rows'][0]))
  _,report=build_document(snapshot)
  self.assertEqual(len(report['ambiguous']),1)
 def test_unknown_roles_do_not_get_invented_summaries(self):
  row=copy.deepcopy(FIXTURE['rows'][0]);row['Used for (Technical Effect)']='UNMAPPED ROLE'
  entry=next(e for e in POLICY['candidates'] if e['source_name']==row['Substance'].strip())
  _,item=transform(entry,row,FIXTURE['retrieved_at']);self.assertNotIn('description',item)
 def test_malformed_download_rejected(self):
  with self.assertRaises(ValueError):decode_rows(b'<html>unavailable</html>')

 def test_staple_definitions_are_bounded_and_cited(self):
  doc={'sources':[],'ingredients':[]}
  add_staples(doc,Path(__file__).with_name('fixtures')/'food-standards')
  self.assertEqual(len(doc['ingredients']),len(POLICY['staples']))
  self.assertIn('refined wheat flour',doc['ingredients'][0]['aliases'])
  self.assertIn('does not identify the individual spices',doc['ingredients'][1]['description']['text'])
  for source,item in zip(doc['sources'],doc['ingredients']):self.assertIn(item['description']['citations'][0]['excerpt'],source['content'])

 def test_recorded_food_codes_require_identity_and_alias_evidence(self):
  identities=json.loads(Path(__file__).with_name('fixtures').joinpath('food-code-identities.json').read_text(encoding='utf-8'))
  doc,_=build_document(FIXTURE)
  def recorded(url,*args):
   identity=url.rstrip('/').rsplit('/',1)[-1]
   return {'url':url,'retrieved_at':FIXTURE['retrieved_at'],'content':json.dumps(identities[identity],sort_keys=True)}
  with patch('kyp.food.snapshot',side_effect=recorded):add_code_aliases(doc,Path('unused-fixture-cache'))
  acid=next(i for i in doc['ingredients'] if i['name']=='citric acid')
  self.assertIn('INS-330',acid['aliases']);self.assertIn('E330',acid['aliases'])
  identities['30769']['database_accessions']['CAS']=[]
  with patch('kyp.food.snapshot',side_effect=recorded),self.assertRaises(ValueError):add_code_aliases(build_document(FIXTURE)[0],Path('unused-fixture-cache'))

 def test_oil_evidence_is_draft_and_identity_is_distinct(self):
  import tempfile
  with tempfile.TemporaryDirectory() as folder:
   cache=Path(folder);(cache/'palm-oil-evidence.json').write_text(json.dumps({'content':'Palm oil is derived from the fleshy mesocarp of the fruit of the oil palm','sha256':'a'*64,'retrieved_at':'2026-10-23T00:00:00+00:00'}))
   document=add_oils({'sources':[],'ingredients':[]},cache)
   self.assertEqual(document['ingredients'][0]['aliases'],[])
   self.assertIn('review pending',document['sources'][0]['licence'])
   from kyp.repository import Repository
   repo=Repository(cache/'fixture.sqlite3');repo.import_document(document)
   self.assertIsNone(repo.ingredient('food-palm-oil','food')['description'])
