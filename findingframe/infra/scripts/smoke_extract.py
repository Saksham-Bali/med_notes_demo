import sys, os, json, time
from pathlib import Path
ENGINE = Path(__file__).resolve().parents[3] / "tmc"
sys.path.insert(0, str(ENGINE))
os.chdir(ENGINE)  # engine resolves config/.env relative to cwd
from extraction.finding_frame_extractor import FindingFrameExtractor
rep = (ENGINE / "data" / "sample_report.md").read_text()
print(f"report chars: {len(rep)}", flush=True)
t0 = time.time()
ex = FindingFrameExtractor(domain="radiology", use_cache=False)
res = ex.extract(rep, chart_date="2026-01-01", study_type="RR", source_report_id="report_1")
d = res.to_dict()
print(f"OK in {time.time()-t0:.1f}s | frames={len(d.get('frames',[]))} | conf={d.get('overall_confidence')}", flush=True)
for f in d.get("frames", [])[:6]:
    print(f"  - {f.get('finding_type')} | {f.get('anatomy')}/{f.get('laterality')} | {f.get('assertion')} | evid='{(f.get('evidence_text') or '')[:60]}'")
