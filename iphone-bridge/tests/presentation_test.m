#import <Foundation/Foundation.h>
#import "BridgePresentation.h"
#include <assert.h>

int main(void) { @autoreleasepool {
    NSMutableDictionary *t=[@{@"started":@YES,@"mock":@YES,@"serverOnline":@YES,@"aircraft":@YES,
        @"telemetryFresh":@YES,@"positionFresh":@YES,@"batteryFresh":@YES,@"gps":@YES,@"homeSet":@YES,
        @"flying":@YES,@"battery":@78,@"altitude":@10,@"distanceFromHome":@3,@"flightBlockReason":@""} mutableCopy];
    assert(!GACanConfirmFlight(nil)); assert(!GACanConfirmFlight(@{}));
    assert(GACanConfirmFlight(t)); assert(GAStateForTelemetry(t)==GAMock);
    for(NSString *flag in @[@"takeoffBusy",@"armed",@"flightEnabled",@"enabling",@"returning",@"releaseFailed",@"pendingTransitions"]) {
        t[flag]=@YES; assert(!GACanConfirmFlight(t)); [t removeObjectForKey:flag];
    }
    for(NSString *flag in @[@"started",@"serverOnline",@"aircraft",@"telemetryFresh",@"positionFresh",@"batteryFresh",@"gps",@"homeSet",@"flying"]) {
        t[flag]=@NO; assert(!GACanConfirmFlight(t)); t[flag]=@YES;
    }
    for(NSArray *pair in @[@[@"battery",@29],@[@"altitude",@4.9],@[@"altitude",@30.1],@[@"distanceFromHome",@(-1)],@[@"distanceFromHome",@40.1],@[@"battery",@(NAN)]]) {
        NSString *key=pair[0]; id previous=t[key]; t[key]=pair[1]; assert(!GACanConfirmFlight(t)); t[key]=previous;
    }
    t[@"flightBlockReason"]=@"Aircraft telemetry is stale"; assert(!GACanConfirmFlight(t)); t[@"flightBlockReason"]=@"";
    t[@"armed"]=@YES; assert(GAStateForTelemetry(t)==GACameraOnly);
    t[@"flightEnabled"]=@YES; assert(GAStateForTelemetry(t)==GAFlight);
    t[@"returning"]=@YES; assert(GAStateForTelemetry(t)==GAReturning);
    t[@"pendingTransitions"]=@1; assert(GAStateForTelemetry(t)==GAControlPending);
    t[@"releaseFailed"]=@YES; assert(GAStateForTelemetry(t)==GAReleaseFailed);
    puts("Presentation checks passed: camera interlock, freshness, bounds, missing state, transition precedence.");
} return 0; }
