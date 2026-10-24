import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kyp.food import build_document, add_code_aliases, add_staples, add_oils, review_development
from kyp.food_enrichment import add_enrichment, fetch_record, validate_record, POLICY
from kyp.repository import Repository
from kyp.parser import parse_label
from kyp.matcher import match_many

FIXTURES = Path(__file__).parent/'fixtures'
RECORDED = FIXTURES/'food-enrichment'
LABEL = "Ingredients: Mixed spices (35.6%) (Roasted spice powder (17.8%) (Cumin, Coriander, Turmeric, Aniseed, Black pepper, Fenugreek, Ginger, Clove, Green cardamom powder, Nutmeg), Red chilli powder, Dehydrated onion, Dried garlic, Capsicum extract, Coriander extract, Cumin extract), Iodized salt, Sugar, Starch, Flavour enhancer (635), Thickener (508), Acidity regulator (330), Palm oil, Natural flavouring substance, Mineral and Vitamin."

def document():
    snapshot=json.loads((RECORDED/'fda-food.json').read_text(encoding='utf8'))
    doc,_=build_document(snapshot)
    identities=json.loads((FIXTURES/'food-code-identities.json').read_text(encoding='utf8'))
    def recorded(url,*args):
        return {'url':url,'retrieved_at':snapshot['retrieved_at'],'content':json.dumps(identities[url.rstrip('/').rsplit('/',1)[-1]],sort_keys=True)}
    with patch('kyp.food.snapshot',side_effect=recorded): add_code_aliases(doc,Path('unused'))
    add_staples(doc,FIXTURES/'food-standards')
    add_oils(doc,RECORDED)
    records={key:json.loads((RECORDED/(key+'.json')).read_text(encoding='utf8')) for key in POLICY['sources']}
    return add_enrichment(doc,Path('unused'),records=records)

class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.repo=Repository(Path(self.folder.name)/'catalog.sqlite3')
        self.doc=document();self.repo.import_document(self.doc)
    def test_maggi_corrected_label_resolves_known_leaves_and_keeps_unspecified_term(self):
        review_development(self.repo,self.doc)
        results=match_many(parse_label(LABEL,context='food'),self.repo,context='food')
        self.assertEqual(len(results),25)
        unknown=[r['text'] for r in results if r['match_status']!='matched']
        self.assertEqual(unknown,['Mineral and Vitamin'])
        self.assertEqual(sum(r['ingredient'] is not None and r['ingredient']['description'] is not None for r in results),23)
        self.assertEqual(results[0]['parent_path'],['Mixed spices','Roasted spice powder'])
        palm=next(r for r in results if r['text']=='Palm oil')
        self.assertIsNone(palm['ingredient']['description'])
    def test_import_stays_draft_until_explicit_review(self):
        self.assertIsNone(self.repo.ingredient('food-dried-onion','food')['description'])
        self.assertTrue(self.repo.pending()['descriptions'])
    def test_reimport_preserves_counts_decisions_and_evidence(self):
        review_development(self.repo,self.doc)
        before=self.repo.stats(); approved=self.repo.pending('approved')
        self.repo.import_document(document());review_development(self.repo,document())
        self.assertEqual(before,self.repo.stats())
        self.assertEqual(approved,self.repo.pending('approved'))
        item=self.repo.ingredient('food-dried-onion','food')
        self.assertIn('label_alias_evidence',item['description']['provenance'])
    def test_rejected_source_is_not_reapproved(self):
        review_development(self.repo,self.doc)
        source=next(s for s in self.doc['sources'] if s['id'].startswith('food-evidence-spice_definitions-'))
        self.repo.reject_source(source['id'],'independent reviewer','Needs further review')
        self.repo.import_document(document());review_development(self.repo,document())
        self.assertIsNone(self.repo.ingredient('food-dried-onion','food')['description'])
        self.assertEqual(len(self.repo.review_history('source',source['id'])),2)
    def test_unknown_codes_typos_and_different_forms_are_not_silently_mapped(self):
        labels='635, Flavour enhancer (634), Thickener (330), lodized salt, black cardamom powder, coriander oil, mystery spice'
        results=match_many(parse_label(labels,context='food'),self.repo,context='food')
        self.assertTrue(all(r['match_status']=='unmatched' and r['confirmation_required'] for r in results))
        queries='Flavour enhancer (INS 635), Flavor enhancer (E635), Thickener (E 508), Acidity regulator (330)'
        results=match_many(parse_label(queries,context='food'),self.repo,context='food')
        self.assertTrue(all(r['match_status']=='matched' for r in results))
    def test_dried_forms_and_extracts_remain_distinct(self):
        results=match_many(parse_label('onion powder, dehydrated onion, garlic powder, dried garlic, coriander, coriander extract',context='food'),self.repo,context='food')
        ids=[r['ingredient']['id'] for r in results]
        self.assertEqual(len(set(ids)),6)
        cosmetics=match_many(parse_label('dried onion, Flavour enhancer (635)'),self.repo,context='cosmetics')
        self.assertTrue(all(r['match_status']=='unmatched' for r in cosmetics))
    def test_changed_or_missing_evidence_and_nonallowlisted_origin_fail_closed(self):
        spec=POLICY['sources']['e635']
        record=json.loads((RECORDED/'e635.json').read_text(encoding='utf8'))
        record['content']+=' tampered'
        with self.assertRaises(ValueError):validate_record(record,spec)
        changed=copy.deepcopy(spec);changed['required']=['not supported']
        record=json.loads((RECORDED/'e635.json').read_text(encoding='utf8'))
        with self.assertRaises(ValueError):validate_record(record,changed)
        changed['url']='https://untrusted.example/ingredient'
        with self.assertRaises(ValueError):fetch_record(changed,Path(self.folder.name))
