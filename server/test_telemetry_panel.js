const assert=require('node:assert/strict');
const Display=require('./static/telemetry-display.js');
const Panel=require('./static/telemetry-panel.js');
const d=new Display();
const a={aircraft_connected:true,gps_ok:true,ground_anchor_ok:true,altitude_m:0,latitude:25.761701,longitude:-80.191801,
  heading_deg:0,gimbal_pitch_deg:0,battery_pct:80,flying:false,gps_signal_level:5,satellites:16,fc_age_ms:0,battery_age_ms:0,gimbal_age_ms:0};
d.update({aircraft:a},100);
const fields=Object.fromEntries(Panel.fields(d.read(100)).map(([key,value])=>[key,value]));
assert.equal(fields.Altitude,'0.0 m');assert.equal(fields.Latitude,'25.761701');assert.equal(fields.Longitude,'-80.191801');
assert.equal(fields['Flight state'],'On ground');assert.equal(fields['GPS signal'],'5 / 5');
const element={innerHTML:''},badge={dataset:{}};
Panel.render(element,badge,d.read(1700));
assert.match(element.innerHTML,/Altitude<\/dt><dd>—/);assert.match(badge.textContent,/stale/);
Panel.render(element,badge,null);assert.match(badge.textContent,/Waiting/);
assert.equal(Panel.fields(null).length,12);
assert.equal(Panel.fields({gps_signal_level:6}).find(row=>row[0]==='GPS signal')[1],'No signal');
assert.equal(Panel.fields({gps_signal_level:255}).find(row=>row[0]==='GPS signal')[1],'—');
console.log('Aircraft overview: altitude zero, coordinate precision, key stats, stale and disconnected states passed.');
