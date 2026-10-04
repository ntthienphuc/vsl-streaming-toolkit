"""A single-process WebSocket adapter around the reusable stream core."""
import asyncio
from contextlib import asynccontextmanager
import uuid
from copy import deepcopy
from .config import ServerConfig
from .core import ProtocolError
from .protocol import MessageProcessor, decode_message, error_response


def create_app(bundle_dir=None, config=None, recognizer=None):
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    settings = config or ServerConfig()
    if recognizer is None:
        from .runtime import ONNXRecognizer
        model = ONNXRecognizer(bundle_dir, provider=settings.provider, top_k=settings.top_k)
    else:
        model = recognizer
    @asynccontextmanager
    async def lifespan(application):
        # Construct on the running event loop, including Python 3.9.
        application.state.inference_gate = asyncio.Semaphore(settings.inference_concurrency)
        yield
    app = FastAPI(title="VSL Streaming Toolkit", version="0.1.1", lifespan=lifespan)
    active = set()
    app.state.active_sessions = active
    app.state.recognizer = model

    @app.get("/health")
    async def health():
        return {"status": "ready", "active_sessions": len(active), "version": "0.1.1"}

    @app.get("/v1/config")
    async def configuration():
        profile = deepcopy(getattr(model, "profile", None))
        if profile and profile.get("preprocessing", {}).get("name") == "external-python-v1":
            adapter = profile["preprocessing"]["config"]
            profile["preprocessing"]["config"] = {key: adapter[key] for key in ("factory", "source_sha256")}
        return {"protocol_version": 1, "settings": settings.to_dict(),
                "profile": profile,
                "labels": getattr(model, "labels", None)}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return DEMO_HTML

    @app.websocket("/v1/stream")
    async def stream(websocket: WebSocket):
        if len(active) >= settings.max_sessions:
            await websocket.accept()
            await websocket.close(code=1013, reason="Server session capacity reached")
            return
        session_id = str(uuid.uuid4())
        active.add(session_id)
        processor = MessageProcessor(model, settings)
        try:
            await websocket.accept()
            await websocket.send_json({"type": "ready", "session_id": session_id,
                                       "protocol_version": 1, "settings": settings.to_dict()})
            while True:
                packet = await websocket.receive()
                if packet["type"] == "websocket.disconnect":
                    break
                raw = packet.get("text")
                if raw is None:
                    await websocket.send_json(error_response(ProtocolError("text_required", "Send UTF-8 JSON text")))
                    continue
                try:
                    message = decode_message(raw, settings.max_message_bytes)
                except ProtocolError as error:
                    await websocket.send_json(error_response(error))
                    continue
                # One outstanding request per connection; global inference is bounded.
                async with app.state.inference_gate:
                    response = await asyncio.to_thread(processor.process, message)
                await websocket.send_json(response)
        except WebSocketDisconnect:
            pass
        finally:
            active.discard(session_id)
    return app


DEMO_HTML = """<!doctype html><html lang='en'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>VSL keypoint stream</title><style>
body{font:16px system-ui;margin:40px auto;max-width:900px;padding:0 20px;background:#f5f8fa;color:#18313c}
button,input{font:inherit;margin:8px 6px 8px 0;padding:8px}pre{white-space:pre-wrap;background:white;padding:20px;border-radius:8px}
</style><h1>VSL keypoint stream</h1><p>Upload a JSON array of keypoint frames compatible with the server model.
Each frame needs an increasing seq and timestamp_ms. This page sends the file through a WebSocket;
it does not extract landmarks from camera video.</p>
<input type='file' id='file' accept='.json'><button id='run'>Replay file</button><button id='reset'>Reset</button>
<p id='status'>Disconnected</p><pre id='output'></pre><script>
let ws=null,pending=new Map(),counter=0,busy=false;
const output=document.getElementById('output'),status=document.getElementById('status');
function setBusy(value){busy=value;document.getElementById('run').disabled=value;
document.getElementById('reset').disabled=value;document.getElementById('file').disabled=value;}
function connect(){return new Promise((resolve,reject)=>{
ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/v1/stream');
ws.onmessage=e=>{const r=JSON.parse(e.data);if(r.type==='ready'){status.textContent='Connected: '+r.session_id;resolve();}
else{const p=pending.get(r.request_id);if(p){pending.delete(r.request_id);p(r);}
else if(r.type==='error'){output.textContent=JSON.stringify(r,null,2);for(const resolve of pending.values())resolve(r);pending.clear();}}};
ws.onerror=()=>reject(Error('Connection failed'));ws.onclose=()=>{status.textContent='Disconnected';
for(const p of pending.values())p({type:'error',error:{message:'Disconnected'}});pending.clear();};});}
async function send(message){if(!ws||ws.readyState!==1)await connect();const id='browser-'+(++counter);
return new Promise(resolve=>{pending.set(id,resolve);ws.send(JSON.stringify({...message,request_id:id}));});}
document.getElementById('reset').onclick=async()=>{if(busy)return;setBusy(true);try{
output.textContent=JSON.stringify(await send({type:'reset'}),null,2);
}catch(e){output.textContent=e.message;}finally{setBusy(false);}};
document.getElementById('run').onclick=async()=>{if(busy)return;setBusy(true);try{
const file=document.getElementById('file').files[0];if(!file)throw Error('Choose a frame JSON file');
const frames=JSON.parse(await file.text());if(!Array.isArray(frames)||!frames.length)throw Error('Expected nonempty frame array');
const reset=await send({type:'reset'});if(reset.type==='error')throw Error(reset.error.message);
const config=await(await fetch('/v1/config')).json();let results=[],predicted=0,rejected=0;
const n=Math.min(30,config.settings.max_batch_frames);
for(let i=0;i<frames.length;i+=n){const r=await send({type:'frames',frames:frames.slice(i,i+n),flush:i+n>=frames.length});
results.push(r);output.textContent=JSON.stringify(results,null,2);if(r.type==='error')throw Error(r.error.message);
for(const event of r.events){if(event.status==='predicted')predicted++;else rejected++;}
status.textContent='Replayed '+Math.min(i+n,frames.length)+'/'+frames.length+' frames; '+predicted+' predictions; '+rejected+' rejected events';}
}catch(e){output.textContent=e.message;}finally{setBusy(false);}};</script></html>"""
