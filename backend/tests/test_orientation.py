import io
import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from kyp.orientation import choose_orientation, POLICY
from kyp.ocr import TesseractJSOCR, OCRUnavailable

class OrientationTests(unittest.TestCase):
 def test_shared_decision_cases(self):
  cases=json.loads(Path(__file__).with_name('fixtures').joinpath('orientation-cases.json').read_text())
  for case in cases:
   with self.subTest(case=case['name']):
    result=choose_orientation([{'rotation':angle,'text':text} for angle,text in zip((0,90,180,270),case['texts'])])
    self.assertEqual((result['rotation'],result['status']),(case['rotation'],case['status']))
 def test_native_and_server_policies_match(self):
  native=Path(__file__).resolve().parents[2]/'mobile/src/orientation-policy.json'
  self.assertEqual(POLICY,json.loads(native.read_text()))
 def test_missing_or_duplicate_candidates_are_rejected(self):
  with self.assertRaises(ValueError):choose_orientation([{'rotation':0,'text':'ingredients salt water sugar'}]*4)
 def test_four_rotations_cleanup_and_clockwise_dimensions(self):
  buffer=io.BytesIO();Image.new('RGB',(120,80),'white').save(buffer,format='PNG');paths=[]
  def run(command,**kwargs):
   paths.extend(Path(path) for path in command[2:])
   sizes=[]
   for path in paths:
    with Image.open(path) as image:sizes.append(image.size)
   self.assertEqual(sizes,[(120,80),(80,120),(120,80),(80,120)])
   return SimpleNamespace(returncode=0,stdout=json.dumps([{'text':'bad'},{'text':'Ingredients water salt sugar'},{'text':''},{'text':''}]).encode())
  with patch('kyp.ocr.shutil.which',return_value='test-node'),patch('kyp.ocr.subprocess.run',side_effect=run):result=TesseractJSOCR().orient(buffer.getvalue())
  self.assertEqual(result['rotation'],90)
  self.assertTrue(all(not path.exists() for path in paths))
 def test_auto_orientation_timeout_cleans_images(self):
  buffer=io.BytesIO();Image.new('RGB',(20,20),'white').save(buffer,format='PNG');paths=[]
  def timeout(command,**kwargs):
   paths.extend(Path(path) for path in command[2:]);raise subprocess.TimeoutExpired(command,45)
  with patch('kyp.ocr.shutil.which',return_value='test-node'),patch('kyp.ocr.subprocess.run',side_effect=timeout),self.assertRaises(OCRUnavailable):TesseractJSOCR().orient(buffer.getvalue())
  self.assertTrue(all(not path.exists() for path in paths))
