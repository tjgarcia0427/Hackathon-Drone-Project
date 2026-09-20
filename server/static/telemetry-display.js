/* Display observations never replace the navigation state used for dispatch. */
(function(root) {
  class AircraftTelemetryDisplay {
    constructor() { this.aircraft=null; this.drone=null; this.at=0; this.navigationAge=0; }
    update(message, now) {
      if (Object.prototype.hasOwnProperty.call(message,'drone')) this.drone=message.drone;
      if (Object.prototype.hasOwnProperty.call(message,'aircraft')) this.aircraft=message.aircraft;
      this.navigationAge=Object.prototype.hasOwnProperty.call(message,'navigation_age_ms')?message.navigation_age_ms:0;
      this.at=now;
      if (message.drone_connected===false) { this.aircraft=null; this.drone=null; }
    }
    read(now) {
      const elapsed=Math.max(0,now-this.at);
      const a=this.aircraft;
      if (!a && !this.drone) return null;
      const s=a?{...a}:{...this.drone,aircraft_connected:true,gps_ok:true,
        fc_age_ms:this.navigationAge,battery_age_ms:this.navigationAge,gimbal_age_ms:this.navigationAge,altitude_reference:'takeoff'};
      for (const key of ['fc_age_ms','battery_age_ms','gimbal_age_ms'])
        s[key]=Number.isFinite(s[key])?Math.max(0,s[key])+elapsed:null;
      const fresh=s.aircraft_connected && s.fc_age_ms!==null && s.fc_age_ms<1500;
      if (!fresh) {
        for (const key of ['latitude','longitude','altitude_m','heading_deg','gps_signal_level','satellites','flying']) s[key]=null;
        s.gps_ok=false;
      }
      if (!s.gps_ok) s.latitude=s.longitude=null;
      if (!s.aircraft_connected || s.battery_age_ms===null || s.battery_age_ms>=5000) s.battery_pct=null;
      if (!s.aircraft_connected || s.gimbal_age_ms===null || s.gimbal_age_ms>=1500) s.gimbal_pitch_deg=null;
      s.telemetry_fresh=!!fresh;
      return s;
    }
  }
  root.AircraftTelemetryDisplay=AircraftTelemetryDisplay;
  if (typeof module!=='undefined') module.exports=AircraftTelemetryDisplay;
})(typeof window!=='undefined'?window:globalThis);
