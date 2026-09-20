import importlib.util
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    HAVE_DEPS=True
except ImportError:
    HAVE_DEPS=False

@unittest.skipUnless(HAVE_DEPS,'Optional: install tools/requirements.txt and httpx')
class SmokeServerTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('smoke_server',Path(__file__).parents[1]/'tools/smoke_server.py')
        self.module=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.client=TestClient(self.module.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)

    def wait_for_hello(self):
        for _ in range(50):
            if self.client.get('/state').json()['mock']: return
            time.sleep(.01)
        self.fail('Mock handshake did not complete')

    def test_mock_command_roundtrip_and_frame_upload(self):
        with self.client.websocket_connect('/ws/drone') as ws:
            ws.send_json({'type':'hello','mode':'mock'})
            self.wait_for_hello()
            with ThreadPoolExecutor(max_workers=1) as pool:
                response=pool.submit(self.client.post,'/command',json={'action':'yaw','deg':30})
                command=ws.receive_json()
                self.assertEqual(command['action'],'yaw'); self.assertEqual(command['deg'],30)
                self.assertNotIn('params',command)
                ws.send_json({'type':'ack','cmd_id':command['cmd_id'],'ok':True})
                self.assertTrue(response.result(timeout=5).json()['ok'])
            payload=b'\xff\xd8\xff\xd9'
            self.assertEqual(self.client.post('/frame',content=payload,headers={'Content-Type':'image/jpeg'}).status_code,200)
            self.assertEqual(self.client.get('/frame.jpg').content,payload)

    def test_live_hardware_rejected(self):
        with self.client.websocket_connect('/ws/drone') as ws:
            ws.send_json({'type':'hello','mode':'live'})
            with self.assertRaises(WebSocketDisconnect) as exc: ws.receive_json()
            self.assertEqual(exc.exception.code,1008)

    def test_second_connection_rejected(self):
        with self.client.websocket_connect('/ws/drone') as ws:
            ws.send_json({'type':'hello','mode':'mock'}); self.wait_for_hello()
            with self.client.websocket_connect('/ws/drone') as second:
                with self.assertRaises(WebSocketDisconnect) as exc: second.receive_json()
                self.assertEqual(exc.exception.code,1008)
            self.assertTrue(self.client.get('/state').json()['connected'])

if __name__=='__main__': unittest.main()
