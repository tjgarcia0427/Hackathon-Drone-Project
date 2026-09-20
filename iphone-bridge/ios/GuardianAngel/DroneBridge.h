#import <UIKit/UIKit.h>
#import "BridgeClient.h"
@interface DroneBridge : NSObject
@property(nonatomic,strong,readonly) BridgeClient *client;
@property(nonatomic,copy) void (^log)(NSString *);
// Structured telemetry for the view layer, published at 1 Hz and on every control-state change.
// Keys: started, mock, aircraft, serverOnline, battery, altitude, heading, latitude, longitude,
// gps, homeSet, flying, distanceFromHome, armed, flightEnabled, returning, released,
// releasedLowBattery, command (e.g. "yaw (cmd-42)"), lastCommandAt.
@property(nonatomic,copy) void (^updated)(NSDictionary *telemetry);
- (NSDictionary *)telemetry;
- (instancetype)initWithPreview:(UIView *)preview mock:(BOOL)mock;
- (void)start;
- (void)armFlight:(BOOL)flight;
- (void)stopAutomation:(NSString *)reason;
- (void)shutdown;
@end
