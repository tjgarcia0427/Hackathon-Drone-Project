import { GuardianClient, toolResult } from './client.mjs';

const text = (maxLength = 2000) => ({ type: 'string', minLength: 1, maxLength });
const number = (minimum, maximum) => ({ type: 'number', minimum, maximum });
const uuid = { type: 'string', format: 'uuid' };
const observation = { observation_id: uuid };
const schema = (properties = {}, required = []) => ({ type: 'object', additionalProperties: false, properties, required });
export const definitions = [
  ['status', 'Read connection, pilot control gates, mission and recent Watch alerts. Does not acquire or renew control.', schema()],
  ['begin', 'Start one supervised mission; mode cannot exceed the server setting. Watch event pins the target to its measured location.', schema({ objective: text(), mode: { type: 'string', enum: ['observe', 'camera', 'flight'] }, target_lat: number(-84.999, 84.999), target_lng: number(-180, 180), watch_event_id: uuid }, ['objective', 'mode'])],
  ['observe', 'Receive the current JPEG as an image plus timestamped telemetry and mission memory. No image means no fresh frame; do not invent a view.', schema()],
  ['request_takeoff', 'Ask the iPhone pilot to confirm takeoff within 20 seconds. Does not arm AI. Waits for confirmed hover or failure. Never auto-retry.', schema(observation, ['observation_id'])],
  ['navigate', 'Navigate to the coordinates already pinned in this mission. Requires pilot-enabled flight at 5–30 m, fresh telemetry and the 35 m fence.', schema({ ...observation, altitude_m: number(5, 30) }, ['observation_id', 'altitude_m'])],
  ['move', 'Move at most 5 m at an absolute compass bearing. Requires a fresh image and unchanged aircraft pose; phone enforces motion limits.', schema({ ...observation, bearing: { ...number(0, 360), exclusiveMaximum: 360 }, distance_m: number(0, 5), note: text(1000) }, ['observation_id', 'bearing', 'distance_m', 'note'])],
  ['yaw', 'Turn relative to current heading, -180..180 degrees, after inspecting a fresh image. Requires flight enable.', schema({ ...observation, degrees: number(-180, 180), note: text(1000) }, ['observation_id', 'degrees', 'note'])],
  ['gimbal', 'Set camera pitch -90..0 degrees. Pilot must enable camera or flight control.', schema({ ...observation, pitch: number(-90, 0) }, ['observation_id', 'pitch'])],
  ['hold', 'Hold position using locally enabled flight control; waits for settled telemetry. Use stop to release control instead.', schema(observation, ['observation_id'])],
  ['return_home', 'Request DJI return-to-home and wait for landing confirmation. Pilot must supervise; STOP does not cancel DJI RTH.', schema(observation, ['observation_id'])],
  ['report_candidate', 'Save a possible person match for human review with the exact evidence image. Does not identify a person or automatically end/redirect the mission.', schema({ ...observation, bbox: { type: 'array', items: { type: 'integer', minimum: 0 }, minItems: 4, maxItems: 4 }, confidence: number(0, 1), note: text(1000) }, ['observation_id', 'bbox', 'confidence', 'note'])],
  ['remember', 'Save a compact search observation or coverage note in mission memory. Historical notes are never current telemetry.', schema({ note: text() }, ['note'])],
  ['memory', 'Read archived mission notes by mission ID; this cannot restore a control lease.', schema({ mission_id: uuid }, ['mission_id'])],
  ['stop', 'End the agent mission and release AI control. Cancels pending takeoff requests. Does not stop motors or cancel DJI RTH.', schema()],
];

export function register(api, factory = config => new GuardianClient(config)) {
  const sessions = new Map();
  const config = api.pluginConfig || {};
  for (const [shortName, description, parameters] of definitions) {
    const name = `guardian_${shortName}`;
    api.registerTool(ctx => {
      if (ctx.agentId !== (config.agentId || 'guardian-angel') || !ctx.sessionId) return null;
      return {
        name, label: name, description, parameters,
        async execute(_id, args, signal) {
          try {
            ctx.assertInvocationCurrent?.();
            const key = `${ctx.agentId}:${ctx.sessionId}`;
            if (!sessions.has(key)) {
              // Bounded cache; evicted sessions lose their lease and cannot auto-resume.
              if (sessions.size >= 32) sessions.delete(sessions.keys().next().value);
              sessions.set(key, factory(config));
            }
            const client = sessions.get(key);
            let result;
            if (shortName === 'status') result = await client.http('/agent/status', undefined, signal);
            else if (shortName === 'begin') result = await client.begin(args, signal);
            else if (shortName === 'observe') result = await client.observe(signal);
            else if (shortName === 'stop') result = await client.stop();
            else if (shortName === 'remember') result = await client.http('/agent/memory', { ...args, ...client.owned() }, signal);
            else if (shortName === 'memory') {
              if (!/^[0-9a-f-]{36}$/i.test(args.mission_id)) throw new Error('Invalid mission ID');
              result = await client.http(`/agent/memory/${args.mission_id}`, undefined, signal);
            } else result = await client.action(shortName, args, signal);
            return toolResult(result);
          } catch (error) {
            return { isError: true, content: [{ type: 'text', text: error.message }] };
          }
        },
      };
    }, { name, optional: true });
  }
}
