#ifndef GA_PILOT_TAKEOFF_H
#define GA_PILOT_TAKEOFF_H
#include <stdbool.h>
#include <math.h>

// Takeoff execution does not own the server, anchor or AI arm flags.
// A local pilot may authorize exactly one agent launch for five minutes.
// Monotonic time only: never persist or restore this permission after reconnect.
typedef struct { double expiresAt; } GATakeoffPermit;
static inline bool GATakeoffPermitValid(GATakeoffPermit p, double now) {
    return isfinite(now) && now>0 && isfinite(p.expiresAt) && now<p.expiresAt;
}
static inline bool GATakeoffConsumePermit(GATakeoffPermit *p, double now) {
    bool valid=GATakeoffPermitValid(*p,now); *p=(GATakeoffPermit){0}; return valid;
}
typedef struct {
    bool active, startPending, accepted, interrupted, cancelPending, uncertain;
    double startedAt, stableSince;
} GATakeoff;

typedef struct {
    bool foreground, connected, aircraft, gps, anchor, flying, motorsOn, aiBusy, autoFlight;
    double now, fcTime, batteryTime, battery, altitude, distance, horizontalSpeed, verticalSpeed;
} GATakeoffObservation;

static inline bool GATakeoffBusy(GATakeoff s) {
    return s.active || s.startPending || s.cancelPending || s.uncertain;
}
static inline bool GATakeoffFresh(double now, double at, double maxAge) {
    return isfinite(now) && isfinite(at) && at>0 && now>=at && now-at<maxAge;
}
static inline const char *GATakeoffProblem(GATakeoff s, GATakeoffObservation o) {
    if(s.uncertain) return "Takeoff outcome unconfirmed. Use the RC; press STOP to retry cancellation.";
    if(GATakeoffBusy(s)) return "Takeoff is already in progress. Keep the RC ready.";
    if(!o.foreground) return "Keep Guardian Angel active for takeoff.";
    if(!o.connected) return "Connect to the server before takeoff.";
    if(!o.aircraft) return "Connect the Mavic Air 2 before takeoff.";
    if(o.aiBusy) return "Press STOP to disable camera/AI control and wait for control release before takeoff.";
    if(!GATakeoffFresh(o.now,o.fcTime,1.5) || !GATakeoffFresh(o.now,o.batteryTime,5)) return "Wait for fresh aircraft and battery telemetry.";
    if(o.flying) return "Aircraft is already airborne. Enable flight when within 1-30 m above takeoff.";
    if(o.motorsOn) return "Motors are already running. Use the RC for takeoff.";
    if(o.autoFlight) return "Aircraft is in an automatic takeoff, return or landing mode. Use the RC.";
    if(!o.gps || !o.anchor) return "Wait for GPS OK and Ground anchor OK before takeoff.";
    if(!isfinite(o.battery) || o.battery<30) return "Battery must be at least 30% for takeoff.";
    if(!isfinite(o.altitude) || fabs(o.altitude)>2 || !isfinite(o.distance) || o.distance<0 || o.distance>5)
        return "Aircraft must be grounded within 5 m of the recorded launch point. Check the launch site.";
    return 0;
}
static inline void GATakeoffBegin(GATakeoff *s, double now) {
    *s=(GATakeoff){.active=true,.startPending=true,.startedAt=now};
}
// Returns true when a late acceptance needs another cancellation after STOP.
static inline bool GATakeoffStartResult(GATakeoff *s, bool error) {
    s->startPending=false;
    if(error) { s->active=false; return false; }
    s->accepted=true;
    if(s->interrupted && !s->cancelPending) { s->uncertain=true; return true; }
    return false;
}
static inline bool GATakeoffRequestCancel(GATakeoff *s) {
    if(s->cancelPending || (!s->active && !s->uncertain)) return false;
    s->active=false; s->interrupted=true; s->uncertain=true; s->cancelPending=true;
    return true;
}
static inline void GATakeoffCancelResult(GATakeoff *s, bool error) {
    s->cancelPending=false; s->uncertain=error;
}
typedef enum { GATakeoffWaiting, GATakeoffComplete, GATakeoffCancelRequired } GATakeoffEvent;
static inline GATakeoffEvent GATakeoffObserve(GATakeoff *s, GATakeoffObservation o) {
    if(!s->active) return GATakeoffWaiting;
    if(!o.foreground || !o.connected || !o.aircraft || !o.gps || !o.anchor ||
       !GATakeoffFresh(o.now,o.fcTime,1.5) || !GATakeoffFresh(o.now,o.batteryTime,5) ||
       !isfinite(o.battery) || o.battery<25 || !isfinite(o.now) || o.now-s->startedAt>=30)
        return GATakeoffCancelRequired;
    // DJI's completion callback can arrive at 0.5 m, before its ~1.2 m hover.
    bool settled=s->accepted && o.flying && !o.autoFlight && isfinite(o.altitude) && o.altitude>=1.0 &&
        isfinite(o.horizontalSpeed) && o.horizontalSpeed>=0 && o.horizontalSpeed<0.4 &&
        isfinite(o.verticalSpeed) && o.verticalSpeed>=0 && o.verticalSpeed<0.3;
    if(!settled) s->stableSince=0;
    else if(!s->stableSince) s->stableSince=o.now;
    else if(o.now-s->stableSince>=1) { s->active=false; return GATakeoffComplete; }
    return GATakeoffWaiting;
}
#endif
