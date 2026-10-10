"""A single-process WebSocket adapter around the reusable stream core."""
import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
import uuid
from copy import deepcopy
from .config import ServerConfig
from .core import ProtocolError
from .protocol import MessageProcessor, decode_message, error_response
from .session_logging import SessionLog, SessionLogError, canonical_sha256, prepare_log_directory
from . import __version__


def create_app(bundle_dir=None, config=None, recognizer=None, session_log_dir=None):
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    settings = config or ServerConfig()
    log_directory = prepare_log_directory(session_log_dir)
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
    app = FastAPI(title="VSL Streaming Toolkit", version=__version__, lifespan=lifespan)
    active = set()
    app.state.active_sessions = active
    app.state.recognizer = model

    def public_profile():
        profile = deepcopy(getattr(model, "profile", None))
        if profile and profile.get("preprocessing", {}).get("name") == "external-python-v1":
            adapter = profile["preprocessing"]["config"]
            profile["preprocessing"]["config"] = {key: adapter[key] for key in ("factory", "source_sha256")}
        return profile

    @app.get("/health")
    async def health():
        return {"status": "ready", "active_sessions": len(active), "version": __version__}

    @app.get("/v1/config")
    async def configuration():
        return {"protocol_version": 1, "settings": settings.to_dict(),
                "profile": public_profile(),
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
        evidence = None
        response_index = 0
        end_reason = "server_error"
        disconnect_code = None

        async def send_response(response, request_sha256=None):
            nonlocal response_index
            index = response_index
            response_index += 1
            if evidence:
                evidence.write("response", response_index=index, response=response,
                               request_sha256=request_sha256)
            await websocket.send_json(response)
            if evidence:
                # ASGI send completion is not a remote application acknowledgement.
                evidence.write("send_complete", response_index=index)

        try:
            await websocket.accept()
            if log_directory is not None:
                evidence = SessionLog(log_directory, session_id)
                evidence.write("session_start", software_version=__version__, protocol_version=1,
                               settings=settings.to_dict(), settings_sha256=canonical_sha256(settings.to_dict()),
                               profile=public_profile(),
                               bundle_sha256=getattr(model, "manifest", {}).get("sha256"),
                               provider=getattr(model, "provider", None),
                               active_providers=model.session.get_providers() if hasattr(model, "session") else None)
            await send_response({"type": "ready", "session_id": session_id,
                                 "protocol_version": 1, "settings": settings.to_dict()})
            while True:
                packet = await websocket.receive()
                if packet["type"] == "websocket.disconnect":
                    end_reason = "client_disconnect"
                    disconnect_code = packet.get("code")
                    break
                raw = packet.get("text")
                if raw is None:
                    await send_response(error_response(ProtocolError("text_required", "Send UTF-8 JSON text")))
                    continue
                request_hash = hashlib.sha256(raw.encode("utf-8", errors="surrogatepass")).hexdigest() if evidence else None
                try:
                    message = decode_message(raw, settings.max_message_bytes)
                except ProtocolError as error:
                    await send_response(error_response(error), request_hash)
                    continue
                # One outstanding request per connection; global inference is bounded.
                async with app.state.inference_gate:
                    response = await asyncio.to_thread(processor.process, message)
                await send_response(response, request_hash)
        except WebSocketDisconnect as error:
            end_reason = "connection_lost"
            disconnect_code = error.code
        except SessionLogError:
            end_reason = "evidence_log_failed"
            logging.getLogger(__name__).error("Session evidence logging failed for %s", session_id)
            await websocket.close(code=1011, reason="Session evidence logging failed")
        finally:
            active.discard(session_id)
            if evidence:
                try:
                    state = processor.session.status()
                    evidence.write("session_end", reason=end_reason, disconnect_code=disconnect_code,
                                   state=state, buffered_frames_abandoned=state["buffered_frames"])
                except SessionLogError:
                    logging.getLogger(__name__).error("Session end evidence is incomplete for %s", session_id)
                finally:
                    try:
                        evidence.close()
                    except SessionLogError:
                        logging.getLogger(__name__).error("Session evidence close failed for %s", session_id)
    return app


DEMO_HTML = """<!doctype html><html lang='en'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>VSL keypoint stream</title><style>
body{font:16px system-ui;margin:40px auto;max-width:900px;padding:0 20px;background:#f5f8fa;color:#18313c}
button,input{font:inherit;margin:8px 6px 8px 0;padding:8px}pre{white-space:pre-wrap;background:white;padding:20px;border-radius:8px}
</style><h1>VSL keypoint stream</h1><p>Upload a JSON array or JSONL file of keypoint frames compatible with the server model.
Each frame needs an increasing seq and timestamp_ms. This page sends the file through a WebSocket;
it does not extract landmarks from camera video.</p>
<input type='file' id='file' accept='.json,.jsonl'><button id='run'>Replay file</button><button id='reset'>Reset</button>
<p id='status'>Disconnected</p><pre id='output'></pre><script>
let ws=null,pending=new Map(),counter=0,busy=false,wsReady=false;
const HANDSHAKE_TIMEOUT_MS=10000,REQUEST_TIMEOUT_MS=30000;
const MAX_FILE_BYTES=10*1024*1024,MAX_VISIBLE_RESPONSES=20;
const output=document.getElementById('output'),status=document.getElementById('status');
function setBusy(value){busy=value;document.getElementById('run').disabled=value;
document.getElementById('reset').disabled=value;document.getElementById('file').disabled=value;}
function stopSocket(socket,error){
if(ws===socket){ws=null;wsReady=false;status.textContent='Disconnected';}
for(const [id,p] of pending){if(p.socket===socket){clearTimeout(p.timer);pending.delete(id);p.reject(error);}}
if(socket.readyState<2)socket.close();}
function finishSocket(){const socket=ws;ws=null;wsReady=false;if(socket&&socket.readyState<2)socket.close();}
function connect(){if(ws&&ws.readyState===1&&wsReady)return Promise.resolve();
return new Promise((resolve,reject)=>{
const socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/v1/stream');
ws=socket;wsReady=false;let ready=false;
const fail=error=>{clearTimeout(timer);if(!ready)reject(error);stopSocket(socket,error);};
const timer=setTimeout(()=>fail(Error('Connection handshake timed out')),HANDSHAKE_TIMEOUT_MS);
socket.onmessage=e=>{let r;try{r=JSON.parse(e.data);}catch(error){fail(Error('Invalid server response'));return;}
if(!r||typeof r!=='object'){fail(Error('Invalid server response'));return;}
if(r.type==='ready'){if(ready){fail(Error('Unexpected repeated handshake'));return;}
ready=true;clearTimeout(timer);wsReady=true;status.textContent='Connected: '+r.session_id;resolve();return;}
if(!ready){fail(Error('Server did not complete the handshake'));return;}
const p=pending.get(r.request_id);
if(p&&p.socket===socket){clearTimeout(p.timer);pending.delete(r.request_id);p.resolve(r);}
else{fail(Error(r.error?.message||'Uncorrelated server response; replay stopped'));}};
socket.onerror=()=>fail(Error('Connection failed'));
socket.onclose=e=>fail(Error('Disconnected ('+e.code+')'+(e.reason?': '+e.reason:'')));});}
async function send(message){
if(!ws||ws.readyState!==1||!wsReady)throw Error('Stream disconnected; restart the complete replay');
const socket=ws,id='browser-'+(++counter);
return new Promise((resolve,reject)=>{
const timer=setTimeout(()=>stopSocket(socket,Error('Request acknowledgement timed out; outcome unknown. Restart the complete replay.')),REQUEST_TIMEOUT_MS);
pending.set(id,{socket,resolve,reject,timer});
try{socket.send(JSON.stringify({...message,request_id:id}));}catch(error){stopSocket(socket,error);}});}
document.getElementById('reset').onclick=async()=>{if(busy)return;setBusy(true);try{
await connect();output.textContent=JSON.stringify(await send({type:'reset'}),null,2);
}catch(e){output.textContent=e.message;}finally{finishSocket();setBusy(false);}};
document.getElementById('run').onclick=async()=>{if(busy)return;setBusy(true);try{
const file=document.getElementById('file').files[0];if(!file)throw Error('Choose a frame JSON file');
if(file.size>MAX_FILE_BYTES)throw Error('Replay file exceeds the 10 MiB browser limit; use the Python client.');
const raw=(await file.text()).trim();
const frames=raw.startsWith('[')?JSON.parse(raw):raw.split(/\\r?\\n/).filter(x=>x.trim()).map(x=>JSON.parse(x));
if(!Array.isArray(frames)||!frames.length)throw Error('Expected nonempty frame array or JSONL');
await connect();const reset=await send({type:'reset'});if(reset.type==='error')throw Error(reset.error.message);
const config=await(await fetch('/v1/config')).json();let results=[],predicted=0,rejected=0,totalResponses=0;
output.textContent='';const encoder=new TextEncoder();
const n=Math.min(30,config.settings.max_batch_frames);
for(let i=0;i<frames.length;){let count=Math.min(n,frames.length-i),request;
while(count>0){request={type:'frames',frames:frames.slice(i,i+count),flush:i+count>=frames.length};
if(encoder.encode(JSON.stringify({...request,request_id:'browser-'+(counter+1)})).length<=config.settings.max_message_bytes)break;
count--;}
if(!count)throw Error('Frame '+i+' exceeds the server message byte limit.');
const r=await send(request);i+=count;
results.push(r);totalResponses++;if(results.length>MAX_VISIBLE_RESPONSES)results.shift();
output.textContent=JSON.stringify(results,null,2);if(r.type==='error')throw Error(r.error.message);
for(const event of r.events){if(event.status==='predicted')predicted++;else rejected++;}
status.textContent='Replayed '+i+'/'+frames.length+' frames; '+predicted+' predictions; '+rejected+' rejected events; showing latest '+results.length+' responses; omitted '+(totalResponses-results.length);}
}catch(e){output.textContent+=(output.textContent?'\\n\\n':'')+e.message;}finally{finishSocket();setBusy(false);}};</script></html>"""
