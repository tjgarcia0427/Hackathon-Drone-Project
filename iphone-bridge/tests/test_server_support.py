"""Test the patch's actual coroutine implementations without AI or a drone."""
import asyncio
import ast
import importlib.util
import json
import time
import threading
import types
import unittest
import uuid
from pathlib import Path

spec=importlib.util.spec_from_file_location('patch_server',Path(__file__).parents[1]/'server-support/patch_server.py')
patcher=importlib.util.module_from_spec(spec); spec.loader.exec_module(patcher)

class ServerSupportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state=types.SimpleNamespace(drone_ws=None,pending_acks={},search_task=None,drone=object(),telemetry_at=time.monotonic())
        self.messages=[]; self.auto_ack=True
        async def send_text(text):
            message=json.loads(text); self.messages.append(message)
            future=self.state.pending_acks.get(message['cmd_id'])
            if self.auto_ack and future is not None: future.set_result({'ok':True,'cmd_id':message['cmd_id']})
        self.state.drone_ws=types.SimpleNamespace(send_text=send_text)
        async def push_state(): pass
        self.ns=dict(S=self.state,asyncio=asyncio,json=json,time=time,uuid=uuid,Any=object,
            log=lambda *a,**k:None,push_state=push_state)
        exec(patcher.HELPERS+patcher.SEND+patcher.RESET+patcher.ABORT,self.ns)

    async def test_command_wire_format_and_cleanup(self):
        answer=await self.ns['send_cmd']('goto',lat=25.7,lng=-80.1,alt=10)
        self.assertTrue(answer['ok']); self.assertEqual(self.messages[0]['lat'],25.7)
        self.assertNotIn('params',self.messages[0]); self.assertFalse(self.state.pending_acks)
        self.assertGreater(self.messages[0]['expires_at_ms'],time.time()*1000)

    async def test_timeout_sends_stop_and_cleans_up(self):
        self.auto_ack=False
        with self.assertRaises(asyncio.TimeoutError): await self.ns['send_cmd']('move',timeout=.01,bearing=0,dist=3)
        self.assertEqual([m['action'] for m in self.messages],['move','stop'])
        self.assertFalse(self.state.pending_acks)

    async def test_nack_sends_stop(self):
        async def nack(text):
            message=json.loads(text); self.messages.append(message)
            if message['action']!='stop': self.state.pending_acks[message['cmd_id']].set_exception(RuntimeError('disabled'))
        self.state.drone_ws.send_text=nack
        with self.assertRaisesRegex(RuntimeError,'disabled'): await self.ns['send_cmd']('yaw',deg=10)
        self.assertEqual(self.messages[-1]['action'],'stop')

    async def test_reset_cancels_before_sending_stop(self):
        self.auto_ack=False
        task=asyncio.create_task(self.ns['send_cmd']('goto',lat=1,lng=1,alt=10))
        self.state.search_task=task
        while not self.messages: await asyncio.sleep(0)
        await self.ns['reset']()
        self.assertTrue(task.cancelled()); self.assertFalse(self.state.pending_acks)
        self.assertEqual(self.messages[-1]['action'],'stop'); self.assertEqual(self.state.phase,'idle')

    async def test_abort_does_not_disarm_before_rtl(self):
        self.auto_ack=False
        task=asyncio.create_task(self.ns['send_cmd']('goto',lat=1,lng=1,alt=10))
        self.state.search_task=task
        while not self.messages: await asyncio.sleep(0)
        self.auto_ack=True
        self.assertTrue((await self.ns['abort']())['ok'])
        self.assertEqual([m['action'] for m in self.messages],['goto','rtl'])

    async def test_stale_frame_is_not_used(self):
        after=time.monotonic(); self.state.latest_frame_at=after-1
        task=asyncio.create_task(self.ns['iphone_fresh_frame'](after))
        await asyncio.sleep(.02); self.assertFalse(task.done())
        self.state.latest_frame_at=time.monotonic()
        self.assertGreater(await asyncio.wait_for(task,.5),after)
        self.state.telemetry_at=time.monotonic()-5
        self.assertFalse(self.ns['iphone_telemetry_ready']())

    def test_refuses_incompatible_source_and_repeat_patch(self):
        with self.assertRaises(ValueError): patcher.patch('x = 1\n')
        with self.assertRaises(ValueError): patcher.patch(patcher.MARKER+'\nx = 1\n')

    def scaffold_namespace(self):
        source=(Path(__file__).parent/'fixtures/server_scaffold.py.txt').read_text(encoding='utf-8')
        tree=ast.parse(patcher.patch(source))
        definitions=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))]
        for node in definitions: node.decorator_list=[]
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+definitions,type_ignores=[])
        ast.fix_missing_locations(module)
        async def broadcast(*args): pass
        self.ns['broadcast']=broadcast
        exec(compile(module,'patched_server.py','exec'),self.ns)
        async def push_state(): pass
        self.ns['push_state']=push_state; self.ns['log']=lambda *a,**k:None
        return self.ns

    def test_modified_teammate_code_is_not_overwritten(self):
        source=(Path(__file__).parent/'fixtures/server_scaffold.py.txt').read_text(encoding='utf-8')
        modified=source.replace('timeout: float = 25.0','timeout: float = 30.0')
        with self.assertRaisesRegex(ValueError,'differs from scaffold'): patcher.patch(modified)
        self.assertIn(patcher.MARKER,patcher.patch(source+'\n# teammate comment\n'))

    async def test_disconnect_cancels_mission_before_allowing_reconnect(self):
        ns=self.scaffold_namespace()
        class Disconnected(Exception): pass
        class WS:
            async def accept(self): pass
            async def receive_text(self): raise Disconnected()
        ns['WebSocketDisconnect']=Disconnected
        started=asyncio.Event(); cancelled=[]
        async def mission():
            try:
                started.set(); await asyncio.Event().wait()
            finally: cancelled.append(True)
        self.state.drone_ws=None
        self.state.search_task=asyncio.create_task(mission()); await started.wait()
        await ns['ws_drone'](WS())
        self.assertEqual(cancelled,[True]); self.assertIsNone(self.state.drone_ws)
        self.assertEqual(self.state.telemetry_at,0)

    async def test_old_frame_cannot_reappear_after_reset(self):
        ns=self.scaffold_namespace()
        class HTTPError(Exception):
            def __init__(self,status,detail): self.status=status; super().__init__(detail)
        started=threading.Event(); release=threading.Event()
        def detect(data):
            started.set(); release.wait(timeout=2); return {'person':False}
        class Request:
            async def body(self): return b'jpeg'
        ns['HTTPException']=HTTPError; ns['detector']=types.SimpleNamespace(detect=detect)
        self.state.frame_epoch=1; self.state.latest_frame=None
        task=asyncio.create_task(ns['frame'](Request()))
        try:
            for _ in range(100):
                if started.is_set(): break
                await asyncio.sleep(.005)
            self.assertTrue(started.is_set())
            self.state.frame_epoch=2
        finally: release.set()
        with self.assertRaises(HTTPError) as exc: await task
        self.assertEqual(exc.exception.status,409); self.assertIsNone(self.state.latest_frame)

if __name__=='__main__': unittest.main()
