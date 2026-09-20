#include "PilotTakeoff.h"
#include <assert.h>
#include <stdio.h>

static GATakeoffObservation ground(void) {
    return (GATakeoffObservation){.foreground=true,.connected=true,.aircraft=true,.gps=true,.anchor=true,
        .now=100,.fcTime=99.9,.batteryTime=99.9,.battery=80,.altitude=0,.distance=0};
}
static void fresh(GATakeoffObservation *o,double now) { o->now=now; o->fcTime=now; o->batteryTime=now; }
int main(void) {
    GATakeoff s={0}; GATakeoffObservation o=ground();
    assert(!GATakeoffProblem(s,o));
    // All launch prerequisites are rechecked at confirmation, including zero/stale/NaN data.
    #define REJECT(field,value) do { GATakeoffObservation bad=o; bad.field=value; assert(GATakeoffProblem(s,bad)); } while(0)
    REJECT(foreground,false); REJECT(connected,false); REJECT(aircraft,false);
    REJECT(gps,false); REJECT(anchor,false); REJECT(flying,true); REJECT(motorsOn,true);
    REJECT(aiBusy,true); REJECT(autoFlight,true); REJECT(fcTime,0); REJECT(fcTime,98.5);
    REJECT(fcTime,101); REJECT(batteryTime,95); REJECT(battery,29.9); REJECT(battery,NAN);
    REJECT(altitude,2.1); REJECT(altitude,NAN); REJECT(distance,5.1); REJECT(distance,NAN);
    #undef REJECT
    // Normal path: acceptance at 0.5 m is NOT completion; wait for settled telemetry.
    GATakeoffBegin(&s,100); assert(GATakeoffBusy(s)); assert(GATakeoffProblem(s,o));
    o.flying=true; o.motorsOn=true; o.autoFlight=true; o.altitude=.5;
    assert(!GATakeoffStartResult(&s,false));
    fresh(&o,101); assert(GATakeoffObserve(&s,o)==GATakeoffWaiting);
    fresh(&o,102); o.autoFlight=false; o.altitude=1.2; o.verticalSpeed=.5;
    assert(GATakeoffObserve(&s,o)==GATakeoffWaiting);
    o.verticalSpeed=0; fresh(&o,103); assert(GATakeoffObserve(&s,o)==GATakeoffWaiting);
    fresh(&o,103.5); o.horizontalSpeed=.8; assert(GATakeoffObserve(&s,o)==GATakeoffWaiting);
    fresh(&o,104); o.horizontalSpeed=0; assert(GATakeoffObserve(&s,o)==GATakeoffWaiting);
    fresh(&o,105); assert(GATakeoffObserve(&s,o)==GATakeoffComplete);
    assert(!GATakeoffBusy(s)); assert(GATakeoffProblem(s,o)); // already flying, cannot launch again
    // SDK rejection can be retried only once fresh grounded/motors-off checks pass.
    s=(GATakeoff){0}; o=ground(); GATakeoffBegin(&s,100);
    assert(!GATakeoffStartResult(&s,true)); assert(!GATakeoffBusy(s));
    assert(!GATakeoffProblem(s,o)); o.motorsOn=true; assert(GATakeoffProblem(s,o));
    // STOP before acceptance: don't let the later success undo cancellation.
    s=(GATakeoff){0}; GATakeoffBegin(&s,100);
    assert(GATakeoffRequestCancel(&s)); assert(!GATakeoffRequestCancel(&s));
    GATakeoffCancelResult(&s,false); assert(GATakeoffBusy(s)); // original SDK call still pending
    assert(GATakeoffStartResult(&s,false)); // late acceptance requires cancelling again
    assert(GATakeoffRequestCancel(&s)); GATakeoffCancelResult(&s,false); assert(!GATakeoffBusy(s));
    // Acceptance while cancel is in flight must not launch a second simultaneous cancel.
    GATakeoffBegin(&s,100); assert(GATakeoffRequestCancel(&s));
    assert(!GATakeoffStartResult(&s,false)); GATakeoffCancelResult(&s,false); assert(!GATakeoffBusy(s));
    // Cancellation error remains blocked until a deliberate STOP retry succeeds.
    GATakeoffBegin(&s,100); GATakeoffStartResult(&s,false);
    assert(GATakeoffRequestCancel(&s)); GATakeoffCancelResult(&s,true);
    assert(GATakeoffBusy(s)); assert(GATakeoffProblem(s,ground()));
    assert(GATakeoffRequestCancel(&s)); GATakeoffCancelResult(&s,false); assert(!GATakeoffBusy(s));
    // Missing callbacks cannot pass the gate just because telemetry says airborne.
    GATakeoffBegin(&s,100); o=ground(); o.flying=true; o.altitude=1.2;
    fresh(&o,101); assert(GATakeoffObserve(&s,o)==GATakeoffWaiting);
    fresh(&o,103); assert(GATakeoffObserve(&s,o)==GATakeoffWaiting);
    fresh(&o,130); assert(GATakeoffObserve(&s,o)==GATakeoffCancelRequired);
    // Each loss during takeoff requests cancellation, never a new launch or auto-arm.
    #define CANCEL_ON(field,value) do { GATakeoffBegin(&s,100); o=ground(); o.field=value; assert(GATakeoffObserve(&s,o)==GATakeoffCancelRequired); } while(0)
    CANCEL_ON(connected,false); CANCEL_ON(foreground,false); CANCEL_ON(aircraft,false);
    CANCEL_ON(gps,false); CANCEL_ON(anchor,false); CANCEL_ON(fcTime,98); CANCEL_ON(batteryTime,94); CANCEL_ON(battery,24);
    #undef CANCEL_ON
    puts("Pilot takeoff: launch gates, early callback, stable hover, duplicate prevention, cancellation races and link-loss checks passed.");
}
