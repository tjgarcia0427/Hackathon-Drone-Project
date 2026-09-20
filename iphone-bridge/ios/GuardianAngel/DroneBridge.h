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
- (void)start;
- (void)armFlight:(BOOL)flight;
- (void)stopAutomation:(NSString *)reason;
- (void)shutdown;
@end
