"""Recompute pooled load summaries from public numeric observations."""
import argparse
import json
from pathlib import Path
import numpy as np

def recompute(root):
    observed=json.loads((root/"evidence/measurements.json").read_text(encoding="utf-8"))
    archived=json.loads((root/"evidence/load_summary.json").read_text(encoding="utf-8"))
    calculated=[]
    for name,data in observed["backends"].items():
        for concurrency in (1,4,8):
            waves=[w for w in data["waves"] if w["sessions"]==concurrency]
            clients=[c for w in waves for c in w["clients"]]
            rtts=[x for c in clients for x in c["rtt_ms"]]
            events=[x for c in clients for x in c["event_bearing_rtt_ms"]]
            calculated.append({
                "backend":name,"concurrent_sessions":concurrency,"waves":len(waves),
                "connections":sum(w["sessions"] for w in waves),"requests":len(rtts),
                "event_bearing_requests":len(events),
                "request_rtt_p50_ms":float(np.percentile(rtts,50)),
                "request_rtt_p95_ms":float(np.percentile(rtts,95)),
                "event_bearing_rtt_p95_ms":float(np.percentile(events,95)),
                "wave_throughput_median_frames_s":float(np.median([w["aggregate_frames_per_second"] for w in waves])),
                "process_tree_sampled_peak_rss_mib":max(s["rss_bytes"] for w in waves for s in w["resources"])/2**20
            })
    assert len(calculated)==len(archived)
    for a,b in zip(calculated,archived):
        assert a.keys()==b.keys()
        for key,value in a.items():
            if isinstance(value,float):
                assert abs(value-b[key])<=1e-9,(key,value,b[key])
            else:
                assert value==b[key],(key,value,b[key])
    return calculated

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(__file__).resolve().parent)
    args=p.parse_args()
    print(json.dumps({"status":"passed","load_summary":recompute(args.root)},indent=2))
