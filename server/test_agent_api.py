"""Agent HTTP / lifecycle tests with real validation and mocked aircraft commands."""
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from PIL import Image
import app
import agent_api
from models import DroneState


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.S = app.State()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict('os.environ', GA_AGENT_TOKEN='t'*40, GA_AGENT_MAX_MODE='flight',
                              GA_AGENT_MEMORY_DIR=self.tmp.name, GA_MISSION_DRIVER='openclaw')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.send = patch('app.send_cmd', new_callable=AsyncMock).start()
        self.send.return_value = {'ok': True}
        self.stop = patch('app.iphone_stop', new_callable=AsyncMock).start()
        self.wait_frame = patch('app.iphone_fresh_frame', new_callable=AsyncMock).start()
        self.addCleanup(patch.stopall)
        self.client = AsyncClient(transport=ASGITransport(app=app.app), base_url='http://test',
                                  headers={'Authorization': 'Bearer '+'t'*40})
        self.addAsyncCleanup(self.client.aclose)
        app.S.drone_ws = AsyncMock()
        app.S.drone = DroneState(latitude=25.7617, longitude=-80.1918, altitude_m=10,
                                 heading_deg=0, gimbal_pitch_deg=-60, battery_pct=90)
        app.S.home = (25.7617, -80.1918)
        app.S.agent_control = dict(camera_enabled=True, flight_enabled=True,
                                   takeoff_request_supported=True, takeoff_ready=True,
                                   home=list(app.S.home))
        image = Image.new('RGB', (640, 360), 'green')
        output = io.BytesIO()
        image.save(output, 'JPEG')
        app.S.latest_frame = output.getvalue()
        self.fresh()
        self.owner = None

    def fresh(self):
        app.S.telemetry_at = app.S.agent_control_at = app.S.latest_frame_at = time.monotonic()

    async def asyncTearDown(self):
        await agent_api.invalidate(app.S, 'test cleanup')
        await asyncio.sleep(0)

    async def begin(self, mode='flight', **kwargs):
        response = await self.client.post('/agent/mission', json=dict(objective='Find a person in blue', mode=mode, **kwargs))
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.owner = dict(mission_id=data['mission']['mission_id'], lease=data['lease'])
        return data

    async def observe(self):
        response = await self.client.post('/agent/observation', json=self.owner)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def act(self, action, obs=None, **args):
        obs = obs or await self.observe()
        body = dict(**self.owner, action_id=str(uuid4()), observation_id=obs['observation_id'], action=action, **args)
        return body, await self.client.post('/agent/action', json=body)

    async def test_auth_disabled_and_wrong_token(self):
        r = await self.client.get('/agent/status', headers={'Authorization':'bad'})
        self.assertEqual(r.status_code, 401)
        with patch.dict('os.environ', GA_AGENT_TOKEN=''):
            self.assertEqual((await self.client.get('/agent/status')).status_code, 503)

    async def test_observe_image_matches_metadata_and_hides_lease(self):
        await self.begin('observe')
        result = await self.observe()
        self.assertEqual(base64.b64decode(result['jpeg_base64']), app.S.latest_frame)
        self.assertEqual(result['frame']['sha256'], hashlib.sha256(app.S.latest_frame).hexdigest())
        self.assertNotIn(self.owner['lease'], json.dumps(result))
        _, r = await self.act('move', obs=result, bearing=0, distance_m=1)
        self.assertEqual(r.status_code, 403)
        self.send.assert_not_called()

    async def test_server_mode_ceiling(self):
        with patch.dict('os.environ', GA_AGENT_MAX_MODE='observe'):
            r = await self.client.post('/agent/mission', json={'objective':'test','mode':'flight'})
            self.assertEqual(r.status_code, 403)

    async def test_exclusive_with_legacy_and_other_agent(self):
        await self.begin()
        r = await self.client.post('/agent/mission', json={'objective':'second','mode':'flight'})
        self.assertEqual(r.status_code, 409)
        self.assertEqual((await self.client.post('/dispatch')).status_code, 409)
        self.assertEqual((await self.client.post('/incident', json={'latitude':25.7617,'longitude':-80.1918})).status_code, 409)
        with patch.dict('os.environ', DEV_COMMANDS='1'):
            self.assertEqual((await self.client.post('/dev/cmd',json={'action':'gimbal','pitch':-60})).status_code, 409)

    async def test_lower_altitude_envelope_and_unchanged_move_limit(self):
        await self.begin()
        app.S.drone.altitude_m = 1.2
        self.fresh()
        _, result = await self.act('move', bearing=0, distance_m=1)
        self.assertEqual(result.status_code, 202, result.text)
        await app.S.agent_api.task
        self.fresh()
        _, result = await self.act('move', bearing=0, distance_m=5.1)
        self.assertEqual(result.status_code, 422)
        app.S.drone.altitude_m = .99
        self.fresh()
        _, result = await self.act('move', bearing=0, distance_m=1)
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.send.await_count, 1)

    async def test_takeoff_authorization_and_diagnostics_are_observable(self):
        await self.begin()
        app.S.agent_control.update(takeoff_authorized=1, takeoff_authorization_seconds=250,
            takeoff_diagnostics={'messages':[{'code':123, 'reason':'test diagnostic'}]},
            flight_limits={'min_altitude_m':1, 'max_altitude_m':30})
        observation = await self.observe()
        self.assertEqual(observation['control']['takeoff_authorized'], 1)
        self.assertEqual(observation['control']['flight_limits']['min_altitude_m'], 1)
        self.assertEqual(observation['control']['takeoff_diagnostics']['messages'][0]['code'],123)

    async def test_takeoff_routes_request_and_waits_for_ack(self):
        await self.begin()
        gate = asyncio.Event()
        async def delayed(*args, **kw):
            await gate.wait()
            return {'ok':True}
        self.send.side_effect = delayed
        body, response = await self.act('request_takeoff')
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()['status'], 'pending')
        await asyncio.sleep(0)
        self.send.assert_awaited_once_with('request_takeoff', timeout=65)
        _, other = await self.act('hold')
        self.assertEqual(other.status_code, 409)
        gate.set()
        result = await self.client.post('/agent/actions/'+body['action_id']+'/wait', json=self.owner)
        self.assertEqual(result.json()['status'], 'completed')

    async def test_old_phone_and_unready_takeoff_rejected(self):
        await self.begin()
        app.S.agent_control['takeoff_request_supported'] = False
        _, result = await self.act('request_takeoff')
        self.assertEqual(result.status_code, 409)
        self.send.assert_not_called()

    async def test_duplicate_action_id_does_not_resend_and_mismatch_refused(self):
        await self.begin()
        body, first = await self.act('move', bearing=0, distance_m=1)
        await app.S.agent_api.task
        second = await self.client.post('/agent/action', json=body)
        self.assertEqual(second.json()['status'], 'completed')
        self.send.assert_awaited_once()
        body['distance_m'] = 2
        self.assertEqual((await self.client.post('/agent/action', json=body)).status_code, 409)

    async def test_old_observation_invalidated_on_action_completion(self):
        await self.begin()
        obs = await self.observe()
        _, result = await self.act('gimbal', obs=obs, pitch=-60)
        await app.S.agent_api.task
        _, result = await self.act('move', obs=obs, bearing=0, distance_m=1)
        self.assertEqual(result.status_code, 409)
        newer = await self.observe()
        self.assertFalse(newer['frame']['available'])  # no new JPEG after gimbal yet
        await asyncio.sleep(.02)
        self.fresh()
        self.assertTrue((await self.observe())['frame']['available'])

    async def test_expired_frame_and_pose_change_refused(self):
        await self.begin()
        obs = await self.observe()
        app.S.drone.latitude += .00005
        _, r = await self.act('move', obs=obs, bearing=0, distance_m=1)
        self.assertEqual(r.status_code, 409)
        app.S.drone.latitude -= .00005
        app.S.agent_api.observations[obs['observation_id']]['frame_at'] -= 31
        _, r = await self.act('move', obs=obs, bearing=0, distance_m=1)
        self.assertEqual(r.status_code, 409)

    async def test_strict_numbers_fence_battery_and_pilot_enable(self):
        await self.begin()
        for changes in ({'distance_m':True}, {'distance_m':6}, {'bearing':360}):
            args={'bearing':0,'distance_m':1, **changes}
            _, r = await self.act('move', **args)
            self.assertEqual(r.status_code, 422, r.text)
        app.S.drone.battery_pct=29
        _, r = await self.act('move', bearing=0,distance_m=1)
        self.assertEqual(r.status_code,409)
        app.S.drone.battery_pct=90
        app.S.agent_control['flight_enabled']=False
        _, r = await self.act('move', bearing=0,distance_m=1)
        self.assertEqual(r.status_code,409)
        self.send.assert_not_called()

    async def test_navigation_uses_mission_target_and_fresh_phone_home(self):
        await self.begin(target_lat=25.76171,target_lng=-80.1918)
        # Stale legacy S.home must never substitute for the phone's anchor.
        app.S.home=(0,0)
        _, r=await self.act('navigate',altitude_m=10)
        self.assertEqual(r.status_code,202,r.text)
        await app.S.agent_api.task
        self.send.assert_awaited_once_with('goto',timeout=120,lat=25.76171,lng=-80.1918,alt=10)

    async def test_target_outside_fence_refused(self):
        await self.begin(target_lat=25.77,target_lng=-80.1918)
        _, r=await self.act('navigate',altitude_m=10)
        self.assertEqual(r.status_code,422)
        self.send.assert_not_called()

    async def test_camera_without_gps_and_movement_without_image(self):
        await self.begin('camera')
        app.S.telemetry_at=0
        _, r=await self.act('gimbal',pitch=-45)
        self.assertEqual(r.status_code,202,r.text)
        await app.S.agent_api.task
        await self.client.post('/agent/stop')
        self.fresh()
        await self.begin()
        app.S.latest_frame_at=0
        _, r=await self.act('move',bearing=0,distance_m=1)
        self.assertEqual(r.status_code,409)

    async def test_candidate_saves_exact_evidence_without_marking_found(self):
        await self.begin('observe')
        body,r=await self.act('report_candidate',bbox=[10,20,90,80],confidence=.8,note='Possible blue shirt; operator review')
        self.assertEqual(r.status_code,202,r.text)
        self.assertTrue(r.json()['candidate']['human_review_required'])
        self.assertEqual((Path(self.tmp.name)/(body['action_id']+'.jpg')).read_bytes(),app.S.latest_frame)
        self.assertIsNone(app.S.found)
        self.send.assert_not_called()

    async def test_invalid_candidate_box_refused(self):
        await self.begin('observe')
        for bbox in ([0,0,900,500],[30,20,10,5],[True,0,10,20]):
            _,r=await self.act('report_candidate',bbox=bbox,confidence=.9,note='test')
            self.assertEqual(r.status_code,422)

    async def test_reset_cancels_inflight_and_rejects_old_owner(self):
        await self.begin()
        gate=asyncio.Event()
        self.send.side_effect=lambda *a,**kw: gate.wait()
        # AsyncMock needs an actual async side effect, not a returned coroutine.
        async def delayed(*a,**kw): await gate.wait()
        self.send.side_effect=delayed
        await self.act('move',bearing=0,distance_m=1)
        await asyncio.sleep(0)
        await self.client.post('/reset')
        self.assertFalse(agent_api.active(app.S))
        self.assertEqual((await self.client.post('/agent/observation',json=self.owner)).status_code,409)
        self.stop.assert_awaited()

    async def test_lease_expiry_and_memory_not_auto_resumed(self):
        await self.begin()
        app.S.agent_api.expires=0
        await asyncio.wait_for(app.S.agent_api.watchdog,2)
        self.assertFalse(agent_api.active(app.S))
        self.stop.assert_awaited_once()
        mission_id=self.owner['mission_id']
        app.S=app.State()
        result=await self.client.get('/agent/memory/'+mission_id)
        self.assertTrue(result.json()['historical'])
        self.assertFalse(agent_api.active(app.S))

    async def test_stale_cleanup_does_not_stop_new_mission(self):
        await self.begin()
        old=self.owner.copy()
        await self.client.post('/agent/stop')
        await self.begin()
        r=await self.client.post('/agent/release',json=old)
        self.assertEqual(r.status_code,409)
        self.assertTrue(agent_api.active(app.S))

    async def test_failed_command_returns_failure_not_success(self):
        await self.begin()
        self.send.side_effect=RuntimeError('Pilot declined takeoff')
        body,r=await self.act('request_takeoff')
        result=await self.client.post('/agent/actions/'+body['action_id']+'/wait',json=self.owner)
        self.assertEqual(result.json()['status'],'failed')
        self.assertIn('declined',result.json()['error'])

    async def test_action_budget_and_disk_failure_fail_closed(self):
        await self.begin()
        app.S.agent_api.steps=12
        _,r=await self.act('move',bearing=0,distance_m=1)
        self.assertEqual(r.status_code,409)
        app.S.agent_api.steps=0
        with patch.object(app.S.agent_api,'persist',side_effect=OSError('disk full')):
            _,r=await self.act('move',bearing=0,distance_m=1)
            self.assertEqual(r.status_code,503)
        self.send.assert_not_called()
        self.stop.assert_awaited()

    async def test_watch_agent_mode_never_calls_builtin_planner(self):
        now=datetime.now(timezone.utc).isoformat()
        event=dict(event_id=str(uuid4()),server_session=app.S.watch.session,source='watch_button',timestamp=now,
                   test_mode=False,latitude=25.76171,longitude=-80.1918,accuracy=5,location_timestamp=now)
        with patch('planner.plan_mission') as planner:
            r=await self.client.post('/watch/alerts',json=event)
            self.assertEqual(r.json()['status'],'awaiting_agent')
            planner.assert_not_called()
        data=await self.begin(watch_event_id=event['event_id'],target_lat=0,target_lng=0)
        self.assertEqual(data['mission']['target'],[event['latitude'],event['longitude']])
        # Location expires even while reasoning continues.
        app.S.watch.records[event['event_id']]['received_monotonic']-=121
        _,r=await self.act('navigate',altitude_m=10)
        self.assertEqual(r.status_code,409)


if __name__ == '__main__': unittest.main()


class EvidenceRouteTests(AgentTests):
    async def test_evidence_route_serves_saved_frame_and_404s_unknown(self):
        ident = uuid4()
        Path(self.tmp.name, f"{ident}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        r = await self.client.get(f"/agent/evidence/{ident}.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/jpeg")
        self.assertEqual(r.content, b"\xff\xd8\xff\xd9")
        self.assertEqual((await self.client.get(f"/agent/evidence/{uuid4()}.jpg")).status_code, 404)
        anon = AsyncClient(transport=ASGITransport(app=app.app), base_url='http://test')
        self.addAsyncCleanup(anon.aclose)
        self.assertEqual((await anon.get(f"/agent/evidence/{ident}.jpg")).status_code, 401)
