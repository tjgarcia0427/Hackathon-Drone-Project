import asyncio
import os
import threading
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import HTTPException
import app
import ai_backends
import planner
from models import DroneState, FallEvent, MissionPlan, SearchStep


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        app.S=app.State()
        self.original=planner._settings
        self.addCleanup(setattr,planner,'_settings',self.original)
        self.client=TestClient(app.app)

    def test_server_starts_without_api_key_and_lists_four_options(self):
        with patch.dict(os.environ,{},clear=True):
            planner._settings=ai_backends.Settings('anthropic_api')
            data=self.client.get('/state').json()['ai']
        self.assertFalse(data['configured'])
        self.assertEqual(len(data['options']),4)

    def test_switch_idle_and_block_active_or_pending_mission(self):
        with patch('ai_backends.validate_setup'):
            response=self.client.post('/ai/config',json={'provider':'codex','model':''})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['billing'],'subscription')
            app.S.phase='searching'
            self.assertEqual(self.client.post('/ai/config',json={'provider':'claude_code'}).status_code,409)
            app.S.phase='idle'; app.S.planning=True
            self.assertEqual(self.client.post('/ai/config',json={'provider':'claude_code'}).status_code,409)
            app.S.planning=False; app.S.pending_acks['pending']=object()
            self.assertEqual(self.client.post('/ai/config',json={'provider':'claude_code'}).status_code,409)
        self.assertEqual(planner._settings.provider,'codex')

    def test_bad_config_is_not_applied_and_secrets_cannot_be_posted(self):
        with patch('ai_backends.validate_setup',side_effect=ai_backends.AIError('Missing setup')):
            self.assertEqual(self.client.post('/ai/config',json={'provider':'openai_api','model':'test-model'}).status_code,400)
        self.assertEqual(planner._settings,self.original)
        self.assertEqual(self.client.post('/ai/config',json={'provider':'codex','api_key':'do-not-store'}).status_code,422)


class PlanningLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_timeout_discards_late_movement_and_requests_stop(self):
        app.S=app.State()
        app.S.plan=MissionPlan(target_lat=25.7617,target_lng=-80.1918,search_radius_m=5,altitude_m=10,rationale='test')
        app.S.drone=DroneState(latitude=25.7617,longitude=-80.1918,altitude_m=10,heading_deg=0)
        app.S.latest_frame=b'jpeg'
        release=threading.Event()
        def late_step(*args):
            release.wait(2)
            return SearchStep(action='move',move_distance_m=5,move_bearing_deg=90,observation='late')
        with patch('planner.next_search_step',side_effect=late_step), patch('planner.search_timeout',return_value=.03), \
             patch('app.iphone_fresh_frame',new_callable=AsyncMock,return_value=0), \
             patch('app.iphone_telemetry_ready',return_value=True), \
             patch('app.send_cmd',new_callable=AsyncMock) as send, \
             patch('app.iphone_stop',new_callable=AsyncMock) as stop:
            try:
                await app.run_mission()
                self.assertEqual(app.S.phase,'aborted')
                stop.assert_awaited_once()
                self.assertEqual([c.args[0] for c in send.await_args_list],['goto','gimbal'])
            finally:
                release.set()

    async def test_reset_cannot_restore_a_late_plan(self):
        app.S=app.State()
        started=threading.Event(); release=threading.Event()
        def plan(_):
            started.set(); release.wait(3)
            return MissionPlan(target_lat=25.7617,target_lng=-80.1918,search_radius_m=5,altitude_m=10,rationale='test')
        with patch('planner.plan_mission',side_effect=plan):
            task=asyncio.create_task(app.incident(FallEvent(latitude=25.7617,longitude=-80.1918)))
            try:
                await asyncio.to_thread(started.wait,2)
                self.assertTrue(app.S.planning)
                await app.reset()
            finally:
                release.set()
            with self.assertRaises(HTTPException) as error:
                await task
            self.assertEqual(error.exception.status_code,409)
        self.assertIsNone(app.S.plan)
        self.assertEqual(app.S.phase,'idle')


if __name__ == '__main__':
    unittest.main()
