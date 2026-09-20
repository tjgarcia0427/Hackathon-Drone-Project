"""Apply the iPhone bridge integration to server/app.py, preserving other files.

Default: print unified diff only. --apply: save a backup, then write.
Targets the initial project scaffold (15359dc); unexpected structure fails closed.
"""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import sys
from pathlib import Path

MARKER = '# Guardian Angel iPhone integration v1'
BASE_AST_SHA256 = '0896ecc635cb1d6dd5394651aacce9c782c93e53f8bd15c3a70c7840e7b0fd73'
HELPERS = '''
# Guardian Angel iPhone integration v1
async def iphone_stop(reason: str) -> None:
    """Release app flight control. Does not cancel DJI RTH or stop motors."""
    ws = S.drone_ws
    if ws is not None:
        try:
            await asyncio.wait_for(ws.send_text(json.dumps({
                "type": "cmd", "cmd_id": uuid.uuid4().hex[:8], "action": "stop",
            })), 2.0)
        except Exception as exc:
            log(f"stop delivery failed; pilot intervention required: {exc}")
    log(f"AI control release requested: {reason}")


async def iphone_cancel_mission() -> None:
    task = S.search_task
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def iphone_fresh_frame(after: float) -> float:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        received = getattr(S, "latest_frame_at", 0.0)
        if received > after and time.monotonic() - received < 3.0:
            return received
        await asyncio.sleep(0.1)
    raise RuntimeError("no fresh camera frame after the last action")


def iphone_telemetry_ready() -> bool:
    return S.drone is not None and time.monotonic() - getattr(S, "telemetry_at", 0.0) < 3.0

'''

SEND = '''async def send_cmd(action: str, timeout: float = 25.0, **params: Any) -> dict:
    ws = S.drone_ws
    if ws is None:
        raise RuntimeError("no drone connected")
    cmd_id = uuid.uuid4().hex[:8]
    fut = asyncio.get_running_loop().create_future()
    S.pending_acks[cmd_id] = fut
    try:
        await asyncio.wait_for(ws.send_text(json.dumps({
            "type": "cmd", "cmd_id": cmd_id, "action": action,
            "expires_at_ms": int((time.time() + 5.0) * 1000), **params,
        })), 3.0)
        log(f"→ drone {action} {params}", cmd_id=cmd_id)
        return await asyncio.wait_for(fut, timeout)
    except Exception:
        if action != "rtl":
            await iphone_stop(f"{action} failed or timed out")
        raise
    finally:
        S.pending_acks.pop(cmd_id, None)
'''
ABORT = '''async def abort() -> dict:
    await iphone_cancel_mission()
    S.phase = "aborted"
    try:
        # iPhone acknowledges actual landing, not just SDK acceptance.
        await send_cmd("rtl", timeout=180)
    except Exception as exc:
        log(f"abort: return not completed ({exc}); pilot must intervene")
        await push_state()
        return {"ok": False, "error": str(exc)}
    await push_state()
    return {"ok": True}
'''
RESET = '''async def reset() -> dict:
    S.frame_epoch = getattr(S, "frame_epoch", 0) + 1
    await iphone_cancel_mission()
    await iphone_stop("mission reset")
    S.incident = S.plan = S.plan_verdict = S.found = None
    S.history, S.phase = [], "idle"
    S.latest_frame = S.latest_detection = None
    S.latest_frame_at = 0.0
    await push_state()
    return {"ok": True, "note": "AI control release requested; re-enable locally"}
'''
FRAME = '''async def frame(request: Request) -> dict:
    """Publish a matched frame/detection pair, ordered by receive time."""
    if S.drone_ws is None:
        raise HTTPException(409, "no connected drone")
    epoch = getattr(S, "frame_epoch", 0)
    received = time.monotonic()
    data = await request.body()
    if not data or len(data) > 2_000_000:
        raise HTTPException(400, "expected JPEG under 2 MB")
    detection = await asyncio.to_thread(detector.detect, data)
    if S.drone_ws is None or epoch != getattr(S, "frame_epoch", 0):
        raise HTTPException(409, "frame belongs to an old connection or reset")
    if received > getattr(S, "latest_frame_at", 0.0):
        S.latest_frame, S.latest_detection = data, detection
        S.latest_frame_at = received
        await broadcast({"type": "frame", "detection": detection})
    return {"ok": True, "detection": detection}
'''

def replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f'Expected one integration point: {before[:100]!r}; review app.py manually')
    return text.replace(before, after, 1)

def replace_function(source: str, name: str, replacement: str) -> str:
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name==name]
    if len(nodes)!=1: raise ValueError(f'Expected async function {name}')
    node=nodes[0]; lines=source.splitlines(keepends=True)
    return ''.join(lines[:node.lineno-1])+replacement.rstrip()+'\n'+''.join(lines[node.end_lineno:])

