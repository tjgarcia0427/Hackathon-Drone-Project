"""Execute the production request/confirmation methods on macOS with SDK/UI seams.

No aircraft. The local takeoff state machine has separate C tests. This suite
exercises the actual remote request methods extracted from DroneBridge.m.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'ios/GuardianAngel/DroneBridge.m').read_text(encoding='utf-8')
methods = source.split('// BEGIN agent takeoff request methods.\n')[1].split('// END agent takeoff request methods.')[0]
assert 'if([self.remoteTakeoff[@"cmd_id"] isEqual:identifier]) return;' in source
assert '[self finishTakeoffRequest:YES error:nil]; // agent takeoff integration' in source
assert '[self finishTakeoffRequest:NO error:reason]; // agent takeoff integration' in source
assert 'if(self.remoteTakeoff) { [self note:@"Finish or cancel the pilot takeoff request first"]; return; }' in source

prelude = r'''
#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>
#include <assert.h>
#import "PilotTakeoff.h"
static double clockTime=100;
static double CACurrentMediaTime(void) { return clockTime; }
static void Main(dispatch_block_t block) { block(); }
@interface RequestBridge : NSObject {
    double _takeoffPromptDeadline;
    GATakeoff _pilotTakeoff;
    BOOL _armed, _flightEnabled, _homeSet;
    struct { double lat,lon; } _home;
}
@property(nonatomic,strong) NSDictionary *remoteTakeoff;
@property(nonatomic,copy) void (^takeoffPrompt)(NSString *, void (^)(BOOL));
@property(nonatomic,copy) void (^dismissTakeoffPrompt)(void);
@property(nonatomic,copy) NSString *problem;
@property(nonatomic) NSUInteger launches, acknowledgments, prompts, dismissals;
@property(nonatomic) BOOL acknowledgedOK;
@property(nonatomic,copy) NSString *error;
- (void)requestPilotTakeoff:(NSDictionary *)cmd;
- (void)finishTakeoffRequest:(BOOL)ok error:(NSString *)error;
- (void)updateTakeoffRequest;
- (void)rejectSDK;
@end
// Production methods name their own class in the weak callback.
#define DroneBridge RequestBridge
@implementation RequestBridge
- (void)note:(NSString *)message {}
- (NSString *)takeoffProblem { return _takeoffPromptDeadline?@"Answer pending prompt":self.problem; }
- (void)pilotTakeoff { self.launches++; GATakeoffBegin(&_pilotTakeoff,clockTime); }
- (void)rejectSDK { GATakeoffStartResult(&_pilotTakeoff,true); }
- (void)ack:(NSString *)identifier ok:(BOOL)ok error:(NSString *)error {
    self.acknowledgments++; self.acknowledgedOK=ok; self.error=error;
}
'''
tests = r'''
@end
static NSDictionary *Command(NSString *identifier) { return @{@"cmd_id":identifier,@"expires_at_ms":@999999}; }
int main(void) { @autoreleasepool {
    __block void (^answer)(BOOL)=nil;
    RequestBridge *(^make)(void)=^{
        RequestBridge *bridge=[RequestBridge new]; __weak RequestBridge *weak=bridge;
        bridge.takeoffPrompt=^(NSString *identifier,void (^respond)(BOOL)){ weak.prompts++; answer=respond; };
        bridge.dismissTakeoffPrompt=^{ weak.dismissals++; };
        return bridge;
    };
    RequestBridge *b=make();
    [b requestPilotTakeoff:Command(@"one")];
    assert(b.launches==0 && b.prompts==1 && b.acknowledgments==0);
    [b requestPilotTakeoff:Command(@"one")]; assert(b.prompts==1);
    answer(YES); answer(YES);
    assert(b.launches==1 && b.acknowledgments==0); // SDK acceptance is not completion
    [b updateTakeoffRequest]; assert(b.acknowledgments==0);
    [b finishTakeoffRequest:YES error:nil];
    assert(b.acknowledgedOK && b.acknowledgments==1 && !b.remoteTakeoff);

    b=make(); [b requestPilotTakeoff:Command(@"two")];
    answer(NO); assert(b.launches==0 && b.acknowledgments==1 && !b.acknowledgedOK);
    answer(YES); assert(b.launches==0); // late approval after decline

    b=make(); [b requestPilotTakeoff:Command(@"three")];
    clockTime+=21; [b updateTakeoffRequest];
    assert(!b.remoteTakeoff && b.dismissals==1 && !b.acknowledgedOK);
    answer(YES); assert(b.launches==0);

    b=make(); [b requestPilotTakeoff:Command(@"four")];
    clockTime+=21; answer(YES); assert(b.launches==0 && !b.acknowledgedOK);

    b=make(); [b requestPilotTakeoff:Command(@"five")];
    b.problem=@"GPS lost"; answer(YES);
    assert(b.launches==0 && [b.error isEqual:@"GPS lost"]);

    b=make(); [b requestPilotTakeoff:Command(@"six")];
    [b finishTakeoffRequest:NO error:@"STOP / disconnect / background"];
    answer(YES); assert(b.launches==0 && b.acknowledgments==1);

    b=make(); [b requestPilotTakeoff:Command(@"seven")]; answer(YES);
    [b rejectSDK]; [b updateTakeoffRequest]; assert(!b.acknowledgedOK && !b.remoteTakeoff);

    b=make(); [b requestPilotTakeoff:@{@"cmd_id":@"missing-expiry"}];
    assert(b.prompts==0 && b.launches==0 && !b.acknowledgedOK);

    b=make(); [b requestPilotTakeoff:Command(@"eight")];
    [b requestPilotTakeoff:Command(@"nine")];
    assert(b.prompts==1 && b.acknowledgments==1 && !b.acknowledgedOK);
    assert([b.remoteTakeoff[@"cmd_id"] isEqual:@"eight"]);
    answer= nil;
    puts("Production agent takeoff request: approval, expiry, revalidation, deduplication, STOP and SDK rejection passed.");
} return 0; }
'''
with tempfile.TemporaryDirectory(prefix='guardian-request-') as tmp:
    code, binary = Path(tmp)/'request.m', Path(tmp)/'request-test'
    code.write_text(prelude+methods+tests, encoding='utf-8')
    subprocess.run(['xcrun','clang','-fobjc-arc','-fblocks','-framework','Foundation',
                    '-I'+str(root/'ios/GuardianAngel'),str(code),'-o',str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
