#import <UIKit/UIKit.h>
#import "BridgeClient.h"
@interface DroneBridge : NSObject
@property(nonatomic,strong,readonly) BridgeClient *client;
@property(nonatomic,copy) void (^log)(NSString *);
@property(nonatomic,copy) void (^updated)(NSString *);
- (instancetype)initWithPreview:(UIView *)preview mock:(BOOL)mock;
- (void)start;
- (void)armFlight:(BOOL)flight;
- (void)stopAutomation:(NSString *)reason;
- (void)shutdown;
@end
