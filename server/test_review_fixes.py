"""Regression cases from the independent review; no AI account or aircraft."""
import asyncio
import io
import math
import os
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import ai_backends
import app
import geometry
import safety
from models import DroneState, MissionPlan, SearchStep
from sim_drone import Sim


def person(bbox=None, confidence=.9, moving=False, posture='prone'):
    return dict(bbox=bbox or [280,160,390,190],posture=posture,is_moving=moving,
                subject_confidence=confidence,reason='synthetic test')


def decision(candidates=None):
    return dict(action='found',confidence=.9,observation='synthetic test',chosen_index=0,
                candidates=candidates or [person()])


class SchemaAndBoundsTests(unittest.TestCase):
    def test_float_pixels_are_normalized_before_strict_validation(self):
        step=ai_backends.validate_decision(decision([person([10.0,20.2,90.8,120.0])]),SearchStep)
        self.assertEqual(step.candidates[0].bbox,[10,20,91,120])

    def test_pixel_strings_bools_and_nonfinite_numbers_still_fail(self):
        for value in ('10',True,math.nan,math.inf):
            with self.subTest(value=value),self.assertRaises(ai_backends.AIError):
                ai_backends.validate_decision(decision([person([value,20,90,120])]),SearchStep)

    def test_invalid_boxes_never_project_or_pass_found(self):
        for box in ([9000,20,9020,80],[-5,10,20,30],[10,10,10,30],[50,50,10,10],[0,0,640,361]):
            with self.subTest(box=box):
                step=ai_backends.validate_decision(decision([person(box)]),SearchStep)
                self.assertFalse(safety.check_found(step,frame_size=(640,360)).ok)
                self.assertIsNone(geometry.bbox_ground_point(box,640,360,altitude_m=10,heading_deg=0,gimbal_pitch_deg=-60))

    def test_reported_moving_subject_is_rejected(self):
        step=ai_backends.validate_decision(decision([person(moving=True)]),SearchStep)
        self.assertIn('moving',safety.check_found(step,frame_size=(640,360)).reason)

    def test_low_rated_single_subject_is_rejected(self):
        step=ai_backends.validate_decision(decision([person(confidence=.2)]),SearchStep)
        self.assertFalse(safety.check_found(step).ok)

    def test_both_api_providers_require_explicit_model(self):
        with patch.dict(os.environ,{},clear=True):
            for provider in ('anthropic_api','openai_api'):
                config=ai_backends.Settings(provider)
                self.assertEqual(config.public()['effective_model'],'Choose an API model')
                with self.assertRaisesRegex(ai_backends.AIError,'model ID'):
                    ai_backends.validate_setup(config)


class EvidenceTests(unittest.TestCase):
    def test_evidence_id_never_returns_a_different_decision_image(self):
        original=app.S
        try:
            app.S=app.State();app.S.step_frame=b'jpeg-one';app.S.last_step={'decision_id':'one'}
            with TestClient(app.app) as client:
                self.assertEqual(client.get('/step.jpg?decision_id=one').content,b'jpeg-one')
                app.S.step_frame=b'jpeg-two';app.S.last_step={'decision_id':'two'}
                self.assertEqual(client.get('/step.jpg?decision_id=one').status_code,409)
                self.assertEqual(client.get('/step.jpg?decision_id=two').content,b'jpeg-two')
        finally: app.S=original

    def test_dev_move_needs_fresh_navigation_and_valid_numbers(self):
        original=app.S
        try:
            app.S=app.State();app.S.home=(25.7617,-80.1918)
            app.S.drone=DroneState(latitude=25.7617,longitude=-80.1918,altitude_m=10,heading_deg=0)
            app.S.telemetry_at=time.monotonic()-10
            with patch.dict(os.environ,{'DEV_COMMANDS':'1'}),patch('app.send_cmd',new_callable=AsyncMock) as send,TestClient(app.app) as client:
                self.assertEqual(client.post('/dev/cmd',json={'action':'move','bearing':0,'dist':1}).status_code,409)
                app.S.telemetry_at=time.monotonic()
                for bearing,dist in ((True,1),(-1,1),(360,1),(0,-1),(0,6)):
                    self.assertEqual(client.post('/dev/cmd',json={'action':'move','bearing':bearing,'dist':dist}).status_code,400)
                send.assert_not_awaited()
        finally: app.S=original


class MissionFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_console_encoding_cannot_abort_a_mission_log(self):
        output=io.BytesIO()
        with patch('sys.stdout',io.TextIOWrapper(output,encoding='ascii',write_through=True)):
            app.log('✓ accepted / ✗ rejected')
            self.assertIn(b'accepted',output.getvalue())
        await asyncio.sleep(0)

    async def test_bystander_simulation_rejects_then_changes_view_then_finds(self):
        original=app.S
        app.S=app.State()
        home=(25.7617,-80.1918)
        sim=Sim(home,home,bystanders=2);sim.alt=10;sim.gimbal=-75
        app.S.plan=MissionPlan(target_lat=home[0],target_lng=home[1],search_radius_m=5,altitude_m=10,rationale='test')
        app.S.drone=DroneState(**sim.telemetry());app.S.home=home
        seen=[]
        async def fresh(_):
            app.S.latest_frame=sim.frame()
            return time.monotonic()
        def plan(*args):
            seen.append(list(args[3]))
            if len(seen)==1:
                return ai_backends.validate_decision(decision([person(confidence=.9),person([100.,30.,130.,110.],.85,posture='upright')]),SearchStep)
            if len(seen)==2:
                return SearchStep(action='yaw',yaw_deg=30,observation='Change view after rejection')
            return ai_backends.validate_decision(decision([person([280.,160.,390.,190.]),
                person([10.,30.,30.,110.],.1,True,'upright'),person([170.,75.,200.,170.],.1,True,'upright')]),SearchStep)
        try:
            with patch('planner.next_search_step',side_effect=plan),patch('app.iphone_fresh_frame',side_effect=fresh),\
                 patch('app.iphone_telemetry_ready',return_value=True),patch('app.send_cmd',new_callable=AsyncMock) as send,\
                 patch('app.iphone_stop',new_callable=AsyncMock) as stop:
                await app.run_mission()
            self.assertEqual(app.S.phase,'found')
            self.assertIn('REJECTED: ambiguous',seen[1][0])
            self.assertIn('Do not repeat',seen[1][0])
            self.assertEqual([c.args[0] for c in send.await_args_list],['goto','gimbal','yaw','hold'])
            self.assertEqual(app.S.found['people_in_frame'],3)
            self.assertTrue(app.S.last_step['decision_id'])
            stop.assert_not_awaited()
        finally:
            await asyncio.sleep(0)
            app.S=original


if __name__=='__main__': unittest.main()
