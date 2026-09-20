export const configSchema = {
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "serverUrl": {
      "type": "string",
      "default": "http://127.0.0.1:8000"
    },
    "tokenEnv": {
      "type": "string",
      "default": "GA_AGENT_TOKEN"
    },
    "agentId": {
      "type": "string",
      "default": "guardian-angel"
    }
  }
};
