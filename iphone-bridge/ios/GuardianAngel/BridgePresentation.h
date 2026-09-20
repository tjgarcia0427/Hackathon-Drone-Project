#import <Foundation/Foundation.h>
#include <math.h>
#import "Navigation.h"

// Presentation decisions only. DroneBridge independently validates every arm request.
typedef NS_ENUM(NSInteger, GAOpState) {
    GANotStarted, GAMock, GADisarmed, GACameraOnly, GAFlight, GAReturning,
    GALowBattery, GAControlPending, GAReleaseFailed
};

static inline GAOpState GAStateForTelemetry(NSDictionary *t) {
    if(![t[@"started"] boolValue]) return GANotStarted;
    if([t[@"releaseFailed"] boolValue]) return GAReleaseFailed;
    if([t[@"takeoffBusy"] boolValue] || [t[@"enabling"] boolValue] || [t[@"pendingTransitions"] unsignedIntegerValue]>0) return GAControlPending;
    if([t[@"returning"] boolValue]) return GAReturning;
    if([t[@"flightEnabled"] boolValue]) return GAFlight;
    if([t[@"armed"] boolValue]) return GACameraOnly;
    if([t[@"batteryFresh"] boolValue] && [t[@"battery"] doubleValue]>=0 && [t[@"battery"] doubleValue]<30) return GALowBattery;
    return [t[@"mock"] boolValue]?GAMock:GADisarmed;
}

static inline BOOL GACanConfirmFlight(NSDictionary *t) {
    NSString *reason=t[@"flightBlockReason"];
    // A missing snapshot or reason is unknown, never a passing check.
    if(![reason isKindOfClass:NSString.class] || reason.length) return NO;
    if(![t[@"started"] boolValue] || ![t[@"serverOnline"] boolValue] || ![t[@"aircraft"] boolValue]) return NO;
    if([t[@"takeoffBusy"] boolValue] || [t[@"armed"] boolValue] || [t[@"flightEnabled"] boolValue] || [t[@"enabling"] boolValue] ||
       [t[@"returning"] boolValue] || [t[@"releaseFailed"] boolValue] || [t[@"pendingTransitions"] unsignedIntegerValue]) return NO;
    if(![t[@"telemetryFresh"] boolValue] || ![t[@"positionFresh"] boolValue] || ![t[@"batteryFresh"] boolValue] ||
       ![t[@"gps"] boolValue] || ![t[@"homeSet"] boolValue] || ![t[@"flying"] boolValue]) return NO;
    double battery=[t[@"battery"] doubleValue], altitude=[t[@"altitude"] doubleValue], distance=[t[@"distanceFromHome"] doubleValue];
    return isfinite(battery) && battery>=30 && isfinite(altitude) && altitude>=GA_MIN_ALTITUDE_M && altitude<=GA_MAX_ALTITUDE_M && isfinite(distance) && distance>=0 && distance<=40;
}
