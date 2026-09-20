// Simulator-only stand-in. Never linked into the production app or used for DJI validation.
#import "DroneBridge.h"
#import <QuartzCore/QuartzCore.h>
@interface BridgeClient ()
@property(nonatomic,readwrite) BOOL connected;
@end
@implementation BridgeClient
- (BOOL)connect:(NSString *)url { self.connected=YES; if(self.stateChanged) self.stateChanged(YES,@"UI harness server connected"); return YES; }
- (void)disconnect { self.connected=NO; if(self.stateChanged) self.stateChanged(NO,@"UI harness disconnected"); }
- (NSTimeInterval)lastPong { return CACurrentMediaTime(); }
- (NSUInteger)connectionID { return 1; }
- (void)send:(NSDictionary *)message {}
- (void)uploadJPEG:(NSData *)jpeg {}
@end

@interface DroneBridge ()
@property(nonatomic,strong,readwrite) BridgeClient *client;
@property(nonatomic,strong) NSMutableDictionary *testState;
@property(nonatomic) NSUInteger flightRequests, stopRequests;
@end
@implementation DroneBridge
- (instancetype)initWithPreview:(UIView *)preview mock:(BOOL)mock {
    if((self=[super init])) {
        self.client=[BridgeClient new];
        self.testState=[@{@"started":@NO,@"mock":@(mock),@"aircraft":@YES,@"serverOnline":@NO,
            @"battery":@78,@"batteryFresh":@YES,@"positionFresh":@YES,@"telemetryFresh":@YES,
            @"altitude":@9.8,@"heading":@92,@"latitude":@25.7617,@"longitude":@(-80.1918),
            @"gps":@YES,@"homeSet":@YES,@"flying":@YES,@"distanceFromHome":@3,@"command":@""} mutableCopy];
    } return self;
}
- (NSDictionary *)telemetry {
    self.testState[@"serverOnline"]=@(self.client.connected);
    self.testState[@"telemetryAt"]=@(NSDate.date.timeIntervalSince1970);
    NSString *problem=@"";
    if(!self.client.connected) problem=@"Connect to the server first";
    else if([self.testState[@"armed"] boolValue]) problem=@"Stop camera control before enabling flight";
    else if([self.testState[@"releaseFailed"] boolValue]) problem=@"Control release is unconfirmed";
    else if([self.testState[@"pendingTransitions"] integerValue] || [self.testState[@"returning"] boolValue]) problem=@"Wait for the control transition";
    else if(![self.testState[@"telemetryFresh"] boolValue]) problem=@"Aircraft telemetry is stale";
    else if([self.testState[@"battery"] doubleValue]<30) problem=@"Battery must be at least 30% to enable flight";
    self.testState[@"flightBlockReason"]=problem;
    return self.testState.copy;
}
- (void)start { self.testState[@"started"]=@YES; if(self.log) self.log(@"UI harness — simulated state only; no DJI connection"); }
- (void)armFlight:(BOOL)flight {
    if([self.testState[@"armed"] boolValue]) { if(self.log) self.log(@"Stop AI control before changing control mode"); return; }
    self.testState[@"armed"]=@YES; self.testState[@"flightEnabled"]=@(flight);
    if(flight) self.flightRequests++;
    if(self.log) self.log(flight?@"MOCK flight enabled":@"Camera commands enabled; flight commands remain disabled");
}
- (void)stopAutomation:(NSString *)reason {
    self.stopRequests++; self.testState[@"armed"]=@NO; self.testState[@"flightEnabled"]=@NO;
    if(self.log) self.log(reason);
}
- (void)shutdown { [self.client disconnect]; }
@end
