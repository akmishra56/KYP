import tempfile,unittest
from pathlib import Path
from kyp.evaluate_ocr import validate_manifest,evaluate
class EvaluationTests(unittest.TestCase):
 def test_duplicate_images_and_product_leakage_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   base=Path(folder);(base/'a.png').write_bytes(b'a');(base/'b.png').write_bytes(b'b')
   a={'image':'a.png','permission':'owner supplied','reviewed_by':'fixture','expected_tokens':['Salt'],'context':'food','product_id':'one','split':'baseline'}
   self.assertEqual(len(validate_manifest([a],base)),1)
   for b in [a|{'product_id':'two'},a|{'image':'b.png','split':'held_out'},a|{'image':'../escape.png'},a|{'reviewed_by':''}]:
    with self.assertRaises(ValueError):validate_manifest([a,b],base)
 def test_engine_metrics_preserve_compound_leaf_truth(self):
  class Fake:
   def read(self,image):return {'text':'Seasoning (Salt, Sugar), Mystery blend'}
  with tempfile.TemporaryDirectory() as folder:
   base=Path(folder);(base/'a.png').write_bytes(b'fixture')
   records=[{'image':'a.png','context':'food','split':'held_out','expected_tokens':['Salt','Sugar','Mystery blend'],'tags':['glare']}]
   result=evaluate(records,base,Fake(),'fixture')
   self.assertEqual(result['overall']['recall'],1);self.assertEqual(result['condition:glare']['precision'],1)

class CalibrationTests(unittest.TestCase):
 def test_isotonic_pooling_is_monotone_and_ties_are_grouped(self):
  from kyp.calibration import fit_isotonic,predict,metrics
  blocks=fit_isotonic([(0.2,0),(0.4,1),(0.4,0),(0.7,0),(0.9,1)])
  probs=[predict(blocks,x/10) for x in range(11)]
  self.assertEqual(probs,sorted(probs));self.assertTrue(all(0<=p<=1 for p in probs))
  report=metrics(blocks,[(0.2,0),(0.9,1)]);self.assertEqual(report['brier'],0)
  self.assertEqual(sum(b['samples'] for b in report['reliability_bins']),2)
 def test_synthetic_examples_cannot_be_calibration_evidence(self):
  from kyp.calibration import experiment
  with self.assertRaises(ValueError):experiment([{'is_real':False}],None)
