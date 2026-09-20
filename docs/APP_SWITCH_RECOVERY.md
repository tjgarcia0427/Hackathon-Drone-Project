# Demo hotfix: return from DJI Fly while airborne

Pull the updated branch and **rebuild/reinstall the iPhone app from Xcode while the aircraft is grounded**. This phone change is on both `main` and `ui-redesign`. Continue using the server from `main`; this hotfix does not require a server change or database migration.

## Demo sequence

1. Connect the aircraft/controller/iPhone. Take off with the pilot in DJI Fly if Guardian Angel's DJI takeoff call returns `-1008`.
2. Return to Guardian Angel, start the real bridge if needed, and reconnect the server. The aircraft must have strong GPS and a valid DJI home point; stay close to the launch point.
3. Wait for **Ground anchor OK**. After an airborne reconnect, the log says **Airborne: ground anchor recovered from the aircraft's DJI home point. Reconnect server, then tap Enable flight.** The phone no longer needs to have recorded an anchor before takeoff.
4. With the pilot hovering at 5–30 m, battery at least 30%, tap **Enable flight**. The extra confirmation/checklist is removed. If camera control is enabled, stop it first; on the redesigned UI the first flight-button tap stops camera control and the next enables flight.
5. Wait for the flight-enabled log. Start a new OpenClaw flight-mode mission, get a fresh observation and request one 1 m move in a clear direction, then hold. Set `GA_AGENT_MAX_MODE=flight` on the main server before the test. Old agent ownership is invalidated by the app-switch disconnect.

The phone's recovery accepts DJI's current home point within 40 m of the aircraft; agent movement stays within the server's 35 m boundary. It does not substitute the current airborne position for the launch position. Missing/invalid home, weak GPS, stale telemetry, low battery and out-of-envelope flight still block control. Stay in Guardian Angel once AI flight is enabled; switching away releases control again. STOP and pilot takeover remain available.

## Why no database is needed for this blocker

DJI retains the home point on the aircraft while the phone changes apps. On a fresh SDK state callback, Guardian Angel reads `isHomeLocationSet` and `homeLocation` from that connected aircraft. This recovers the coordinate after the SDK disconnect/reconnect without trusting an old saved "anchor OK" flag, another aircraft's cached location, or server history. The display still calls the recovered reference a ground anchor.

This supersedes earlier instructions that require Guardian Angel to witness the drone on the ground. It also supersedes the older separate Enable flight confirmation/checklist. It does not make `-1008` itself disappear or automatically restore AI authority. No persistent server database changes are part of this hotfix.

## Review and test handoff

The teammate's airborne-home recovery on `ui-redesign` was preserved and factored into `GroundAnchor.h`, then added to `main`. Native tests cover recovery at low hover, retaining the original launch coordinates, GPS/home validation and the unchanged flight envelope. The preservation test allows only the explicit recovery addition; flight execution and OcuSync video code remain compared with the hardware-tested baseline. UIKit smoke tests exercise direct enable, camera-mode STOP, stale/disconnected rejection and log STOP. The two branches retain their existing interfaces.

Mac CI compiles and links the real DJI app; hardware validation still requires the team's aircraft. If recovery stays waiting, inspect GPS/home availability and distance. Rebuild the updated branch first; pulling server code alone cannot change the installed phone app.
