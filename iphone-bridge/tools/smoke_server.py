"""Mock-only bridge test server. Does not call an AI service or accept live drones.

Run from this directory: python -m uvicorn smoke_server:app --host 0.0.0.0 --port 8000
Then open http://YOUR-LAPTOP-IP:8000/docs to send commands through POST /command.
"""
import asyncio
import json
import time
import uuid
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

app=FastAPI(title='Guardian Angel MOCK bridge test')
socket=None
mock_confirmed=False
telemetry={}
pending={}
frame=b''

@app.websocket('/ws/drone')
async def drone(ws:WebSocket):
    global socket,mock_confirmed,telemetry
    await ws.accept()
    if socket is not None:
        await ws.close(code=1008,reason='One bridge at a time'); return
    socket=ws; mock_confirmed=False; telemetry={}
    try:
        while True:
            message=json.loads(await ws.receive_text())
            if message.get('type')=='hello':
                if message.get('mode')!='mock':
                    await ws.close(code=1008,reason='This server accepts mock hardware only'); return
                mock_confirmed=True
            elif message.get('type')=='telemetry': telemetry=message
            elif message.get('type')=='ack':
                future=pending.get(message.get('cmd_id'))
                if future and not future.done(): future.set_result(message)
    except WebSocketDisconnect: pass
    finally:
        socket=None; mock_confirmed=False
        for future in list(pending.values()):
            if not future.done(): future.set_exception(RuntimeError('Bridge disconnected'))

@app.get('/state')
async def state(): return dict(connected=socket is not None,mock=mock_confirmed,telemetry=telemetry,jpeg_bytes=len(frame))

@app.post('/frame')
async def upload(request:Request):
    global frame
    if not mock_confirmed: raise HTTPException(409,'Mock bridge not connected')
    frame=await request.body(); return {'ok':True}

@app.get('/frame.jpg')
async def image(): return Response(frame,media_type='image/jpeg')

@app.post('/command')
async def command(body:dict):
    if socket is None or not mock_confirmed: raise HTTPException(409,'Connect the mock iPhone first')
    identifier=uuid.uuid4().hex[:8]
    message={**body,'type':'cmd','cmd_id':identifier,'expires_at_ms':int((time.time()+5)*1000)}
    future=asyncio.get_running_loop().create_future(); pending[identifier]=future
    try:
        await socket.send_text(json.dumps(message))
        return await asyncio.wait_for(future,180 if body.get('action')=='rtl' else 120)
    except asyncio.TimeoutError:
        if socket: await socket.send_text(json.dumps({'type':'cmd','cmd_id':uuid.uuid4().hex[:8],'action':'stop'}))
        raise HTTPException(504,'No completion acknowledgment')
    except RuntimeError as exc: raise HTTPException(503,str(exc))
    finally: pending.pop(identifier,None)
