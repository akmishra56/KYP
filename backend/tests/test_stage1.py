import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from kyp.api import create_app
from kyp.repository import Repository
from kyp.parser import parse_label
from kyp.matcher import match, match_many
from kyp.ocr import OCRUnavailable, TesseractOCR

# Synthetic data only. Nothing in this fixture is scientific or production seed data.
DOCUMENT = {
 'sources': [{'id': 'fixture-source', 'url': 'https://example.invalid/fixture', 'licence': 'TEST ONLY', 'attribution': 'Synthetic test fixture', 'retrieved_at': '2026-10-23T00:00:00+00:00', 'content': 'Demo carrier forms a formula base.'}],
 'ingredients': [{'id': 'carrier', 'name': 'Demo carrier', 'aliases': ['Carrier alias'], 'description': {'text': 'Demo carrier forms a formula base.', 'citations': [{'source_id': 'fixture-source', 'excerpt': 'Demo carrier forms a formula base.'}]}}, {'id': 'blank', 'name': 'Demo no description', 'aliases': []}]
}

class FoundationTests(unittest.TestCase):
 def setUp(self):
  self.folder = tempfile.TemporaryDirectory()
  self.path = Path(self.folder.name)/'test.sqlite3'
  self.repo = Repository(self.path)
  self.repo.import_document(DOCUMENT)
 def tearDown(self):
  self.folder.cleanup()
 def test_draft_descriptions_not_published(self):
  self.assertEqual(self.repo.ingredient('carrier')['description_status'], 'unavailable')
 def test_source_review_required(self):
  description = self.repo.pending()['descriptions'][0]['id']
  with self.assertRaises(ValueError): self.repo.approve_description(description, 'reviewer')
 def test_review_publishes_description_and_citation(self):
  self.repo.approve_source('fixture-source','licence-reviewer')
  self.repo.approve_description(self.repo.pending()['descriptions'][0]['id'],'content-reviewer')
  detail = self.repo.ingredient('carrier')
  self.assertEqual(detail['description']['sources'][0]['excerpt'], DOCUMENT['sources'][0]['content'])
 def test_idempotent_import_preserves_approval(self):
  self.repo.approve_source('fixture-source','reviewer')
  self.repo.import_document(DOCUMENT)
  self.assertEqual(len(self.repo.index()),2)
  self.assertEqual(len(self.repo.pending()['sources']),0)
  self.assertEqual(len(self.repo.pending()['descriptions']),1)
 def test_citationless_import_rolls_back(self):
  document=copy.deepcopy(DOCUMENT)
  document['ingredients'][0]['id']='bad'
  document['ingredients'][0]['description']['citations']=[]
  with self.assertRaises(ValueError):self.repo.import_document(document)
  self.assertIsNone(self.repo.ingredient('bad'))
 def test_fabricated_excerpt_rejected(self):
  document=copy.deepcopy(DOCUMENT)
  document['ingredients'][0]['description']['citations'][0]['excerpt']='Unsupported claim'
  with self.assertRaises(ValueError):self.repo.import_document(document)
 def test_sources_immutable(self):
  document=copy.deepcopy(DOCUMENT);document['sources'][0]['content']='Replacement'
  with self.assertRaises(ValueError):self.repo.import_document(document)
 def test_empty_review_identity_rejected(self):
  with self.assertRaises(ValueError):self.repo.approve_source('fixture-source',' ')
 def test_alias_matched_without_description(self):
  result=match(parse_label('Carrier alias')[0],self.repo)
  self.assertEqual(result['match_method'],'alias')
  self.assertIsNone(result['ingredient']['description'])
 def test_ambiguous_alias_not_forced(self):
  self.repo.import_document({'ingredients':[{'id':'other','name':'Other carrier','aliases':['Carrier alias']}]})
  result=match(parse_label('Carrier alias')[0],self.repo)
  self.assertEqual(result['match_status'],'ambiguous')
  self.assertIsNone(result['ingredient'])
 def test_fuzzy_suggestion_not_confirmed(self):
  result=match(parse_label('Demo carrie')[0],self.repo)
  self.assertEqual(result['match_status'],'unmatched')
  self.assertTrue(result['suggestions'])
 def test_unknown_remains_unmatched(self):
  result=match(parse_label('Mystery blend')[0],self.repo)
  self.assertIsNone(result['ingredient'])
 def test_rejected_source_withdraws_description_and_keeps_identity(self):
  self.repo.approve_source('fixture-source','automated fixture reviewer')
  desc=self.repo.pending()['descriptions'][0]['id']
  self.repo.approve_description(desc,'content fixture reviewer')
  self.repo.reject_source('fixture-source','withdrawal reviewer','Permission requires rechecking')
  self.assertIsNone(self.repo.ingredient('carrier')['description'])
  self.assertEqual(match(parse_label('Carrier alias')[0],self.repo)['match_status'],'matched')
  self.assertEqual(self.repo.stats()['ingredients_with_published_descriptions'],0)
  self.repo.approve_source('fixture-source','permission reviewer')
  self.assertIsNotNone(self.repo.ingredient('carrier')['description'])
  self.assertEqual([x['decision'] for x in self.repo.review_history('source','fixture-source')],['approved','rejected','approved'])
 def test_rejection_survives_import_and_retains_reason(self):
  desc=self.repo.pending()['descriptions'][0]['id']
  self.repo.reject_description(desc,'editor','Wording needs correction')
  self.repo.import_document(DOCUMENT)
  self.assertFalse(self.repo.pending()['descriptions'])
  self.assertEqual(self.repo.pending('rejected')['descriptions'][0]['id'],desc)
  self.assertIsNone(self.repo.ingredient('carrier')['description'])
  event=self.repo.review_history('description',desc)[0]
  self.assertEqual((event['reviewer'],event['reason']),('editor','Wording needs correction'))
  with self.assertRaises(ValueError):self.repo.approve_description(desc,'editor')
  self.repo.approve_source('fixture-source','licence reviewer')
  self.repo.approve_description(desc,'editor')
  self.assertIsNotNone(self.repo.ingredient('carrier')['description'])
 def test_batch_reads_catalog_and_each_detail_once(self):
  with patch.object(self.repo,'index',wraps=self.repo.index) as index, patch.object(self.repo,'ingredient',wraps=self.repo.ingredient) as detail:
   results=match_many(parse_label('Carrier alias, Demo carrier, Unknown'),self.repo)
  self.assertEqual([r['match_status'] for r in results],['matched','matched','unmatched'])
  self.assertEqual(index.call_count,1)
  self.assertEqual(detail.call_count,1)
 def test_overlong_fuzzy_query_stays_unmatched(self):
  with patch('kyp.matcher.CosineIndex.rank',side_effect=AssertionError('fuzzy work should be bounded')):
   self.assertEqual(match(parse_label('x'*513)[0],self.repo)['match_status'],'unmatched')
 def test_cosine_candidates_are_filtered_by_product_type(self):
  self.repo.import_document({'ingredients':[
   {'id':'food-salt','name':'Sodium chloride','aliases':['Salt'],'contexts':['food']},
   {'id':'food-citrate','name':'Sodium citrate','contexts':['food']},
   {'id':'cosmetic-only','name':'Retinol','contexts':['cosmetics']}]})
  typo=match(parse_label('Sodlum chlorlde')[0],self.repo,'food')
  self.assertEqual(typo['closest_candidates'][0]['id'],'food-salt')
  self.assertEqual(typo['match_status'],'unmatched')
  self.assertIsNone(typo['ingredient'])
  self.assertTrue(0 < typo['closest_candidates'][0]['similarity'] < 1)
  self.assertIsNone(typo['closest_candidates'][0]['match_probability'])
  excluded=match(parse_label('Retinol')[0],self.repo,'food')
  self.assertEqual(excluded['match_status'],'unmatched')
  self.assertNotIn('cosmetic-only',[item['id'] for item in excluded['closest_candidates']])
  self.assertEqual(match(parse_label('Retinol')[0],self.repo,'cosmetics')['match_status'],'matched')
 def test_exact_cosine_is_not_a_claim_of_correct_match_probability(self):
  result=match(parse_label('Carrier alias')[0],self.repo)
  self.assertEqual(result['match_similarity'],1)
  self.assertIsNone(result['match_probability'])
  self.assertEqual(result['probability_status'],'not_calibrated')
 def test_comma_word_sets_and_percentage_brackets(self):
  tokens=parse_label('Ingredients: Sodium\nchloride, Sugar (5%), Vegetable oil, Spices (Cumin, Coriander)',context='food')
  self.assertEqual([t.text for t in tokens],['Sodium chloride','Sugar','Vegetable oil','Cumin','Coriander'])
  result=match_many(tokens,self.repo,'food')
  self.assertEqual(result[0]['words'],['sodium','chloride'])
  self.assertEqual([t['position'] for t in result],[0,1,2,3,4])
 def test_preview_exposes_cosine_details_without_confirming(self):
  self.repo.import_document({'ingredients':[{'id':'food-salt','name':'Sodium chloride','contexts':['food']}]})
  with TestClient(create_app(str(self.path))) as client:
   text='Sodlum chlorlde, Carrier alias'
   scan=client.post('/scans',json={'text':text,'product_context':'food'}).json()
   self.assertEqual(scan['text'],text)
   self.assertEqual(len(scan['match_preview']),2)
   self.assertEqual(scan['match_preview'][0]['closest_candidates'][0]['id'],'food-salt')
   self.assertEqual(scan['match_preview'][0]['match_status'],'unmatched')
   self.assertIsNone(scan['match_preview'][0]['match_probability'])
   self.assertTrue(scan['review_required'])
 def test_explicit_contexts_survive_identity_only_alias_import(self):
  self.repo.import_document({'ingredients':[{'id':'scoped','name':'Scoped name','contexts':['cosmetics']}]})
  self.repo.import_document({'ingredients':[{'id':'scoped','name':'Scoped name','aliases':['Scoped alias']}]})
  self.assertNotIn('scoped',[item['id'] for item in self.repo.index('food')])
  self.assertIn('scoped',[item['id'] for item in self.repo.index('cosmetics')])
  with self.assertRaises(ValueError):self.repo.import_document({'ingredients':[{'id':'bad-context','name':'Bad context','contexts':['invented']}]})
 def test_product_context_never_crosses_description_domains(self):
  doc=copy.deepcopy(DOCUMENT)
  desc=doc['ingredients'][0]['description'];desc['provenance']={'context':'cosmetics'}
  self.repo.import_document(doc)
  self.repo.approve_source('fixture-source','fixture source reviewer')
  for row in self.repo.pending()['descriptions']:self.repo.approve_description(row['id'],'fixture content reviewer')
  self.assertEqual(self.repo.ingredient('carrier','cosmetics')['description']['provenance']['context'],'cosmetics')
  self.assertEqual(self.repo.ingredient('carrier','food')['description']['provenance'],{})
  doc['ingredients'][0]['description']['provenance']['context']='food';self.repo.import_document(doc)
  self.repo.approve_description(self.repo.pending()['descriptions'][0]['id'],'fixture food reviewer')
  self.assertEqual(self.repo.ingredient('carrier','food')['description']['provenance']['context'],'food')
  self.assertEqual(self.repo.ingredient('carrier','cosmetics')['description']['provenance']['context'],'cosmetics')
 def test_only_other_domain_description_is_unavailable(self):
  doc=copy.deepcopy(DOCUMENT);doc['ingredients']=[{'id':'domain-only','name':'Domain only','description':doc['ingredients'][0]['description']}]
  doc['ingredients'][0]['description']['provenance']={'context':'cosmetics'}
  self.repo.import_document(doc);self.repo.approve_source('fixture-source','fixture reviewer')
  desc=next(row['id'] for row in self.repo.pending()['descriptions'] if row['ingredient_id']=='domain-only')
  self.repo.approve_description(desc,'fixture reviewer')
  self.assertIsNone(self.repo.ingredient('domain-only','food')['description'])
  self.assertIsNone(self.repo.ingredient('domain-only')['description'])
  self.assertIsNotNone(self.repo.ingredient('domain-only','cosmetics')['description'])
 def test_food_advisories_excluded_with_compound_paths(self):
  tokens=parse_label('Ingredients: Seasoning (Salt, Sugar), Starch 10%. Contains: wheat. May contain milk.',context='food')
  self.assertEqual([t.text for t in tokens],['Salt','Sugar','Starch'])
  self.assertFalse(any(t.optional for t in tokens))
  self.assertEqual([t.text for t in parse_label('Salt, Sugar. May contain nuts',context='food')],['Salt','Sugar'])
 def test_api_context_validation_and_food_review(self):
  with TestClient(create_app(str(self.path))) as client:
   text='Ingredients: Carrier alias. Contains: milk'
   scan=client.post('/scans',json={'text':text,'product_context':'food'}).json()
   self.assertEqual(len(scan['tokens']),1)
   result=client.post('/scans/'+scan['id']+'/confirm',json={'text':text,'product_context':'food'},headers={'X-Scan-Token':scan['scan_token']})
   self.assertEqual(result.json()['matched_count'],1)
   self.assertEqual(result.json()['product_context'],'food')
   self.assertEqual(client.post('/scans',json={'text':'salt','product_context':'invented'}).status_code,422)
 def test_orientation_requires_consent_and_does_not_create_lookup(self):
  class Provider:
   def orient(self,payload):return {'rotation':90,'status':'confident','policy_version':'fixture-only'}
  with TestClient(create_app(str(self.path),ocr=Provider())) as client:
   self.assertEqual(client.post('/images/orient',content=b'fixture',headers={'Content-Type':'image/jpeg'}).status_code,400)
   response=client.post('/images/orient',content=b'fixture',headers={'Content-Type':'image/jpeg','X-Image-Processing-Consent':'yes'})
   self.assertEqual(response.status_code,200);self.assertEqual(response.json()['rotation'],90)
   self.assertNotIn('scan_token',response.json())
   self.assertNotIn('text',response.json())
 def test_orientation_upload_limits_and_unavailable_engine(self):
  class Provider:
   def read(self,payload):return {'text':'fixture'}
  with TestClient(create_app(str(self.path),ocr=Provider())) as client:
   headers={'Content-Type':'image/jpeg','X-Image-Processing-Consent':'yes'}
   self.assertEqual(client.post('/images/orient',content=b'x'*(8*1024*1024+1),headers=headers).status_code,413)
   self.assertEqual(client.post('/images/orient',content=b'',headers=headers).status_code,422)
   self.assertEqual(client.post('/images/orient',content=b'fixture',headers=headers).status_code,503)
 def test_food_image_review_excludes_advisories(self):
  class Provider:
   def read(self,payload):return {'text':'Ingredients: Carrier alias. May contain milk'}
  with TestClient(create_app(str(self.path),ocr=Provider())) as client:
   result=client.post('/scans/image',content=b'fixture',headers={'Content-Type':'image/jpeg','X-Image-Processing-Consent':'yes','X-Product-Context':'food'})
   self.assertEqual(result.status_code,201)
   self.assertEqual([t['text'] for t in result.json()['tokens']],['Carrier alias'])
 def test_additive_code_separators_preserve_code_identity(self):
  self.repo.import_document({'ingredients':[{'id':'code','name':'Code fixture','aliases':['E-330','INS-330']}]})
  for code in ['E330','E 330','INS330','INS 330']:
   self.assertEqual(match(parse_label(code)[0],self.repo)['ingredient']['id'],'code')
  self.assertEqual(match(parse_label('330')[0],self.repo)['match_status'],'unmatched')
 def test_parser_parentheses_optional_and_stops(self):
  tokens=parse_label('Ingredients: Water (Aqua/Eau), Blend (A, B); Glycerin 5%*; may contain: CI 123. Warnings: avoid eyes')
  self.assertEqual([t.text for t in tokens],['Water (Aqua/Eau)','Blend (A, B)','Glycerin','CI 123'])
  self.assertTrue(tokens[-1].optional)
  self.assertEqual([t.position for t in tokens],[0,1,2,3])
 def test_parser_hyphenation_cas_and_e_number(self):
  tokens=parse_label('Toco-\npherol, 56-81-5, E-330')
  self.assertEqual([t.text for t in tokens],['Tocopherol','56-81-5','E-330'])
 def test_unbalanced_brackets_requires_review(self):
  with self.assertRaises(ValueError):parse_label('Blend (A, B')
 def test_api_review_lookup_and_access_control(self):
  with TestClient(create_app(self.path)) as client:
   scan=client.post('/scans',json={'text':'Carrier alias, Mystery blend'}).json()
   url='/scans/'+scan['id']+'/confirm'
   self.assertEqual(client.post(url,json={'text':'Carrier alias'}).status_code,404)
   response=client.post(url,headers={'X-Scan-Token':scan['scan_token']},json={'text':'Carrier alias, Mystery blend','confirmations':[{'position':1,'confirmation_key':scan['match_preview'][1]['confirmation_key'],'ingredient_id':None}]})
   self.assertEqual(response.status_code,200)
   result=response.json()
   self.assertEqual(result['matched_count'],1)
   self.assertNotIn('score', result)
   self.assertNotIn('hazard', str(result))
   self.assertEqual(client.get('/ingredients/carrier').status_code,200)
   self.assertEqual(client.get('/ingredients/missing').status_code,404)
 def test_api_rejects_empty_and_extra_fields(self):
  with TestClient(create_app(self.path)) as client:
   self.assertEqual(client.post('/scans',json={'text':'   '}).status_code,422)
   self.assertEqual(client.post('/scans',json={'text':'Carrier','score':5}).status_code,422)
 def test_uncertain_ingredients_require_individual_decisions(self):
  with TestClient(create_app(self.path)) as client:
   text='Demo carrler, Mystery blend'
   scan=client.post('/scans',json={'text':text}).json()
   url='/scans/'+scan['id']+'/confirm';headers={'X-Scan-Token':scan['scan_token']}
   def send(choices):return client.post(url,headers=headers,json={'text':text,'confirmations':choices})
   self.assertEqual(send([]).status_code,409)
   choices=[{'position':0,'confirmation_key':scan['match_preview'][0]['confirmation_key'],'ingredient_id':'carrier'}]
   self.assertEqual(send(choices).json()['detail']['pending_positions'],[1])
   choices.append({'position':1,'confirmation_key':scan['match_preview'][1]['confirmation_key'],'ingredient_id':None})
   result=send(choices);self.assertEqual(result.status_code,200)
   tokens=result.json()['tokens'];self.assertEqual(result.json()['matched_count'],1)
   self.assertEqual(tokens[0]['match_method'],'user_confirmed');self.assertEqual(tokens[0]['text'],'Demo carrler')
   self.assertEqual(tokens[1]['confirmation_status'],'kept_unknown');self.assertIsNone(tokens[1]['ingredient'])
   self.assertTrue(all(t['match_probability'] is None for t in tokens))
 def test_confirmation_rejects_stale_duplicate_and_unoffered_choices(self):
  with TestClient(create_app(self.path)) as client:
   scan=client.post('/scans',json={'text':'Demo carrler'}).json()
   choice={'position':0,'confirmation_key':scan['match_preview'][0]['confirmation_key'],'ingredient_id':'carrier'}
   url='/scans/'+scan['id']+'/confirm';headers={'X-Scan-Token':scan['scan_token']}
   for choices in [[choice,choice],[choice|{'ingredient_id':'invented'}],[choice|{'position':199}],[choice|{'confirmation_key':'0'*64}]]:
    self.assertEqual(client.post(url,headers=headers,json={'text':scan['text'],'confirmations':choices}).status_code,422)
   self.assertEqual(client.post(url,headers=headers,json={'text':'Other typo','confirmations':[choice]}).status_code,422)
   self.assertEqual(client.post(url,headers=headers,json={'text':scan['text'],'product_context':'food','confirmations':[choice]}).status_code,422)
   other=client.post('/scans',json={'text':scan['text']}).json()
   self.assertNotEqual(other['match_preview'][0]['confirmation_key'],choice['confirmation_key'])
   self.assertEqual(client.post('/scans/'+other['id']+'/confirm',headers={'X-Scan-Token':other['scan_token']},json={'text':scan['text'],'confirmations':[choice]}).status_code,422)
 def test_low_ocr_exact_match_requires_confirmation_and_can_be_rejected(self):
  class LowOCR:
   def read(self,image):return {'text':'Carrier alias','ocr_confidence':0.4,'provider':'test-only'}
  with TestClient(create_app(self.path,LowOCR())) as client:
   scan=client.post('/scans/image',content=b'x',headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'}).json()
   token=scan['match_preview'][0];self.assertIn('low_ocr_quality',token['confirmation_reasons'])
   url='/scans/'+scan['id']+'/confirm';headers={'X-Scan-Token':scan['scan_token']}
   self.assertEqual(client.post(url,headers=headers,json={'text':scan['text']}).status_code,409)
   choice={'position':0,'confirmation_key':token['confirmation_key'],'ingredient_id':None}
   rejected=client.post(url,headers=headers,json={'text':scan['text'],'confirmations':[choice]}).json()
   self.assertEqual(rejected['matched_count'],0);self.assertIsNone(rejected['tokens'][0]['ingredient'])
   choice['ingredient_id']='carrier'
   accepted=client.post(url,headers=headers,json={'text':scan['text'],'confirmations':[choice]}).json()
   self.assertEqual(accepted['tokens'][0]['ocr_confidence'],0.4);self.assertEqual(accepted['tokens'][0]['match_method'],'user_confirmed')
 def test_ambiguous_alias_requires_explicit_identity(self):
  self.repo.import_document({'ingredients':[{'id':'other','name':'Other carrier','aliases':['Carrier alias']}]})
  with TestClient(create_app(self.path)) as client:
   scan=client.post('/scans',json={'text':'Carrier alias'}).json();token=scan['match_preview'][0]
   self.assertIn('ambiguous_name',token['confirmation_reasons']);self.assertEqual({t['id'] for t in token['confirmation_options']},{'carrier','other'})
   result=client.post('/scans/'+scan['id']+'/confirm',headers={'X-Scan-Token':scan['scan_token']},json={'text':scan['text'],'confirmations':[{'position':0,'confirmation_key':token['confirmation_key'],'ingredient_id':'other'}]})
   self.assertEqual(result.status_code,200);self.assertEqual(result.json()['tokens'][0]['ingredient']['id'],'other')
 def test_food_nested_blends_preserve_parent_paths_and_leaf_order(self):
  tokens=parse_label('Ingredients: Flour, Seasoning (Salt, Spices [Cumin, Turmeric], Sugar), Palm oil. Contains: wheat',context='food')
  self.assertEqual([t.text for t in tokens],['Flour','Salt','Cumin','Turmeric','Sugar','Palm oil'])
  self.assertEqual(tokens[2].to_dict()['parent_path'],['Seasoning','Spices'])
  self.assertEqual(tokens[4].to_dict()['parent_path'],['Seasoning'])
  self.assertEqual([t.position for t in tokens],list(range(6)))
  self.assertEqual(parse_label('Water (Aqua/Eau)',context='food')[0].parent_path,())
  self.assertEqual(len(parse_label('Blend (Salt, Sugar)',context='cosmetics')),1)
 def test_food_groups_are_bounded_and_malformed_input_requires_correction(self):
  for text in ['Blend (Salt, Sugar)', 'Blend [Salt; Sugar]']:
   self.assertEqual([t.text for t in parse_label(text,context='food')],['Salt','Sugar'])
  with self.assertRaises(ValueError):parse_label('Blend ('*13+'Salt, Sugar'+')'*13,context='food')
  with self.assertRaises(ValueError):parse_label('Blend ('+','.join(['Salt']*201)+')',context='food')
  with self.assertRaises(ValueError):parse_label('Blend (Salt, Sugar]',context='food')
 def test_shared_capabilities_and_limits_survive_new_instances(self):
  from kyp.operations import SharedOperations
  from fastapi import HTTPException
  a=SharedOperations(self.repo,'x'*40);identity,capability=a.create(0.4)
  b=SharedOperations(self.repo,'x'*40)
  self.assertEqual(b.authorize(identity,capability),0.4)
  with self.assertRaises(HTTPException):b.authorize(identity,'wrong')
  self.assertTrue(a.allow('client','image',2));self.assertTrue(b.allow('client','image',2));self.assertFalse(a.allow('client','image',2))
  self.assertTrue(b.allow('other','image',2))
  with patch('kyp.operations.time.time',return_value=10**20):
   with self.assertRaises(HTTPException):b.authorize(identity,capability)
  with self.repo.connection() as db:
   saved=db.execute('SELECT capability_hash FROM scan_sessions WHERE id=?',(identity,)).fetchone()['capability_hash']
  self.assertNotEqual(saved,capability)
 def test_public_mode_fails_closed_without_configuration(self):
  with patch.dict('os.environ',{'KYP_PUBLIC_MODE':'1','KYP_PUBLIC_ORIGIN':'http://localhost','KYP_OPERATION_SECRET':''}):
   with self.assertRaises(ValueError):create_app(self.path)
 def test_public_api_cross_worker_session_https_and_rate_response(self):
  if not self.repo.postgres:self.skipTest('Public mode deliberately requires PostgreSQL')
  config={'KYP_PUBLIC_MODE':'1','KYP_PUBLIC_ORIGIN':'https://kyp.example.test','KYP_OPERATION_SECRET':'test-secret-'*4}
  with patch.dict('os.environ',config):
   app1=create_app(self.path);app2=create_app(self.path)
   with TestClient(app1,base_url='https://kyp.example.test') as first, TestClient(app2,base_url='https://kyp.example.test') as second:
    scan=first.post('/scans',json={'text':'Carrier alias'}).json()
    result=second.post('/scans/'+scan['id']+'/confirm',headers={'X-Scan-Token':scan['scan_token']},json={'text':'Carrier alias'})
    self.assertEqual(result.status_code,200);self.assertEqual(result.headers['cache-control'],'no-store')
    self.assertIn('max-age',result.headers['strict-transport-security'])
    self.assertEqual(second.get('http://kyp.example.test/health').status_code,400)
    self.assertEqual(second.get('https://evil.example/health').status_code,400)
    with patch.object(app2.state.operations,'allow',return_value=False):
     limited=second.post('/scans',json={'text':'Carrier alias'})
    self.assertEqual(limited.status_code,429);self.assertEqual(limited.headers['retry-after'],'60')
 def test_compound_raw_leaf_preserves_percentage_without_affecting_match_text(self):
  tokens=parse_label('Seasoning (5%) (Salt 10%, Sugar)',context='food')
  self.assertEqual(tokens[0].raw,'Salt 10%');self.assertEqual(tokens[0].text,'Salt')
  self.assertEqual(tokens[0].parent_path,('Seasoning',))
 def test_comma_recovery_keeps_original_and_requires_every_entry(self):
  raw='Ingredients: Carrier alias), Demo no description, Mystery blend'
  class BrokenOCR:
   def read(self,image):return {'text':raw,'ocr_confidence':0.4,'provider':'fixture'}
  with TestClient(create_app(self.path,BrokenOCR())) as client:
   scan=client.post('/scans/image',content=b'x',headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'}).json()
   self.assertEqual(scan['tokens'],[]);self.assertTrue(scan['parse_warning'])
   review='/scans/'+scan['id']+'/review';body={'text':raw,'parsing_mode':'comma_review'}
   self.assertEqual(client.post(review,json=body).status_code,404)
   recovered=client.post(review,headers={'X-Scan-Token':scan['scan_token']},json=body)
   self.assertEqual(recovered.status_code,201);recovered=recovered.json()
   self.assertEqual(recovered['text'],raw);self.assertIsNone(recovered['parse_warning'])
   self.assertEqual(recovered['parsing_mode'],'comma_review')
   self.assertEqual([t['text'] for t in recovered['tokens']],['Carrier alias','Demo no description','Mystery blend'])
   self.assertEqual(recovered['tokens'][0]['raw'],'Carrier alias)')
   self.assertTrue(all(t['ocr_confidence']==0.4 for t in recovered['tokens']))
   self.assertTrue(all('uncertain_structure' in t['confirmation_reasons'] for t in recovered['match_preview']))
   url='/scans/'+recovered['id']+'/confirm';headers={'X-Scan-Token':recovered['scan_token']}
   self.assertEqual(client.post(url,headers=headers,json=body).status_code,409)
   choices=[{'position':t['position'],'confirmation_key':t['confirmation_key'],'ingredient_id':t['ingredient']['id'] if t['ingredient'] else None} for t in recovered['match_preview']]
   self.assertEqual(client.post(url,headers=headers,json=body|{'confirmations':choices[:-1]}).status_code,409)
   result=client.post(url,headers=headers,json=body|{'confirmations':choices})
   self.assertEqual(result.status_code,200);self.assertEqual(result.json()['matched_count'],2)
 def test_comma_recovery_is_explicit_bounded_and_bound_to_decisions(self):
  with self.assertRaises(ValueError):parse_label('Carrier alias), Mystery')
  tokens=parse_label('Blend (Carrier alias, Mystery]',comma_review=True)
  self.assertEqual(len(tokens),2);self.assertTrue(all(t.structure_uncertain for t in tokens));self.assertTrue(all(t.parent_path==() for t in tokens))
  with self.assertRaises(ValueError):parse_label(','.join(['Salt']*201),comma_review=True)
  with TestClient(create_app(self.path)) as client:
   scan=client.post('/scans',json={'text':'Carrier alias','parsing_mode':'comma_review'}).json()
   choice={'position':0,'confirmation_key':scan['match_preview'][0]['confirmation_key'],'ingredient_id':'carrier'}
   result=client.post('/scans/'+scan['id']+'/confirm',headers={'X-Scan-Token':scan['scan_token']},json={'text':'Carrier alias','confirmations':[choice]})
   self.assertEqual(result.status_code,422)
   bypass=client.post('/scans/'+scan['id']+'/confirm',headers={'X-Scan-Token':scan['scan_token']},json={'text':'Carrier alias'})
   self.assertEqual(bypass.status_code,422)
   self.assertEqual(client.post('/scans',json={'text':'Carrier alias','parsing_mode':'guess'}).status_code,422)
 def test_scan_expiry(self):
  with TestClient(create_app(self.path)) as client:
   scan=client.post('/scans',json={'text':'Carrier alias'}).json()
   with patch('kyp.api.time.monotonic', return_value=10**20):
    response=client.post('/scans/'+scan['id']+'/confirm',headers={'X-Scan-Token':scan['scan_token']},json={'text':'Carrier alias'})
   self.assertEqual(response.status_code,404)
 def test_image_consent_and_injected_ocr(self):
  class FakeOCR:
   def read(self,image):
    return {'text':'Carrier alias','ocr_confidence':0.4,'provider':'test-only'}
  with TestClient(create_app(self.path,FakeOCR())) as client:
   self.assertEqual(client.post('/scans/image',content=b'fixture',headers={'Content-Type':'image/png'}).status_code,400)
   result=client.post('/scans/image',content=b'fixture',headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'})
   self.assertEqual(result.status_code,201)
   self.assertTrue(result.json()['review_required'])
   self.assertEqual(result.json()['tokens'][0]['ocr_confidence'],0.4)
 def test_imperfect_ocr_is_reviewable_but_cannot_be_confirmed(self):
  raw='Ingredients: Mixed spices (Cumin, Coriander, Salt\nNutrition Information (Approx. Values) Energy 165 kcal'
  class ImperfectOCR:
   def read(self,image):return {'text':raw,'ocr_confidence':0.3,'provider':'test-only'}
  with TestClient(create_app(self.path,ImperfectOCR())) as client:
   response=client.post('/scans/image',content=b'fixture',headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'})
   self.assertEqual(response.status_code,201)
   scan=response.json();self.assertEqual(scan['text'],raw);self.assertEqual(scan['tokens'],[])
   self.assertIn('Unbalanced brackets',scan['parse_warning'])
   url='/scans/'+scan['id']+'/confirm';headers={'X-Scan-Token':scan['scan_token']}
   self.assertEqual(client.post(url,json={'text':raw},headers=headers).status_code,422)
   corrected=client.post('/scans',json={'text':'Salt, Sugar'}).json()
   choices=[{'position':t['position'],'confirmation_key':t['confirmation_key'],'ingredient_id':None} for t in corrected['match_preview']]
   fixed=client.post('/scans/'+corrected['id']+'/confirm',json={'text':'Salt, Sugar','confirmations':choices},headers={'X-Scan-Token':corrected['scan_token']})
   self.assertEqual(fixed.status_code,200)
   self.assertTrue(all(t['match_status']=='unmatched' for t in fixed.json()['tokens']))
 def test_missing_ingredient_heading_warns_without_discarding_text(self):
  class NoHeadingOCR:
   def read(self,image):return {'text':'Salt, Sugar','provider':'test-only'}
  with TestClient(create_app(self.path,NoHeadingOCR())) as client:
   response=client.post('/scans/image',content=b'fixture',headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'})
   scan=response.json();self.assertEqual(scan['text'],'Salt, Sugar')
   self.assertEqual(len(scan['tokens']),2);self.assertIn('Ingredient heading not detected',scan['review_warning'])
 def test_food_packaging_sections_are_excluded(self):
  for boundary in ['Nutrition Information (Approx. Values)','Nutritional facts','How to use','Manufactured by','Spice content above 25%']:
   tokens=parse_label('INGREDIENTS: Salt, Sugar. '+boundary+' unrelated text (')
   self.assertEqual([t.text for t in tokens],['Salt','Sugar'])
  self.assertEqual(parse_label('Nutritional yeast, Salt')[0].text,'Nutritional yeast')
 def test_ocr_unavailable_honest(self):
  with patch('kyp.ocr.shutil.which',return_value=None):
   with self.assertRaises(OCRUnavailable):TesseractOCR().read(b'not-an-image')
 def test_api_ocr_failure_and_upload_limits(self):
  class MissingOCR:
   def read(self,image):raise OCRUnavailable('Engine unavailable')
  with TestClient(create_app(self.path,MissingOCR())) as client:
   headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'}
   self.assertEqual(client.post('/scans/image',content=b'x',headers=headers).status_code,503)
   self.assertEqual(client.post('/scans/image',content=b'x'*(8*1024*1024+1),headers=headers).status_code,413)
   self.assertEqual(client.post('/scans/image',content=b'',headers=headers).status_code,422)

class OCRAdapterTests(unittest.TestCase):
 def test_optional_ocr_engine_selection_is_explicit(self):
  from kyp.ocr import default_provider,TesseractJSOCR
  with patch.dict('os.environ',{'KYP_OCR_ENGINE':'tesseractjs'}):self.assertIsInstance(default_provider(),TesseractJSOCR)
  with patch.dict('os.environ',{'KYP_OCR_ENGINE':'rapidocr'}),patch('kyp.ocr_experiments.RapidOCRExperiment') as factory:
   self.assertIs(default_provider(),factory.return_value)
  with patch.dict('os.environ',{'KYP_OCR_ENGINE':'invalid'}):
   with self.assertRaises(ValueError):default_provider()

 def test_transient_image_cleanup_and_tsv_confidence(self):
  from PIL import Image
  from types import SimpleNamespace
  image=io.BytesIO();Image.new('RGB',(20,20),'white').save(image,format='PNG')
  seen=[]
  def run(command,**kwargs):
   image_path=Path(command[1]);self.assertTrue(image_path.exists());seen.append(image_path)
   tsv='block_num\tpar_num\tline_num\tconf\ttext\n1\t1\t1\t91\tCarrier\n1\t1\t1\t42\talias\n'
   return SimpleNamespace(returncode=0,stdout=tsv.encode())
  with patch('kyp.ocr.shutil.which',return_value='test-engine'),patch('kyp.ocr.subprocess.run',side_effect=run):
   result=TesseractOCR().read(image.getvalue())
  self.assertEqual(result['text'],'Carrier alias')
  self.assertEqual(result['ocr_confidence'],0.42)
  self.assertFalse(seen[0].exists())
 def test_invalid_image_rejected_when_engine_available(self):
  with patch('kyp.ocr.shutil.which',return_value='test-engine'):
   with self.assertRaises(ValueError):TesseractOCR().read(b'invalid')

if __name__=='__main__':unittest.main()
