#import <Foundation/Foundation.h>
@interface BridgeClient : NSObject
@property(nonatomic,copy) void (^command)(NSDictionary *);
@property(nonatomic,copy) void (^stateChanged)(BOOL, NSString *);
@property(nonatomic,readonly) BOOL connected;
@property(nonatomic,readonly) NSTimeInterval lastPong;
@property(nonatomic,readonly) NSUInteger connectionID;
@property(nonatomic,copy) void (^diagnostic)(NSString *);
@property(nonatomic) BOOL mockHardware;
- (BOOL)connect:(NSString *)baseURL;
- (void)disconnect;
- (void)send:(NSDictionary *)message;
- (void)uploadJPEG:(NSData *)jpeg;
@end
