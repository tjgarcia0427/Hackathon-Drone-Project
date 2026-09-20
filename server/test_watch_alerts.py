"""Watch API integration tests: no live AI, account, network or aircraft required."""
import asyncio
from datetime import datetime, timedelta, timezone
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

import app
import watch_alerts
from models import DroneState, MissionPlan, FallEvent


class WatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.S = app.State()
        self.client = AsyncClient(transport=ASGITransport(app=app.app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        self.plan = MissionPlan(target_lat=25.7617, target_lng=-80.1918,
                                altitude_m=10, search_radius_m=5, rationale="test")
        self.planner = patch("planner.plan_mission", return_value=self.plan).start()
        self.auto = patch("app.AUTO_DISPATCH", False).start()
        self.addCleanup(patch.stopall)

    async def asyncTearDown(self):
        task = app.S.watch_plan_task
        if task and not task.done():
            await asyncio.wait_for(task, 3)
        await asyncio.sleep(0)

    def event(self, **changes):
        now = datetime.now(timezone.utc).isoformat()
        value = dict(event_id=str(uuid4()), server_session=app.S.watch.session,
                     source="watch_button", timestamp=now, test_mode=False,
                     latitude=25.7617, longitude=-80.1918, accuracy=5, location_timestamp=now)
        value.update(changes)
        return value

    async def send(self, event=None):
        return await self.client.post("/watch/alerts", json=event or self.event())

    async def planned(self):
        event = self.event()
        response = await self.send(event)
        self.assertEqual(response.status_code, 202, response.text)
        await app.S.watch_plan_task
        self.assertTrue(app.S.plan_verdict.ok)
        return event

    def aircraft(self):
        app.S.home = (25.7617, -80.1918)
        app.S.drone_ws = AsyncMock()
        app.S.drone = DroneState(latitude=25.7617, longitude=-80.1918,
                                 altitude_m=10, heading_deg=0, battery_pct=90)
        app.S.telemetry_at = time.monotonic()

    async def test_status_and_early_ack_while_model_is_blocked(self):
        info = (await self.client.get("/watch/status")).json()
        self.assertEqual(info["server_session"], app.S.watch.session)
        release = threading.Event()
        self.planner.side_effect = lambda _: (release.wait(3), self.plan)[1]
        event = self.event()
        try:
            response = await asyncio.wait_for(self.send(event), .5)
            self.assertEqual(response.status_code, 202)
            self.assertTrue(app.S.planning)
            self.assertEqual(response.json()["status"], "planning")
            self.assertIsNone(app.S.plan)
        finally:
            release.set()
        await app.S.watch_plan_task
        receipt = await self.client.get("/watch/alerts/" + event["event_id"])
        self.assertEqual(receipt.json()["status"], "planned")
        self.assertEqual(app.S.incident.event, "help_requested")

    async def test_concurrent_retries_plan_once_and_conflicting_id_is_rejected(self):
        event = self.event()
        responses = await asyncio.gather(self.send(event), self.send(event), self.send(event))
        self.assertEqual([r.status_code for r in responses], [202] * 3)
        self.assertEqual(sum(r.json()["duplicate"] for r in responses), 2)
        await app.S.watch_plan_task
        self.planner.assert_called_once()
        changed = {**event, "source": "watch_shake"}
        self.assertEqual((await self.send(changed)).status_code, 409)

    async def test_restart_replay_is_rejected(self):
        response = await self.send(self.event(server_session=str(uuid4())))
        self.assertEqual(response.status_code, 409)
        self.planner.assert_not_called()
        self.assertEqual(app.S.watch.records, {})

    async def test_test_mode_never_plans_even_with_auto_dispatch_or_active_mission(self):
        app.AUTO_DISPATCH = True
        app.S.phase, app.S.plan = "searching", self.plan
        response = await self.send(self.event(test_mode=True))
        self.assertEqual(response.json()["status"], "test_received")
        self.assertIs(app.S.plan, self.plan)
        self.assertEqual(app.S.phase, "searching")
        self.planner.assert_not_called()
        self.assertIsNone(app.S.search_task)

    async def test_location_problems_alert_operator_without_planning(self):
        old = (datetime.now(timezone.utc) - timedelta(seconds=16)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat()
        for changes in [dict(latitude=None, longitude=None, accuracy=None, location_timestamp=None),
                        dict(accuracy=21), dict(location_timestamp=old), dict(location_timestamp=future)]:
            with self.subTest(changes=changes):
                response = await self.send(self.event(**changes))
                self.assertEqual(response.status_code, 202, response.text)
                self.assertEqual(response.json()["status"], "location_rejected")
        self.planner.assert_not_called()
        self.assertEqual(app.S.phase, "idle")

    async def test_invalid_payloads_do_not_create_alerts(self):
        for changes in [dict(latitude=90), dict(accuracy=-1), dict(latitude=None),
                        dict(source="automatic_fall"), dict(test_mode="false"),
                        dict(timestamp="2026-01-01T12:00:00"), dict(unexpected="field"),
                        dict(timestamp=(datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat()),
                        dict(timestamp=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat())]:
            with self.subTest(changes=changes):
                self.assertEqual((await self.send(self.event(**changes))).status_code, 422)
        self.assertFalse(app.S.watch.records)
        self.planner.assert_not_called()

    async def test_busy_alert_does_not_replace_or_queue_mission(self):
        first = await self.planned()
        original = app.S.plan
        response = await self.send()
        self.assertEqual(response.json()["status"], "busy")
        self.assertIs(app.S.plan, original)
        self.assertEqual(app.S.watch_event_id, first["event_id"])
        self.planner.assert_called_once()

    async def test_target_uses_watch_coordinates_even_when_ai_changes_them(self):
        self.planner.return_value = self.plan.model_copy(update={"target_lat":0, "target_lng":0})
        event = await self.planned()
        self.assertEqual((app.S.plan.target_lat, app.S.plan.target_lng), (event["latitude"], event["longitude"]))

    async def test_reset_during_planning_discards_result_and_retry_does_not_replan(self):
        started, release = threading.Event(), threading.Event()
        def blocked(_):
            started.set(); release.wait(3)
            return self.plan
        self.planner.side_effect = blocked
        event = self.event()
        try:
            await self.send(event)
            await asyncio.to_thread(started.wait, 2)
            await self.client.post("/reset")
        finally:
            release.set()
        await app.S.watch_plan_task
        self.assertIsNone(app.S.plan)
        self.assertEqual(app.S.phase, "idle")
        retry = await self.send(event)
        self.assertTrue(retry.json()["duplicate"])
        self.assertEqual(retry.json()["status"], "cancelled")
        self.planner.assert_called_once()

    async def test_dispatch_rechecks_battery_fence_and_destination(self):
        await self.planned()
        self.aircraft()
        app.S.drone.battery_pct = 20
        self.assertEqual((await self.client.post("/dispatch")).status_code, 400)
        app.S.drone.battery_pct = 90
        app.S.plan.search_radius_m = 40
        self.assertEqual((await self.client.post("/dispatch")).status_code, 400)
        app.S.plan.search_radius_m = 5
        app.S.plan.target_lat += .00001
        response = await self.client.post("/dispatch")
        self.assertEqual(response.status_code, 400)
        self.assertIn("match", response.json()["detail"])

    async def test_dispatch_expiry_and_success(self):
        event = await self.planned()
        self.aircraft()
        record = app.S.watch.records[event["event_id"]]
        record["received_monotonic"] -= 121
        self.assertEqual((await self.client.post("/dispatch")).status_code, 409)
        record["received_monotonic"] = time.monotonic()
        with patch("app.run_mission", new_callable=AsyncMock) as mission:
            response = await self.client.post("/dispatch")
            self.assertEqual(response.status_code, 200, response.text)
            await app.S.search_task
            mission.assert_awaited_once()
        self.assertEqual(record["status"], "dispatched")
        self.assertEqual((await self.client.post("/dispatch")).status_code, 409)

    async def test_model_failure_retains_receipt_and_cannot_dispatch(self):
        self.planner.side_effect = RuntimeError("model unavailable")
        event = self.event()
        response = await self.send(event)
        self.assertEqual(response.status_code, 202)
        await app.S.watch_plan_task
        self.assertEqual(app.S.watch.records[event["event_id"]]["status"], "failed")
        self.assertEqual((await self.client.post("/dispatch")).status_code, 400)

    async def test_retained_duplicate_after_trigger_age_limit_and_capacity(self):
        event = self.event(test_mode=True)
        await self.send(event)
        with patch.object(watch_alerts.WatchAlert, "age", return_value=70):
            self.assertTrue((await self.send(event)).json()["duplicate"])
        with patch("watch_alerts.MAX_RECORDS", 1):
            self.assertEqual((await self.send(self.event(test_mode=True))).status_code, 429)
        self.assertIn(event["event_id"], app.S.watch.records)

    async def test_superseded_watch_plan_cannot_be_retried_as_new(self):
        event = await self.planned()
        await app.incident(FallEvent(latitude=25.7617, longitude=-80.1918))
        self.assertEqual(app.S.watch.records[event["event_id"]]["status"], "cancelled")
        self.assertIsNone(app.S.watch_event_id)
        self.assertTrue((await self.send(event)).json()["duplicate"])


if __name__ == "__main__":
    unittest.main()
