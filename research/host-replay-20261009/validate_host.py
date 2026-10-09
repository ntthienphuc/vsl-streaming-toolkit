"""Private owner-model host evidence. No source-framework or accuracy claim."""
import argparse
import asyncio
from collections import Counter
import csv
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'dependencies'))
import numpy as np
import psutil
import websockets
import vsl_streaming
from vsl_streaming.bundle import register_onnx
from vsl_streaming.config import ServerConfig
from vsl_streaming.core import StreamConfig, StreamSession
from vsl_streaming.protocol import MessageProcessor
from vsl_streaming.runtime import ONNXRecognizer, external_tensor

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument("--release-source", required=True, type=Path, help="Git checkout containing the frozen v0.1.2 commit")
PARSER.add_argument("--owner-root", required=True, type=Path, help="Authorized owner server checkout; imported as trusted Python")
PARSER.add_argument("--trace-dir", required=True, type=Path, help="Authorized run*_keypoints_15fps.json files")
PARSER.add_argument("--out-root", required=True, type=Path, help="Private output directory; contains bundles and owner paths")
PARSER.add_argument("--check-only", action="store_true", help="Check installed source and input inventory without inference or timing")
ARGS = PARSER.parse_args()
REPO = ARGS.release_source.resolve()
OWNER = ARGS.owner_root.resolve()
TRACES = ARGS.trace_dir.resolve()
COMMIT = "f2410017a5273ecf3158f7971f31c4b484d2e9dd"

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(p, value):
    Path(p).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')

def dist(values):
    return {'n': len(values), 'p50_ms': float(np.percentile(values, 50)), 'p95_ms': float(np.percentile(values, 95)), 'max_ms': float(max(values))} if values else {'n': 0}

def clean(events):
    return [{k: v for k, v in e.items() if k != 'inference_ms'} for e in events]

def segmentize(frames, mode='signing_space', chunk=31):
    session = StreamSession(StreamConfig(mode=mode))
    events = []
    for start in range(0, len(frames), chunk):
        events.extend(session.push_batch(frames[start:start + chunk]))
    events.extend(session.flush())
    return events, session.status()

def objects(frames):
    def component(value):
        return None if value is None else SimpleNamespace(landmark=[SimpleNamespace(**p) for p in value])
    return [SimpleNamespace(**{k: component(f.get(k)) for k in ('pose_landmarks', 'left_hand_landmarks', 'right_hand_landmarks')}) for f in frames]

def offline(model, frames, chunk=31):
    processor, events = MessageProcessor(model), []
    for offset in range(0, len(frames), chunk):
        r = processor.process({'type': 'frames', 'request_id': str(offset), 'frames': frames[offset:offset+chunk], 'flush': offset+chunk >= len(frames)})
        assert r['type'] == 'result', r
        events.extend(r['events'])
    return clean(events)

