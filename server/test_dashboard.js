/* Execute the actual dashboard scripts with DOM/network stubs. No live AI/drone. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),draws=[];let now=100,socket;const timers=[];
function node(){return {innerHTML:'',textContent:'',style:{},dataset:{},hidden:false,naturalWidth:640,naturalHeight:360,clientWidth:640,clientHeight:360,
  classList:{add(){},remove(){}},replaceChildren(){},append(){},insertAdjacentHTML(){},
  getContext:()=>({clearRect(){draws.length=0;},strokeRect(...args){draws.push(args);},fillText(){}}),
  set src(v){this.currentSrc=v;},get src(){return this.currentSrc;}};}
const get=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
const context={document:{getElementById:get,createElement:node},performance:{now:()=>now},Date,URL,console,
  location:{protocol:'http:',host:'localhost:8000',href:'http://localhost:8000/'},setInterval:fn=>timers.push(fn),setTimeout(){},
  WebSocket:class{constructor(){socket=this;}},addEventListener(){}};
context.window=context;vm.createContext(context);
const root=path.join(__dirname,'static');
for(const file of ['telemetry-display.js','telemetry-panel.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
vm.runInContext([...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n'),context);
const send=message=>socket.onmessage({data:JSON.stringify(message)});
send({type:'telemetry',aircraft:{aircraft_connected:true,gps_ok:true,altitude_m:0,latitude:25.761701,longitude:-80.191801,
  battery_pct:80,heading_deg:0,gimbal_pitch_deg:0,fc_age_ms:0,battery_age_ms:0,gimbal_age_ms:0}});
assert.match(get('aircraft-stats').innerHTML,/Altitude<\/dt><dd>0\.0 m/);
assert.match(get('aircraft-stats').innerHTML,/25\.761701/);
now=1800;for(const tick of timers)tick();
assert.match(get('aircraft-stats').innerHTML,/Altitude<\/dt><dd>—/);
if(html.includes('decision-image')) {
  const st={type:'step',decision_id:'one',judged_at:1,frame:[640,360],ok:false,reason:'ambiguous',step:{action:'found',chosen_index:0},
    candidates:[{index:0,bbox:[20,30,60,70],posture:'prone',chosen:true,subject_confidence:.9}]};
  send(st);assert.equal(draws.length,0);
  const oldLoad=get('decision-image').onload;
  send({...st,decision_id:'two'});oldLoad();assert.equal(draws.length,0); // late image must not draw wrong boxes
  get('decision-image').onload();assert.equal(draws.length,1);
  assert.match(get('decision-status').textContent,/rejected: ambiguous/);
  const evidence=get('decision-image').src;
  send({type:'frame',detection:null});
  assert.equal(get('decision-image').src,evidence); // live frames stay separate
  assert.match(get('cam').src,/frame\.jpg/);
}
console.log('Production dashboard scripts: top-level stats, stale expiry, and versioned evidence separation passed.');