def patch(source: str) -> str:
    if MARKER in source: raise ValueError('iPhone patch already present; no changes made')
    syntax=ast.parse(source)
    digest=hashlib.sha256(ast.dump(syntax,include_attributes=False).encode()).hexdigest()
    if digest != BASE_AST_SHA256:
        raise ValueError('Server code differs from scaffold 15359dc. No edits made; merge iphone-integration.patch manually to preserve teammate changes.')
    for name in ('S.pending_acks','S.drone_ws','S.latest_frame','S.latest_detection','S.search_task','S.home'):
        if name not in source: raise ValueError(f'Missing expected state member {name}')
    source=replace_function(source,'send_cmd',HELPERS+SEND)
    source=replace_function(source,'abort',ABORT)
    source=replace_function(source,'reset',RESET)
    source=replace_function(source,'frame',FRAME)
    source=replace_once(source,'await send_cmd("rtl", timeout=5)','await send_cmd("rtl", timeout=180)')
    source=replace_once(source,'        await asyncio.sleep(1.2)  # let a fresh frame land',
        '        frame_at = await iphone_fresh_frame(time.monotonic())')
    source=replace_once(source,'            if S.drone is None:', '            if not iphone_telemetry_ready():')
    source=replace_once(source,'            verdict = safety.check_step(step, S.drone, *home, step_no)',
        '            if not iphone_telemetry_ready() or time.monotonic() - frame_at > 10.0:\n'
        '                raise RuntimeError("planner result based on stale frame/telemetry")\n'
        '            verdict = safety.check_step(step, S.drone, *home, step_no)')
    source=replace_once(source,'        log(f"mission error: {e}")',
        '        log(f"mission error: {e}")\n        await iphone_stop("mission failed")')
    source=replace_once(source,'    S.phase = "dispatched"',
        '    if not iphone_telemetry_ready():\n        raise HTTPException(409, "fresh aircraft telemetry required")\n'
        '    if S.home is None or not (5 <= S.plan.altitude_m <= 30) or safety.haversine_m(*S.home, S.plan.target_lat, S.plan.target_lng) > 35:\n'
        '        raise HTTPException(400, "iPhone demo requires target within 35 m of launch and altitude 5..30 m")\n'
        '    S.phase = "dispatched"')
    source=replace_once(source,'    await ws.accept()\n    S.drone_ws = ws',
        '    await ws.accept()\n'
        '    if S.drone_ws is not None:\n        await ws.close(code=1008, reason="one drone connection allowed")\n        return\n'
        '    S.frame_epoch = getattr(S, "frame_epoch", 0) + 1\n'
        '    S.drone = None\n    S.telemetry_at = 0.0\n'
        '    S.latest_frame = S.latest_detection = None\n    S.latest_frame_at = 0.0\n'
        '    S.drone_ws = ws')
    source=replace_once(source,'            if t == "telemetry":',
        '            if t == "telemetry":\n                S.telemetry_at = time.monotonic()')
    source=replace_once(source,'                    S.home = (S.drone.latitude, S.drone.longitude)',
        '                    S.home = (float(msg.get("home_latitude", S.drone.latitude)), float(msg.get("home_longitude", S.drone.longitude)))')
    source=replace_once(source,'        S.drone_ws = None\n        log("drone disconnected")',
        '        await iphone_cancel_mission()\n'
        '        S.drone_ws = None\n        S.telemetry_at = 0.0\n'
        '        S.frame_epoch = getattr(S, "frame_epoch", 0) + 1\n'
        '        for fut in list(S.pending_acks.values()):\n'
        '            if not fut.done():\n                fut.set_exception(RuntimeError("drone disconnected"))\n'
        '        log("drone disconnected")')
    ast.parse(source)
    return source

def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app',type=Path,help='Path to Hackathon-Drone-Project/server/app.py')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    original=args.app.read_bytes()
    before=original.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    try: after=patch(before)
    except ValueError as exc: parser.exit(1,f'{exc}\n')
    print(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(args.app),tofile=str(args.app)+' (iPhone)')))
    if args.apply:
        backup=args.app.with_suffix(args.app.suffix+'.before-iphone')
        if backup.exists(): parser.exit(1,f'Backup already exists: {backup}. No files changed.\n')
        if args.app.read_bytes()!=original:
            parser.exit(1,'The file changed during review. No files changed; run the preview again.\n')
        backup.write_bytes(original)
        args.app.write_text(after,encoding='utf-8',newline='\n')
        print(f'Applied. Original saved as {backup}')
    else: print('Preview only. Add --apply to save after reviewing the diff.')

if __name__=='__main__': main()
