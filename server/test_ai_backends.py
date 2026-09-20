import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import httpx
import ai_backends as ai
from models import MissionPlan, SearchStep

PLAN = {"target_lat": 25.7617, "target_lng": -80.1918, "search_radius_m": 5.0,
        "altitude_m": 10.0, "pattern": "grid", "gimbal_pitch_deg": -60.0, "rationale": "Demo"}
STEP = {"action": "yaw", "yaw_deg": 30.0, "gimbal_pitch_deg": None, "move_bearing_deg": None,
        "move_distance_m": None, "confidence": 0.0, "observation": "Inspect another bearing"}


class APIProviderTests(unittest.TestCase):
    def test_openai_real_sdk_serializes_image_and_parses_schema(self):
        from openai import OpenAI
        captured = []
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"id":"resp_test", "object":"response", "created_at":1,
                "model":"test-model", "status":"completed", "output":[{"id":"msg_test", "type":"message",
                "role":"assistant", "status":"completed", "content":[{"type":"output_text", "text":json.dumps(STEP), "annotations":[]}]}]})
        def factory(**kwargs):
            return OpenAI(api_key="test-only", http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)
        with patch.dict(os.environ, {"OPENAI_API_KEY":"test-only"}), patch('openai.OpenAI', side_effect=factory):
            result = ai.generate(ai.Settings('openai_api','test-model'), SearchStep, 'system', 'prompt', b'jpeg', timeout=8)
        self.assertEqual(result.action, 'yaw')
        self.assertEqual(captured[0]['input'][0]['content'][0]['image_url'], 'data:image/jpeg;base64,'+base64.b64encode(b'jpeg').decode())
        self.assertFalse(captured[0]['store'])
        self.assertEqual(captured[0]['text']['format']['type'], 'json_schema')

    def test_anthropic_real_sdk_serializes_image_and_parses_schema(self):
        from anthropic import Anthropic
        captured = []
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"id":"msg_test", "type":"message", "role":"assistant", "model":"test-model",
                "content":[{"type":"text", "text":json.dumps(PLAN)}], "stop_reason":"end_turn",
                "usage":{"input_tokens":1,"output_tokens":1}})
        def factory(**kwargs):
            return Anthropic(api_key="test-only", http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY":"test-only"}), patch('anthropic.Anthropic', side_effect=factory):
            result = ai.generate(ai.Settings('anthropic_api','test-model'), MissionPlan, 'system', 'prompt', b'jpeg')
        self.assertEqual(result.altitude_m, 10)
        self.assertEqual(captured[0]['messages'][0]['content'][0]['source']['data'], base64.b64encode(b'jpeg').decode())
        self.assertEqual(captured[0]['output_config']['format']['type'], 'json_schema')

    def test_api_failure_is_redacted_and_never_falls_back(self):
        from openai import OpenAI
        count = []
        def handler(request):
            count.append(1)
            return httpx.Response(401, json={"error":{"message":"secret-value must not be exposed"}})
        def factory(**kwargs):
            return OpenAI(api_key="test-only", http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)
        with patch.dict(os.environ, {"OPENAI_API_KEY":"test-only"}), patch('openai.OpenAI', side_effect=factory):
            with self.assertRaises(ai.AIError) as error:
                ai.generate(ai.Settings('openai_api','test-model'), MissionPlan, 'system', 'prompt')
        self.assertNotIn('secret-value', str(error.exception))
        self.assertEqual(len(count), 1)


class DecisionTests(unittest.TestCase):
    def test_schema_all_fields_required_and_no_extras(self):
        schema = ai.strict_schema(SearchStep)
        self.assertEqual(set(schema['required']), set(SearchStep.model_fields))
        self.assertFalse(schema['additionalProperties'])
        self.assertNotIn('default', json.dumps(schema))

    def test_invalid_decisions_fail_closed(self):
        for data in (None, {'action':'takeoff'}, {**PLAN, 'shell':'do something'},
                     {**PLAN,'altitude_m':float('nan')}, {**PLAN,'altitude_m':'10'}, {**PLAN,'altitude_m':True}):
            with self.subTest(data=data), self.assertRaises(ai.AIError):
                ai.validate_decision(data, MissionPlan)

    def test_environment_default_and_subscription_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ai.from_environment().provider, 'anthropic_api')
            with self.assertRaises(ai.AIError):
                ai.validate_setup(ai.Settings('openai_api', 'test-model'))
        with patch.dict(os.environ, {'AI_PROVIDER':'codex','OPENAI_API_KEY':'secret','ANTHROPIC_API_KEY':'secret',
                                    'CODEX_API_KEY':'secret','CLAUDE_CODE_OAUTH_TOKEN':'secret'}):
            env = ai.subscription_environment()
            for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','CODEX_API_KEY','CLAUDE_CODE_OAUTH_TOKEN'):
                self.assertNotIn(key, env)


class CLIProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='guardian-cli-test-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.script = self.folder/'fake_cli.py'
        self.record = self.folder/'request.json'
        self.script.write_text('''import sys, json, os
from pathlib import Path
args=sys.argv[1:]
if args[:2]==['login','status']:
    print('Logged in using '+os.environ.get('TEST_AUTH','ChatGPT'), file=sys.stderr); raise SystemExit()
if args[:2]==['auth','status']:
    print(json.dumps({'loggedIn':True,'authMethod':os.environ.get('TEST_AUTH','claude.ai')})); raise SystemExit()
payload=sys.stdin.read()
Path(os.environ['TEST_RECORD']).write_text(json.dumps({'args':args,'stdin':payload,'cwd':os.getcwd(),
    'has_api_key':any(k in os.environ for k in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','CODEX_API_KEY'])}))
result=json.loads(os.environ['TEST_RESULT'])
if 'exec' in args:
    Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(result))
else:
    print(json.dumps({'type':'system','subtype':'init'}))
    print(json.dumps({'type':'result','subtype':'success','is_error':False,'structured_output':result}))
''', encoding='utf-8')

    def execute(self, provider):
        with patch('ai_backends.cli_command', return_value=[sys.executable,str(self.script)]), patch.dict(os.environ,
             {'TEST_RECORD':str(self.record),'TEST_RESULT':json.dumps(STEP),'OPENAI_API_KEY':'secret'}):
            result=ai.generate(ai.Settings(provider), SearchStep, 'Do not execute tools', 'literal $(command) & data', b'jpeg', timeout=8)
        request=json.loads(self.record.read_text())
        self.assertFalse(request['has_api_key'])
        self.assertFalse(Path(request['cwd']).exists())
        self.assertEqual(result.action,'yaw')
        return request

    def test_codex_image_schema_stdin_and_isolation(self):
        request=self.execute('codex')
        self.assertIn('--image',request['args'])
        self.assertIn('--output-schema',request['args'])
        self.assertIn('read-only',request['args'])
        self.assertIn('shell_tool',request['args'])
        self.assertIn('literal $(command) & data',request['stdin'])

    def test_claude_image_schema_stdin_and_tools_disabled(self):
        request=self.execute('claude_code')
        self.assertEqual(request['args'][request['args'].index('--tools')+1], '')
        self.assertIn('--safe-mode',request['args'])
        self.assertIn('--verbose',request['args'])
        self.assertEqual(request['args'][request['args'].index('--input-format')+1], 'stream-json')
        self.assertEqual(request['args'][request['args'].index('--output-format')+1], 'stream-json')
        payload=json.loads(request['stdin'])
        self.assertEqual(payload['message']['content'][0]['source']['data'],base64.b64encode(b'jpeg').decode())
        self.assertEqual(payload['message']['content'][1]['text'],'literal $(command) & data')

    def test_subscription_rejects_cli_api_login(self):
        with patch('ai_backends.cli_command',return_value=[sys.executable,str(self.script)]), patch.dict(os.environ,{'TEST_AUTH':'API key'}):
            for provider in ('codex','claude_code'):
                with self.subTest(provider=provider), self.assertRaises(ai.AIError):
                    ai.validate_setup(ai.Settings(provider), authenticate=True)

    def test_process_timeout_returns_promptly(self):
        started=time.monotonic()
        with self.assertRaises(ai.AIError):
            ai.run_cli([sys.executable,'-c','import time; time.sleep(20)'], '', self.folder, .05, os.environ.copy())
        self.assertLess(time.monotonic()-started,5)

    def test_npm_shim_uses_node_without_shell(self):
        shim=self.folder/'codex.cmd'; shim.write_text('@echo off')
        entry=self.folder/'node_modules/@openai/codex/bin/codex.js'; entry.parent.mkdir(parents=True); entry.write_text('')
        with patch('ai_backends.shutil.which',side_effect=lambda name:str(shim) if name=='codex' else 'node.exe'), patch.dict(os.environ,{},clear=True):
            self.assertEqual(ai.cli_command('codex'), ['node.exe',str(entry)])

    def test_claude_native_npm_shim(self):
        shim=self.folder/'claude.cmd'; shim.write_text('@echo off')
        entry=self.folder/'node_modules/@anthropic-ai/claude-code/bin/claude.exe'
        entry.parent.mkdir(parents=True); entry.write_bytes(b'fixture')
        with patch('ai_backends.shutil.which',return_value=str(shim)), patch.dict(os.environ,{},clear=True):
            self.assertEqual(ai.cli_command('claude_code'), [str(entry)])


if __name__ == '__main__':
    unittest.main()
