import { definePluginEntry } from 'openclaw/plugin-sdk/plugin-entry';
import { configSchema } from './config-schema.mjs';
import { register } from './tools.mjs';

export default definePluginEntry({
  id: 'guardian-angel',
  name: 'Guardian Angel',
  description: 'Supervised drone observations, mission memory and bounded commands',
  configSchema: { jsonSchema: configSchema },
  register,
});
