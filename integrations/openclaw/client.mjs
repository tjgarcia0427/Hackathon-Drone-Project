import { randomUUID } from 'node:crypto';

// One instance per OpenClaw conversation. Credentials and lease never reach the model.
export class GuardianClient {
  constructor(config, env = process.env, fetchImpl = fetch) {
    const url = new URL(config.serverUrl || 'http://127.0.0.1:8000');
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
      throw new Error('serverUrl must be an HTTP(S) origin with no credentials, path, query or fragment');
    }
    this.origin = url.origin;
    this.token = env[config.tokenEnv || 'GA_AGENT_TOKEN'];
    if (!this.token || this.token.length < 32) throw new Error('Configure the agent token in the Gateway process environment');
    this.fetch = fetchImpl;
    this.owner = null;
    this.busy = false;
  }
  async http(path, body, signal) {
    const timeout = AbortSignal.timeout(15000);
    const response = await this.fetch(this.origin + path, {
      method: body === undefined ? 'GET' : 'POST', redirect: 'error',
      headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(`Guardian Angel ${response.status}: ${JSON.stringify(data.detail || 'request failed')}`);
    return data;
  }
  owned() {
    if (!this.owner) throw new Error('Start a mission in this OpenClaw conversation first');
    return this.owner;
  }
  async begin(args, signal) {
    const data = await this.http('/agent/mission', args, signal);
    this.owner = { mission_id: data.mission.mission_id, lease: data.lease };
    return data.mission;
  }
  async observe(signal) { return this.http('/agent/observation', this.owned(), signal); }
  async stop() {
    // STOP works even after a restart lost the in-process lease; never needs an image.
    const result = await this.http('/agent/stop', {});
    this.owner = null;
    return result;
  }
  async action(action, args, signal) {
    if (this.busy) throw new Error('Wait for the current drone tool to finish');
    this.busy = true;
    try {
      // This ID is never regenerated during polling. An uncertain delivery is
      // stopped, never retried as a new physical action.
      const body = { ...args, ...this.owned(), action, action_id: randomUUID() };
      let result = await this.http('/agent/action', body, signal);
      const deadline = Date.now() + 195000;
      while (result.status === 'pending') {
        if (Date.now() > deadline) throw new Error('Action deadline expired');
        result = await this.http(`/agent/actions/${body.action_id}/wait`, this.owned(), signal);
      }
      if (result.status === 'failed' || result.status === 'cancelled') {
        try { await this.http('/agent/release', this.owner); this.owner = null; }
        catch { result.error = `${result.error || result.status}; release unconfirmed, pilot must verify aircraft state`; }
      }
      return result;
    } catch (error) {
      // A rejected/aborted or uncertain tool invocation ends this control session.
      // Use an independent signal so cancellation of reasoning cannot cancel STOP.
      if (this.owner) {
        try { await this.http('/agent/release', this.owner); this.owner = null; }
        catch { throw new Error(`${error.message}; STOP delivery unconfirmed. Pilot must use RC. Lease will expire.`); }
      }
      throw error;
    } finally { this.busy = false; }
  }
}

export function toolResult(data) {
  const { jpeg_base64, ...metadata } = data;
  const content = [{ type: 'text', text: JSON.stringify(metadata) }];
  if (jpeg_base64) content.push({ type: 'image', data: jpeg_base64, mimeType: 'image/jpeg' });
  return { content, details: metadata, ...(data.status === 'failed' || data.status === 'cancelled' ? { isError: true } : {}) };
}
