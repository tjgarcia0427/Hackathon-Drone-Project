"""Run the production async takeoff/preparation code with a controllable SDK seam.

macOS Foundation is required; no aircraft or DJI binary is used by this test.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'ios/GuardianAngel/DroneBridge.m').read_text(encoding='utf-8')
def method(name):
    match = re.search(r'^- \([^\n]+\)' + re.escape(name) + r'(?=[: {])[^\n]*\n.*?^}\n', source, re.M | re.S)
    assert match, name
    return match.group()

prelude = r'''
#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>
#include <assert.h>
#import "PilotTakeoff.h"
#import "Navigation.h"
static double clockTime=100;
static double CACurrentMediaTime(void) { return clockTime; }
static void Main(dispatch_block_t block) { block(); }
enum { DJIFlightModeAutoTakeoff=1, DJIFlightModeAssistedTakeoff=2 };
@interface DJIFlightController : NSObject
@property(nonatomic,copy) void (^readReply)(BOOL,NSError *);
@property(nonatomic,copy) void (^releaseReply)(NSError *);
@property(nonatomic,copy) void (^launchReply)(NSError *);
@property(nonatomic,copy) void (^cancelReply)(NSError *);
@property(nonatomic) NSUInteger launches, releases, cancellations;
@end
@implementation DJIFlightController
- (void)getVirtualStickModeEnabledWithCompletion:(void (^)(BOOL,NSError *))reply { self.readReply=reply; }
- (void)setVirtualStickModeEnabled:(BOOL)enabled withCompletion:(void (^)(NSError *))reply {
    assert(!enabled); self.releases++; self.releaseReply=reply;
}
- (void)startTakeoffWithCompletion:(void (^)(NSError *))reply { self.launches++; self.launchReply=reply; }
- (void)cancelTakeoffWithCompletion:(void (^)(NSError *))reply { self.cancellations++; self.cancelReply=reply; }
@end
@interface TestBridge : NSObject {
    GATakeoffPermit _takeoffPermit; GATakeoff _pilotTakeoff;
    BOOL _enableAfterTakeoff, _takeoffSubmitted, _closed, _mock, _flying, _motorsOn;
    NSUInteger _takeoffID, _takeoffCancelID, _pendingSDKTransitions; double _takeoffCancelTime; NSInteger _takeoffMode;
    GAPose _pose;
}
@property(nonatomic,strong) DJIFlightController *fc;
@property(nonatomic,copy) NSString *lastTakeoffError;
@property(nonatomic) GATakeoffObservation observation;
@property(nonatomic) NSUInteger acknowledgments, armRequests;
@property(nonatomic) BOOL acknowledgedOK;
- (void)pilotTakeoff;
- (void)cancelPilotTakeoff;
- (void)updatePilotTakeoff;
- (void)failTakeoff:(NSError *)error stage:(NSString *)stage;
- (void)launchPreparedTakeoff:(NSUInteger)request controller:(DJIFlightController *)controller;
- (BOOL)canPrepareTakeoff:(NSUInteger)request controller:(DJIFlightController *)controller;
- (void)authorizeAgentTakeoff;
@end
@implementation TestBridge
- (void)note:(NSString *)message {}
- (NSDictionary *)takeoffDiagnostics { return @{}; }
- (GATakeoffObservation)takeoffObservation { GATakeoffObservation o=self.observation; o.aiBusy=_pendingSDKTransitions>0; return o; }
- (NSString *)takeoffProblem {
    const char *p=GATakeoffProblem(_pilotTakeoff,[self takeoffObservation]); return p?@(p):nil;
}
- (void)finishTakeoffRequest:(BOOL)ok error:(NSString *)error {
    self.acknowledgments++; self.acknowledgedOK=ok; if(!ok) _enableAfterTakeoff=NO;
}
- (void)armFlight:(BOOL)flight { assert(flight); self.armRequests++; }
- (void)autoEnable { _enableAfterTakeoff=YES; }
- (void)stop {
    _takeoffPermit=(GATakeoffPermit){0}; _enableAfterTakeoff=NO;
    [self cancelPilotTakeoff];
}
'''
tests = r'''
@end
static TestBridge *Make(void) {
    TestBridge *b=[TestBridge new]; b.fc=[DJIFlightController new]; clockTime=100;
    b.observation=(GATakeoffObservation){.foreground=true,.connected=true,.aircraft=true,.gps=true,.anchor=true,
        .now=100,.fcTime=100,.batteryTime=100,.battery=80};
    return b;
}
static void Hover(TestBridge *b, double now) {
    clockTime=now; GATakeoffObservation o=b.observation;
    o.now=o.fcTime=o.batteryTime=now; o.flying=true; o.motorsOn=true; o.altitude=1.2;
    b.observation=o; [b updatePilotTakeoff];
}
int main(void) { @autoreleasepool {
    TestBridge *b=Make(); [b autoEnable]; [b pilotTakeoff];
    assert(b.fc.launches==0); b.fc.readReply(NO,nil); assert(b.fc.launches==1);
    b.fc.launchReply(nil); assert(b.armRequests==0 && b.acknowledgments==0);
    Hover(b,101); assert(b.armRequests==0); Hover(b,102);
    assert(b.armRequests==1 && b.acknowledgedOK); Hover(b,103); assert(b.armRequests==1);

    b=Make(); [b pilotTakeoff]; b.fc.readReply(YES,nil);
    assert(b.fc.releases==1 && b.fc.launches==0);
    b.fc.releaseReply(nil); assert(b.fc.launches==1);
    b.fc.launchReply(nil); Hover(b,101); Hover(b,102);
    assert(b.acknowledgedOK && b.armRequests==0); // manual launch does not arm

    b=Make(); [b pilotTakeoff]; [b stop]; assert([b takeoffProblem]!=nil); b.fc.readReply(NO,nil);
    assert(b.fc.launches==0 && b.fc.cancellations==0 && [b takeoffProblem]==nil);
    b=Make(); [b pilotTakeoff]; b.fc.readReply(YES,nil); [b stop]; b.fc.releaseReply(nil);
    assert(b.fc.launches==0 && b.fc.cancellations==0);

    b=Make(); [b pilotTakeoff];
    GATakeoffObservation o=b.observation; o.gps=false; b.observation=o;
    b.fc.readReply(NO,nil); assert(b.fc.launches==0 && b.lastTakeoffError.length);
    b=Make(); [b pilotTakeoff]; o=b.observation; o.connected=false; b.observation=o;
    b.fc.readReply(NO,nil); assert(b.fc.launches==0);

    NSError *failure=[NSError errorWithDomain:@"DJISDK" code:-1008 userInfo:@{NSLocalizedDescriptionKey:@"Rejected"}];
    b=Make(); [b pilotTakeoff]; b.fc.readReply(NO,failure);
    assert(b.fc.launches==0 && [b.lastTakeoffError containsString:@"-1008"]);
    b=Make(); [b pilotTakeoff]; b.fc.readReply(YES,nil); b.fc.releaseReply(failure);
    assert(b.fc.launches==0 && !b.acknowledgedOK);
    b=Make(); [b autoEnable]; [b pilotTakeoff]; b.fc.readReply(NO,nil); b.fc.launchReply(failure);
    Hover(b,101); Hover(b,102); assert(b.fc.launches==1 && b.armRequests==0 && !b.acknowledgedOK);

    b=Make(); [b autoEnable]; [b pilotTakeoff]; b.fc.readReply(NO,nil); [b stop];
    assert(b.fc.cancellations==1); b.fc.cancelReply(nil); b.fc.launchReply(nil);
    assert(b.fc.cancellations==2); b.fc.cancelReply(nil);
    Hover(b,101); Hover(b,102); assert(b.armRequests==0);
    puts("Production SDK preparation: release, delayed callbacks, STOP, rechecks, errors, hover and auto-enable passed.");
} return 0; }
'''
methods = ''.join(method(n) for n in ['authorizeAgentTakeoff', 'canPrepareTakeoff', 'failTakeoff',
    'launchPreparedTakeoff', 'pilotTakeoff', 'cancelPilotTakeoff', 'updatePilotTakeoff'])
with tempfile.TemporaryDirectory(prefix='guardian-takeoff-sdk-') as temp:
    code, binary = Path(temp)/'test.m', Path(temp)/'test'
    code.write_text(prelude+methods+tests, encoding='utf-8')
    subprocess.run(['xcrun','clang','-fobjc-arc','-fblocks','-framework','Foundation',
                    '-I'+str(root/'ios/GuardianAngel'),str(code),'-o',str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
