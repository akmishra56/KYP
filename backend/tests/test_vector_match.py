import unittest
from kyp.matcher import normalize, POLICY
from kyp.vector_match import CosineIndex

class VectorTests(unittest.TestCase):
 def test_sparse_cosine_exact_and_out_of_vocabulary_penalty(self):
  index=CosineIndex([{'id':'salt','name':'Salt','aliases':[]},{'id':'sugar','name':'Sugar','aliases':[]}],normalize,POLICY)
  self.assertEqual(index.rank('salt')[0]['similarity'],1)
  changed=index.rank('salt qqqqq')[0]
  self.assertEqual(changed['id'],'salt');self.assertLess(changed['similarity'],1)
  self.assertEqual(index.rank('zzzzzz'),[])
 def test_alias_variants_deduplicate_identity_candidates(self):
  index=CosineIndex([{'id':'one','name':'Sodium chloride','aliases':['Salt','Common salt']},{'id':'two','name':'Sugar','aliases':[]}],normalize,POLICY)
  results=index.rank('common salt')
  self.assertEqual(results[0]['id'],'one');self.assertEqual(results[0]['similarity'],1)
  self.assertEqual(len([row for row in results if row['id']=='one']),1)
 def test_ties_are_stable_and_do_not_imply_probability(self):
  index=CosineIndex([{'id':'b','name':'Salt','aliases':[]},{'id':'a','name':'Salt','aliases':[]}],normalize,POLICY)
  result=index.rank('salt')
  self.assertEqual([row['id'] for row in result],['a','b'])
  self.assertTrue(all(row['match_probability'] is None for row in result))
