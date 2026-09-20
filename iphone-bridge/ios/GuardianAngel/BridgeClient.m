#import "BridgeClient.h"
#import <QuartzCore/QuartzCore.h>
@interface BridgeClient () <NSURLSessionWebSocketDelegate>
@property(nonatomic,strong) NSURLSession *session;
@property(nonatomic,strong) NSURLSessionWebSocketTask *socket;
@property(nonatomic,strong) NSURL *baseURL;
@property(nonatomic,strong) NSTimer *pingTimer;
@property(nonatomic,readwrite) BOOL connected;
@property(nonatomic,readwrite) NSTimeInterval lastPong;
@property(nonatomic,readwrite) NSUInteger connectionID;
@property(nonatomic) BOOL uploading;
@end
@implementation BridgeClient
- (BOOL)connect:(NSString *)address {
    [self disconnect];
    NSURLComponents *c=[NSURLComponents componentsWithString:[address stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet]];
    if (!c.host.length || !([c.scheme isEqual:@"http"] || [c.scheme isEqual:@"https"]) || c.user || c.password || c.query || c.fragment || (c.path.length && ![c.path isEqual:@"/"])) return NO;
    self.baseURL=c.URL;
    c.scheme=[c.scheme isEqual:@"https"]?@"wss":@"ws"; c.path=@"/ws/drone";
    NSURLSessionConfiguration *config=NSURLSessionConfiguration.ephemeralSessionConfiguration;
    config.timeoutIntervalForRequest=5;
    self.session=[NSURLSession sessionWithConfiguration:config delegate:self delegateQueue:NSOperationQueue.mainQueue];
    self.socket=[self.session webSocketTaskWithURL:c.URL];
    self.socket.maximumMessageSize=16384;
    [self.socket resume];
    [self receive:self.socket];
    return YES;
}
- (void)disconnect {
    ++self.connectionID;
    BOOL wasLive=self.socket!=nil;
    self.connected=NO;
    [self.pingTimer invalidate]; self.pingTimer=nil;
    [self.socket cancelWithCloseCode:NSURLSessionWebSocketCloseCodeNormalClosure reason:nil]; self.socket=nil;
    [self.session invalidateAndCancel]; self.session=nil; self.uploading=NO;
    if(wasLive && self.stateChanged) self.stateChanged(NO,@"Server disconnected");
}
- (void)fail:(NSString *)reason socket:(NSURLSessionWebSocketTask *)socket {
    if(!socket || socket!=self.socket) return;
    [self disconnect];
    if(self.stateChanged) self.stateChanged(NO,reason);
}
- (void)URLSession:(NSURLSession *)session webSocketTask:(NSURLSessionWebSocketTask *)socket didOpenWithProtocol:(NSString *)protocol {
    if(socket!=self.socket) return;
    self.connected=YES; self.lastPong=CACurrentMediaTime();
    [self send:@{@"type":@"hello",@"drone_id":@"air2",@"model":@"Mavic Air 2",@"mode":self.mockHardware?@"mock":@"live"}];
    __weak typeof(self) weakSelf=self;
    self.pingTimer=[NSTimer scheduledTimerWithTimeInterval:1 repeats:YES block:^(NSTimer *timer) {
        BridgeClient *s=weakSelf;
        if(CACurrentMediaTime()-s.lastPong>4) { [s fail:@"Server heartbeat lost" socket:socket]; return; }
        [socket sendPingWithPongReceiveHandler:^(NSError *error) {
            dispatch_async(dispatch_get_main_queue(),^{
                if(socket!=s.socket) return;
                if(error) [s fail:error.localizedDescription socket:socket];
                else s.lastPong=CACurrentMediaTime();
            });
        }];
    }];
    [[NSRunLoop mainRunLoop] addTimer:self.pingTimer forMode:NSRunLoopCommonModes];
    if(self.stateChanged) self.stateChanged(YES,@"Server connected");
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
    if(task==self.socket) [self fail:error.localizedDescription?:@"Server closed" socket:self.socket];
}
- (void)URLSession:(NSURLSession *)session webSocketTask:(NSURLSessionWebSocketTask *)socket didCloseWithCode:(NSURLSessionWebSocketCloseCode)code reason:(NSData *)reason {
    [self fail:@"Server closed connection" socket:socket];
}
- (void)receive:(NSURLSessionWebSocketTask *)socket {
    __weak typeof(self) weakSelf=self;
    [socket receiveMessageWithCompletionHandler:^(NSURLSessionWebSocketMessage *message,NSError *error) {
        dispatch_async(dispatch_get_main_queue(),^{
            BridgeClient *s=weakSelf; if(!s || socket!=s.socket) return;
            if(error) { [s fail:error.localizedDescription socket:socket]; return; }
            NSData *data=message.type==NSURLSessionWebSocketMessageTypeString?[message.string dataUsingEncoding:NSUTF8StringEncoding]:message.data;
            id obj=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if([obj isKindOfClass:NSDictionary.class] && [obj[@"type"] isEqual:@"cmd"] && s.command) s.command(obj);
            [s receive:socket];
        });
    }];
}
- (void)send:(NSDictionary *)message {
    if(!self.connected) return;
    NSData *data=[NSJSONSerialization dataWithJSONObject:message options:0 error:nil];
    if(!data) return;
    NSURLSessionWebSocketTask *socket=self.socket;
    [socket sendMessage:[[NSURLSessionWebSocketMessage alloc] initWithString:[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]] completionHandler:^(NSError *error) {
        if(error) dispatch_async(dispatch_get_main_queue(),^{[self fail:error.localizedDescription socket:socket];});
    }];
}
- (void)uploadJPEG:(NSData *)jpeg {
    if(!self.connected || self.uploading || !jpeg.length) return;
    self.uploading=YES;
    NSURLSession *session=self.session;
    NSMutableURLRequest *request=[NSMutableURLRequest requestWithURL:[NSURL URLWithString:@"/frame" relativeToURL:self.baseURL]];
    request.HTTPMethod=@"POST";
    [request setValue:@"image/jpeg" forHTTPHeaderField:@"Content-Type"];
    request.timeoutInterval=3;
    [[session uploadTaskWithRequest:request fromData:jpeg completionHandler:^(NSData *data,NSURLResponse *response,NSError *error) {
        dispatch_async(dispatch_get_main_queue(),^{
            if(session!=self.session) return;
            self.uploading=NO;
            NSInteger status=[response isKindOfClass:NSHTTPURLResponse.class]?[(NSHTTPURLResponse *)response statusCode]:0;
            if((error || status<200 || status>=300) && self.diagnostic)
                self.diagnostic(error?[NSString stringWithFormat:@"Frame upload failed: %@",error.localizedDescription]:[NSString stringWithFormat:@"Frame upload HTTP %ld",(long)status]);
        });
    }] resume];
}
@end
