/* One presentation for both dashboard themes. Unknown values never become zero. */
(function(root) {
  const number=(v,places=1,suffix='')=>Number.isFinite(v)?v.toFixed(places)+suffix:'—';
  const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function fields(sample) {
    const d=sample||{};
    return [
      ['Altitude',number(d.altitude_m,1,' m'),'Relative to takeoff'],
      ['Latitude',number(d.latitude,6),'Decimal degrees'],
      ['Longitude',number(d.longitude,6),'Decimal degrees'],
      ['Battery',number(d.battery_pct,0,'%'),'Aircraft battery'],
      ['Heading',number(d.heading_deg,0,'°'),'Clockwise from north'],
      ['Gimbal pitch',number(d.gimbal_pitch_deg,0,'°'),'Camera angle'],
      ['Flight state',typeof d.flying==='boolean'?(d.flying?'Airborne':'On ground'):'—','Reported by the aircraft'],
      ['GPS',!d.telemetry_fresh?'—':d.gps_ok?'Strong':'Acquiring','Strong GPS is required for navigation'],
      ['Satellites',number(d.satellites,0),'Satellites observed'],
      ['GPS signal',number(d.gps_signal_level,0,' / 5'),'DJI signal level'],
      ['Ground anchor',typeof d.ground_anchor_ok==='boolean'?(d.ground_anchor_ok?'Recorded':'Waiting'):'—','Recorded before takeoff'],
      ['Reading age',number(Number.isFinite(d.fc_age_ms)?d.fc_age_ms/1000:null,1,' s'),'Time since the flight-controller update'],
    ];
  }
  function render(element,badge,sample) {
    const html=fields(sample).map(([label,value,hint])=>`<div class="aircraft-stat" title="${escape(hint)}"><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`).join('');
    if(element.innerHTML!==html)element.innerHTML=html;
    badge.textContent=!sample?'Waiting for aircraft':sample.telemetry_fresh?(sample.mock?'Simulated telemetry':'Live telemetry'):'Readings stale / unavailable';
    badge.dataset.fresh=String(!!sample?.telemetry_fresh);
  }
  root.AircraftTelemetryPanel={fields,render};
  if(typeof module!=='undefined')module.exports={fields,render};
})(typeof window!=='undefined'?window:globalThis);
