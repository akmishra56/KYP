"""Isolated evaluation worker; local paths only, no production engine change."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kyp.ocr_experiments import RapidOCRExperiment
engine=RapidOCRExperiment()
inputs=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));results=[]
for row in inputs:
 try:results.append({'case':row['case'],**engine.read(Path(row['path']).read_bytes())})
 except Exception as exc:results.append({'case':row['case'],'error':str(exc)})
Path(sys.argv[2]).write_text(json.dumps(results,indent=2),encoding='utf-8')