def health(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as r:
        return json.load(r)

def resource(child):
    processes = [child] + child.children(recursive=True)
    alive = [p for p in processes if p.is_running()]
    return {'rss_bytes': sum(p.memory_info().rss for p in alive), 'processes': len(alive), 'threads': sum(p.num_threads() for p in alive), 'handles': sum(p.num_handles() for p in alive), 'cpu_seconds': sum(p.cpu_times().user + p.cpu_times().system for p in alive)}

async def client(port, frames, chunk=31):
    rtts, bearing, idle, events, sizes = [], [], [], [], []
    async with websockets.connect(f'ws://127.0.0.1:{port}/v1/stream', max_size=2_000_000) as ws:
        ready = json.loads(await asyncio.wait_for(ws.recv(), 30))
        for start in range(0, len(frames), chunk):
            text = json.dumps({'type': 'frames', 'request_id': str(start), 'frames': frames[start:start+chunk], 'flush': start+chunk >= len(frames)}, separators=(',', ':'))
            sizes.append(len(text.encode('utf-8')))
            t = time.perf_counter()
            await ws.send(text)
            response = json.loads(await asyncio.wait_for(ws.recv(), 60))
            dt = (time.perf_counter()-t)*1000
            assert response['type'] == 'result', response
            rtts.append(dt)
            (bearing if response['events'] else idle).append(dt)
            events.extend(response['events'])
    return {'session_id': ready['session_id'], 'events': clean(events), 'rtt_ms': rtts, 'event_bearing_rtt_ms': bearing, 'idle_rtt_ms': idle, 'payload_bytes': sum(sizes), 'request_count': len(sizes)}

async def wave(port, frames, n, child):
    sampled, done = [], asyncio.Event()
    async def sample():
        while not done.is_set():
            sampled.append(resource(child))
            await asyncio.sleep(.1)
    observer = asyncio.create_task(sample())
    before = resource(child)
    t = time.perf_counter()
    try:
        results = await asyncio.gather(*(client(port, frames) for _ in range(n)))
        elapsed = time.perf_counter()-t
    finally:
        done.set()
        await observer
    return results, elapsed, sampled, before, resource(child)

async def lifecycle(port, frames, expected):
    checks = []
    async with websockets.connect(f'ws://127.0.0.1:{port}/v1/stream') as ws:
        await ws.recv()
        async def send(value):
            await ws.send(json.dumps(value))
            return json.loads(await ws.recv())
        message = {'type': 'frames', 'request_id': 'retry', 'frames': frames[:31]}
        first, second = await send(message), await send(message)
        replayed = second.pop('replayed', False)
        first.pop('replayed', None)
        checks.append({'name': 'exact_retry', 'pass': replayed and first == second})
        conflict = await send(dict(message, frames=frames[:30]))
        checks.append({'name': 'conflicting_retry', 'pass': conflict['error']['code'] == 'request_id_conflict'})
        status1 = await send({'type': 'status', 'request_id': 's1'})
        bad = await send({'type': 'frames', 'request_id': 'invalid', 'frames': [dict(frames[31], seq=-1)]})
        status2 = await send({'type': 'status', 'request_id': 's2'})
        checks.append({'name': 'invalid_frame_rejected', 'pass': bad['type'] == 'error', 'response': bad})
        checks.append({'name': 'invalid_frame_state_atomic', 'pass': status1['state'] == status2['state']})
        await ws.send('{"type":"status","type":"flush","request_id":"dup"}')
        malformed = json.loads(await ws.recv())
        checks.append({'name': 'duplicate_json_key', 'pass': malformed['error']['code'] == 'invalid_json'})
        reset = await send({'type': 'reset', 'request_id': 'reset'})
        checks.append({'name': 'reset', 'pass': reset['type'] == 'result'})
        events = []
        for i in range(0, len(frames), 31):
            r = await send({'type': 'frames', 'request_id': f'after-reset-{i}', 'frames': frames[i:i+31], 'flush': i+31>=len(frames)})
            events.extend(r['events'])
        checks.append({'name': 'reset_replay_equivalence', 'pass': clean(events) == expected})
    reconnect = await client(port, frames, chunk=19)
    checks.append({'name': 'reconnect_and_chunk19_equivalence', 'pass': reconnect['events'] == expected})
    return checks

def network(bundle, collections, expected, backend, out):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    env = dict(os.environ)
    env['PYTHONPATH'] = str(HERE)
    env['PYTHONNOUSERSITE'] = '1'
    rows = []
    with (out / f'{backend}_server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'vsl_streaming.cli', 'serve', '--bundle', str(bundle), '--port', str(port)], cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
        child = psutil.Process(process.pid)
        try:
            for _ in range(400):
                if process.poll() is not None: raise RuntimeError('server exited')
                try:
                    if health(port)['status'] == 'ready': break
                except OSError: time.sleep(.1)
            else: raise RuntimeError('server startup timeout')
            assert health(port)['version'] == '0.1.2'
            lifecycle_checks = asyncio.run(lifecycle(port, collections[0], expected[0]))
            assert all(c['pass'] for c in lifecycle_checks), lifecycle_checks
            asyncio.run(wave(port, collections[0], 1, child))
            for trace_index, frames in enumerate(collections):
                for n in (1, 4, 8):
                    for repeat in (1, 2):
                        results, elapsed, sampled, before, after = asyncio.run(wave(port, frames, n, child))
                        for _ in range(60):
                            active = health(port)['active_sessions']
                            if active == 0: break
                            time.sleep(.05)
                        row = {'trace_index': trace_index+1, 'sessions': n, 'repeat': repeat, 'wall_seconds': elapsed, 'aggregate_frames_per_second': n*len(frames)/elapsed, 'event_agreement': all(r['events'] == expected[trace_index] for r in results), 'unique_session_ids': len({r['session_id'] for r in results}) == n, 'active_sessions_after': active, 'resource_before': before, 'resource_after': after, 'resource_samples': sampled, 'server_rss_sampled_peak_bytes': max(s['rss_bytes'] for s in sampled), 'rss_sampling_ms': 100, 'requests': dist([x for r in results for x in r['rtt_ms']]), 'event_bearing_requests': dist([x for r in results for x in r['event_bearing_rtt_ms']]), 'idle_requests': dist([x for r in results for x in r['idle_rtt_ms']]), 'raw_clients': results}
                        assert row['event_agreement'] and row['unique_session_ids'] and active == 0
                        rows.append(row)
                        write(out / f'{backend}_network_checkpoint.json', rows)
                        print(f'{backend} trace={trace_index+1} sessions={n} repeat={repeat} seconds={elapsed:.2f}', flush=True)
            return {'transport': 'TCP WebSocket loopback unpaced one acknowledged request at a time per client; 31-frame chunks', 'memory_scope': 'summed RSS of own server process tree; shared pages may be counted more than once; not private committed memory', 'warmup_sessions': 1, 'lifecycle_checks': lifecycle_checks, 'waves': rows}
        finally:
            descendants = child.children(recursive=True) if child.is_running() else []
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            for descendant in descendants:
                if descendant.is_running(): descendant.terminate()
            psutil.wait_procs(descendants, timeout=10)

def main():
    ARGS.out_root.mkdir(parents=True, exist_ok=True)
    out = ARGS.out_root / ('run_' + time.strftime('%Y%m%d_%H%M%S'))
    out.mkdir(exist_ok=False)
    version = metadata.version('vsl-streaming-toolkit')
    assert version == '0.1.2'
    assert 'site-packages' in vsl_streaming.__file__
    assert subprocess.check_output(['git','-C',str(REPO),'rev-parse',COMMIT], text=True).strip() == COMMIT
    source = Path(vsl_streaming.__file__).parent
    hashes = {p.name: digest(p) for p in source.glob('*.py')}
    frozen = json.loads((HERE/'evidence/aggregate_receipt.json').read_text(encoding='utf-8'))['installed_source_hashes']
    assert hashes == frozen, "Installed module byte hashes differ from the evaluated wheel"
    for name in hashes:
        blob = subprocess.check_output(['git','-C',str(REPO),'show',COMMIT+':src/vsl_streaming/'+name])
        installed = (source/name).read_bytes()
        assert installed.replace(b'\r\n',b'\n') == blob.replace(b'\r\n',b'\n'), name
    report = {'started_local': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'scope': 'host-only owner ONNX runtime integration; no accuracy, source-framework export parity, mobile or Jetson claim', 'release_version': version, 'release_commit': COMMIT, 'import_path': str(source), 'installed_source_hashes': hashes, 'harness_sha256': digest(__file__), 'configuration': ServerConfig().to_dict(), 'host': {'platform': platform.platform(), 'python': sys.version, 'logical_cpus': psutil.cpu_count(), 'physical_cpus': psutil.cpu_count(logical=False), 'ram_bytes': psutil.virtual_memory().total, 'versions': {n: metadata.version(n) for n in ['numpy','onnxruntime','onnx','fastapi','uvicorn','websockets','psutil']}}, 'traces': [], 'backends': {}}
    collections, all_segments = [], []
    for p in sorted(TRACES.glob('run*_keypoints_15fps.json')):
        frames = [dict(f, seq=i) for i,f in enumerate(json.loads(p.read_text(encoding='utf-8-sig'))['frames'])]
        collections.append(frames)
        row = {'name': p.name, 'path_private': str(p), 'sha256': digest(p), 'frames': len(frames), 'duration_ms': frames[-1]['timestamp_ms']-frames[0]['timestamp_ms'], 'modes': {}}
        for mode in ('signing_space','fixed_window'):
            reference, state = segmentize(frames, mode, len(frames))
            checks = []
            for chunk in (1,4,19,31,120):
                actual, status = segmentize(frames, mode, chunk)
                equal = [s.to_dict() for s in actual] == [s.to_dict() for s in reference] and state == status
                assert equal
                checks.append({'chunk_frames':chunk,'agreement':equal})
            row['modes'][mode] = {'events': len(reference), 'reasons': dict(Counter(s.reason for s in reference)), 'state': state, 'fragmentation_checks': checks, 'segments':[s.to_dict(False) for s in reference]}
            if mode == 'signing_space': all_segments.extend(reference)
        report['traces'].append(row)
    assert len(collections) == 3
    if ARGS.check_only:
        report["status"] = "preflight_passed"
        report["distinct_signing_segments"] = len(all_segments)
        report["finished_local"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        write(out/"preflight.json", report)
        print(json.dumps({"status":"preflight_passed","traces":3,"frames":sum(map(len,collections)),"segments":len(all_segments)}))
        return
    sys.path.insert(0,str(OWNER))
    from pipelines.spoter_onnx_inference import SPOTERONNXInferer
    from pipelines.slgcn_onnx_inference import SLGCNONNXInferer
    table = dict(csv.reader((OWNER/'gloss.csv').open(encoding='utf-8')))
    labels = [table[str(i)] for i in range(len(table))]
    dependencies = {str(p):digest(p) for p in [OWNER/'pipelines/spoter_onnx_inference.py',OWNER/'pipelines/slgcn_onnx_inference.py',OWNER/'utils/constants.py']}
    for backend, cls, t,v,c,layout,filename in [('spoter',SPOTERONNXInferer,70,54,2,'BTVC','spoter_all_cams.onnx'),('slgcn',SLGCNONNXInferer,150,27,3,'BCTVM','slgcn_bone_all_cams.onnx')]:
        directory = out/backend; directory.mkdir()
        profile = {'schema_version':1,'input_name':'poses','output_name':'logits','layout':layout,'num_frames':t,'num_points':v,'num_channels':c,'temporal_sampling':'external-python-v1','preprocessing':{'name':'external-python-v1','config':{'factory':'owner_bridge:prepare','source_sha256':digest(HERE/'owner_bridge.py'),'kwargs':{'legacy_server_root':str(OWNER),'backend':backend},'source_dependencies':dependencies}}}
        write(directory/'profile.json',profile); write(directory/'labels.json',labels)
        register_onnx(OWNER/'models'/filename,directory/'labels.json',directory/'profile.json',directory/'bundle')
        model = ONNXRecognizer(directory/'bundle')
        original = cls(str(OWNER/'models'/filename),table,num_frames=t,top_k=3,device='cpu',num_cpu_threads=1)
        converted = [objects(s.frames) for s in all_segments]
        parity = []
        for segment, obj in zip(all_segments,converted):
            reference, actual = original.infer(obj), model.predict_segment(segment.frames)['top_k']
            agree = [r['gloss'] for r in reference] == [r['label'] for r in actual]
            error = max(abs(float(a['score'])-float(b['confidence'])) for a,b in zip(reference,actual))
            parity.append({'segment':segment.to_dict(False),'top3_agreement':agree,'max_score_error':error})
        assert all(p['top3_agreement'] and p['max_score_error']<=2e-6 for p in parity)
        print(f'{backend} direct-owner parity {len(parity)}/{len(parity)}',flush=True)
        tensors = [external_tensor(s.frames,model.profile,model._external) for s in all_segments]
        for _ in range(2):
            for s,obj in zip(all_segments,converted): model.predict_segment(s.frames); original.infer(obj)
        timings = {'onnx':[],'preprocessing':[],'predict':[],'owner_infer_preconverted':[],'owner_infer_with_conversion':[],'matched_delta_ms':[]}
        for pass_index in range(5):
            for s,obj,tensor in zip(all_segments,converted,tensors):
                def timed(fn):
                    start=time.perf_counter();fn();return (time.perf_counter()-start)*1000
                timings['onnx'].append(timed(lambda:model.session.run(['logits'],{'poses':tensor})))
                timings['preprocessing'].append(timed(lambda:external_tensor(s.frames,model.profile,model._external)))
                timings['owner_infer_preconverted'].append(timed(lambda:original.infer(obj)))
                if pass_index%2 == 0:
                    direct=timed(lambda:original.infer(objects(s.frames))); wrapped=timed(lambda:model.predict_segment(s.frames))
                else:
                    wrapped=timed(lambda:model.predict_segment(s.frames));direct=timed(lambda:original.infer(objects(s.frames)))
                timings['predict'].append(wrapped);timings['owner_infer_with_conversion'].append(direct);timings['matched_delta_ms'].append(wrapped-direct)
        expected = [offline(model,frames) for frames in collections]
        predicted = sum(e['status']=='predicted' for trace in expected for e in trace)
        rejected = sum(e['status']!='predicted' for trace in expected for e in trace)
        row = {'model_sha256':digest(directory/'bundle/model.onnx'),'ordered_labels_sha256':digest(directory/'labels.json'),'label_count':len(labels),'profile_sha256':digest(directory/'profile.json'),'profile':profile,'gloss_source_sha256':digest(OWNER/'gloss.csv'),'manifest':model.manifest,'providers':model.session.get_providers(),'owner_session_options':{'execution_mode':str(original.session.get_session_options().execution_mode),'intra_threads':original.session.get_session_options().intra_op_num_threads,'inter_threads':original.session.get_session_options().inter_op_num_threads},'toolkit_session_options':{'execution_mode':str(model.session.get_session_options().execution_mode),'intra_threads':model.session.get_session_options().intra_op_num_threads,'inter_threads':model.session.get_session_options().inter_op_num_threads},'owner_direct_parity':parity,'max_score_error':max(p['max_score_error'] for p in parity),'warmup_passes':2,'timed_passes':5,'distinct_segments':len(all_segments),'timing_summaries':{k:dist(v) for k,v in timings.items()},'raw_layer_timings_ms':timings,'timing_caveat':'Paired runtime-stack difference includes owner vs toolkit session options, output checks and numeric postprocessing; not isolated wrapper cost. Repeated inputs are not independent signer samples.','trace_predictions':expected,'offline_predicted_events':predicted,'offline_rejected_events':rejected}
        report['backends'][backend]=row
        write(out/'receipt.json',report)
        row['network']=network(directory/'bundle',collections,expected,backend,out)
        write(out/'receipt.json',report)
    report['status']='passed';report['finished_local']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
    write(out/'receipt.json',report)
    print(json.dumps({'status':'passed','receipt':str(out/'receipt.json')}),flush=True)

if __name__ == '__main__': main()
