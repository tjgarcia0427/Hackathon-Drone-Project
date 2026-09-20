const assert=require('node:assert/strict');
const Display=require('./static/telemetry-display.js');
const d=new Display();
assert.equal(d.read(0),null);
const aircraft={aircraft_connected:true,gps_ok:false,ground_anchor_ok:false,latitude:null,longitude:null,
  altitude_m:0,heading_deg:0,battery_pct:78,gimbal_pitch_deg:0,fc_age_ms:10,battery_age_ms:20,gimbal_age_ms:30};
d.update({drone:null,aircraft},100);
assert.equal(d.read(100).altitude_m,0); // zero is a valid grounded altitude
assert.equal(d.read(100).latitude,null);
assert.equal(d.read(1600).altitude_m,null); // no stale zero or frozen last altitude
assert.equal(d.read(1600).battery_pct,78); // battery has its own freshness window
assert.equal(d.read(5200).battery_pct,null);
d.update({drone:{latitude:1,longitude:2,altitude_m:10},aircraft:{...aircraft,gps_ok:true,latitude:3,longitude:4,altitude_m:2}},6000);
assert.equal(d.read(6000).latitude,3);
assert.equal(d.read(6000).altitude_m,2);
d.update({drone_connected:false,drone:{latitude:1,longitude:2,altitude_m:10},aircraft:null},6100);
assert.equal(d.read(6100),null);
const legacy=new Display();
legacy.update({drone:{latitude:1,longitude:2,altitude_m:0,battery_pct:80}},100);
assert.equal(legacy.read(100).altitude_m,0);
assert.equal(legacy.read(1700).latitude,null);
legacy.update({drone:{latitude:1,longitude:2,altitude_m:0,battery_pct:80},navigation_age_ms:4000},1800);
assert.equal(legacy.read(1800).altitude_m,null); // a state refresh cannot revive old telemetry
console.log('Dashboard: grounded altitude, partial observations, aging, disconnect and legacy telemetry passed.');
