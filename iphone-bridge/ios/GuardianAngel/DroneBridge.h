#import <UIKit/UIKit.h>
#import "BridgeClient.h"
@interface DroneBridge : NSObject
@property(nonatomic,strong,readonly) BridgeClient *client;
@property(nonatomic,copy) void (^log)(NSString *);
// Keep the original callback compatible with the bench-tested view controller.
@property(nonatomic,copy) void (^updated)(NSString *status);
// Read-only UI state, delivered on the main thread at 1 Hz. Call telemetry on the
// main thread for a fresh gate check. No SDK commands are issued by this getter.
@property(nonatomic,copy) void (^stateUpdated)(NSDictionary *telemetry);
- (NSDictionary *)telemetry;
- (instancetype)initWithPreview:(UIView *)preview mock:(BOOL)mock;
// Server requests only present a local pilot prompt. These blocks execute on main.
@property(nonatomic,copy) void (^takeoffPrompt)(NSString *, void (^respond)(BOOL));
@property(nonatomic,copy) void (^dismissTakeoffPrompt)(void);
- (void)start;
- (NSString *)takeoffProblem;
- (BOOL)pilotTakeoffBusy;
- (void)pilotTakeoff;
// Local pilot-only one-use permission; no remote authorization endpoint.
- (void)authorizeAgentTakeoff;
- (void)armFlight:(BOOL)flight;
- (void)stopAutomation:(NSString *)reason;
- (void)shutdown;
@end
