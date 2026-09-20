import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { GuardianClient, toolResult } from '../client.mjs';
import { definitions, register } from '../tools.mjs';

const owner = { mission_id:'a0d0b5f0-b2ed-459f-85fe-bf515c387d5c', lease:'l'.repeat(64) };
const token = 't'.repeat(40);
const response = (data, ok=true) => ({ ok, status:ok?200:409, json:async()=>data });
const client = fn => new GuardianClient({serverUrl:'http://127.0.0.1:8000'}, {GA_AGENT_TOKEN:token}, fn);

test('manifest exactly matches optional runtime tools', () => {
  const manifest=JSON.parse(fs.readFileSync(new URL('../openclaw.plugin.json',import.meta.url)));
  const registered=[];
  register({pluginConfig:{},registerTool:(factory,options)=>registered.push({factory,options})});
  assert.deepEqual(manifest.contracts.tools,definitions.map(d=>'guardian_'+d[0]));
  for(const item of registered) {
    assert.equal(item.options.optional,true);
    assert.equal(manifest.toolMetadata[item.options.name].optional,true);
    assert.equal(item.factory({agentId:'other',sessionId:'s'}),null);
    assert.equal(item.factory({agentId:'guardian-angel'}),null);
    assert.ok(item.factory({agentId:'guardian-angel',sessionId:'s'}).parameters);
  }
});

test('observation returns real image block and no duplicate base64 in text/details',()=>{
  const result=toolResult({observation_id:'obs',jpeg_base64:'aGVsbG8=',frame:{width:640}});
  assert.deepEqual(result.content[1],{type:'image',data:'aGVsbG8=',mimeType:'image/jpeg'});
  assert.doesNotMatch(result.content[0].text,/aGVsbG8/);
  assert.equal(result.details.jpeg_base64,undefined);
});

test('origin and credentials are configured outside model arguments; redirects forbidden', async()=>{
  assert.throws(()=>client(()=>{}).owned(),/Start a mission/);
  for(const serverUrl of ['file:///secret','https://user:pass@example.com','http://localhost:8000/path','http://localhost:8000/?key=x']) {
    assert.throws(()=>new GuardianClient({serverUrl},{GA_AGENT_TOKEN:token}),/origin/);
  }
  assert.throws(()=>new GuardianClient({},{}),/environment/);
  const c=client(async(url,request)=>{
    assert.equal(request.redirect,'error');
    assert.equal(request.headers.Authorization,'Bearer '+token);
    return response({mission:{mission_id:owner.mission_id},lease:owner.lease});
  });
  const result=await c.begin({objective:'demo',mode:'observe'});
  assert.equal(result.lease,undefined);
  assert.deepEqual(c.owner,owner);
});

test('takeoff is request-only, polls same ID, no success until completion',async()=>{
  const requests=[];
  const c=client(async(url,req)=>{
    const body=JSON.parse(req.body);requests.push({url,body});
    return response(requests.length===1?{status:'pending',action_id:body.action_id}:{status:'completed',ack:{ok:true}});
  });
  c.owner=owner;
  const r=await c.action('request_takeoff',{observation_id:owner.mission_id});
  assert.equal(r.status,'completed');
  assert.equal(requests[0].body.action,'request_takeoff');
  assert.ok(requests[1].url.endsWith('/actions/'+requests[0].body.action_id+'/wait'));
  assert.equal(requests.length,2);
});

test('uncertain delivery uses scoped release, no action retry or global stop',async()=>{
  const paths=[];
  const c=client(async(url,req)=>{
    paths.push(new URL(url).pathname);
    if(paths.length===1)throw new Error('network lost');
    assert.deepEqual(JSON.parse(req.body),owner);
    return response({ok:true});
  });
  c.owner=owner;
  await assert.rejects(()=>c.action('move',{observation_id:owner.mission_id,bearing:0,distance_m:1}),/network lost/);
  assert.deepEqual(paths,['/agent/action','/agent/release']);
  assert.equal(c.owner,null);
});

test('cancellation sends release with an independent signal',async()=>{
  const cancel=new AbortController();cancel.abort();
  const c=client(async(url,req)=>{
    if(url.endsWith('/action')) { assert.equal(req.signal.aborted,true); throw new Error('aborted'); }
    assert.ok(url.endsWith('/release'));assert.equal(req.signal.aborted,false);
    return response({ok:true});
  });
  c.owner=owner;
  await assert.rejects(()=>c.action('gimbal',{pitch:-45},cancel.signal),/aborted/);
});

test('server command failure remains a tool error',()=>{
  assert.equal(toolResult({status:'failed',error:'pilot declined'}).isError,true);
  assert.equal(toolResult({status:'cancelled'}).isError,true);
});

test('leases are isolated by session ID, and missing context fails closed',async()=>{
  const registered=new Map();let clients=0;
  register({pluginConfig:{},registerTool:(factory,options)=>registered.set(options.name,factory)},()=>{
    clients++;return {begin:async()=>({mission_id:'m'+clients}),owned(){throw new Error('no lease');},observe:async()=>({frame:{available:false}})};
  });
  const make=(tool,s)=>registered.get(tool)({agentId:'guardian-angel',sessionId:s});
  await make('guardian_begin','one').execute('id',{objective:'demo'});
  await make('guardian_observe','one').execute('id',{});
  assert.equal(clients,1);
  await make('guardian_observe','two').execute('id',{});
  assert.equal(clients,2);
});
