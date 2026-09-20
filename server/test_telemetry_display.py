import asyncio
import json
import time
import unittest
from fastapi import WebSocketDisconnect
import app
from telemetry_display import clean_readout, age_readout, LatestTelemetry


def readout(**changes):
    return dict(aircraft_connected=True,gps_ok=False,ground_anchor_ok=False,altitude_m=0,
                heading_deg=0,battery_pct=80,gimbal_pitch_deg=0,fc_age_ms=10,
                battery_age_ms=20,gimbal_age_ms=30) | changes


class ObservationTests(unittest.TestCase):
    def test_altitude_without_gps_and_valid_zero(self):
        data=clean_readout(readout())
        self.assertEqual(data['altitude_m'],0)
        self.assertEqual(data['heading_deg'],0)
        self.assertIsNone(data['latitude'])

    def test_stale_fields_expire_independently(self):
        data=age_readout(clean_readout(readout()),1.5)
        self.assertIsNone(data['altitude_m'])
        self.assertEqual(data['battery_pct'],80)
        self.assertIsNone(age_readout(data,5)['battery_pct'])

    def test_invalid_or_missing_values_do_not_turn_into_zero(self):
        data=clean_readout({'aircraft_connected':True,'altitude_m':float('nan'),'heading_deg':False,'fc_age_ms':0})
        self.assertIsNone(data['altitude_m'])
        self.assertIsNone(data['heading_deg'])
        self.assertIsNone(data['battery_pct'])
        json.dumps(data,allow_nan=False)


class Peer:
    def __init__(self, blocked=False):
        self.gate=asyncio.Event()
        if not blocked: self.gate.set()
        self.sent=[]
        self.closed=None
    async def close(self,code): self.closed=code
    async def send_text(self,text):
        await self.gate.wait()
        self.sent.append(json.loads(text))


class DroneSocket(Peer):
    def __init__(self):
        super().__init__()
        self.incoming=asyncio.Queue()
        self.accepted=asyncio.Event()
    async def accept(self): self.accepted.set()
    async def receive_text(self):
        value=await self.incoming.get()
        if value is None: raise WebSocketDisconnect()
        return json.dumps(value)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.S=app.State()
        self.ws=DroneSocket()
        self.connection=asyncio.create_task(app.ws_drone(self.ws))
        await self.ws.accepted.wait()
        await asyncio.sleep(0)

    async def asyncTearDown(self):
        tasks=list(app.S.telemetry_updates.tasks.values())
        for peer in tuple(app.S.dash): app.S.telemetry_updates.remove(peer)
        await asyncio.gather(*tasks,return_exceptions=True)
        await self.ws.incoming.put(None)
        await self.connection

    async def barrier(self):
        future=asyncio.get_running_loop().create_future()
        app.S.pending_acks['barrier']=future
        await self.ws.incoming.put({'type':'ack','cmd_id':'barrier','ok':True})
        await asyncio.wait_for(future,.3)
        app.S.pending_acks.pop('barrier')

    async def test_partial_readout_never_enables_navigation_or_sets_home(self):
        await self.ws.incoming.put({'type':'aircraft_status','aircraft':readout()})
        await self.barrier()
        self.assertEqual(app.S.display_readout()['altitude_m'],0)
        self.assertIsNone(app.S.drone)
        self.assertIsNone(app.S.home)
        self.assertFalse(app.iphone_telemetry_ready())

    async def test_partial_updates_do_not_refresh_old_navigation(self):
        await self.ws.incoming.put({'type':'telemetry','latitude':25.7,'longitude':-80.1,'altitude_m':10,'heading_deg':0})
        await self.barrier()
        self.assertEqual(app.S.home,(25.7,-80.1))
        original=app.S.telemetry_at
        await self.ws.incoming.put({'type':'aircraft_status','aircraft':readout()})
        await self.barrier()
        self.assertEqual(app.S.telemetry_at,original)
        self.assertEqual(app.S.drone.altitude_m,10)
        self.assertEqual(app.S.display_readout()['altitude_m'],0)
        app.S.telemetry_at=time.monotonic()-4
        self.assertFalse(app.iphone_telemetry_ready())

    async def test_slow_dashboard_does_not_block_telemetry_or_ack(self):
        slow=Peer(blocked=True)
        app.S.dash.add(slow)
        for i in range(100):
            await self.ws.incoming.put({'type':'telemetry','latitude':25+i/100000,'longitude':-80,'altitude_m':10,'heading_deg':0})
        await self.barrier()
        self.assertEqual(app.S.drone.latitude,25.00099)
        self.assertLessEqual(len(app.S.telemetry_updates.tasks),1)
        slow.gate.set()
        await asyncio.gather(*list(app.S.telemetry_updates.tasks.values()))
        self.assertEqual(slow.sent[-1]['drone']['latitude'],25.00099)
        self.assertLessEqual(len([x for x in slow.sent if x.get('type')=='telemetry']),2)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_dashboard_not_held_up_by_slow_dashboard(self):
        slow,fast=Peer(blocked=True),Peer()
        peers={slow,fast}
        channel=LatestTelemetry(peers,lambda:{'value':1},timeout=.05)
        channel.publish()
        await asyncio.sleep(.01)
        self.assertEqual(fast.sent,[{'value':1}])
        await asyncio.gather(*list(channel.tasks.values()))
        self.assertNotIn(slow,peers)
        self.assertEqual(slow.closed,1013)
        self.assertIn(fast,peers)


if __name__=='__main__': unittest.main()
