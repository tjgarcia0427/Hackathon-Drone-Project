#import <UIKit/UIKit.h>
#import "DroneBridge.h"

static UIViewController *Root(void) {
    UIWindow *window=[(NSObject *)[UIApplication sharedApplication].delegate valueForKey:@"window"];
    return ((UINavigationController *)window.rootViewController).viewControllers.firstObject;
}
static void Result(BOOL ok, NSString *message) {
    NSDictionary *report=@{@"ok":@(ok),@"message":message};
    NSString *path=[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/ui-result.json"];
    [[NSJSONSerialization dataWithJSONObject:report options:0 error:nil] writeToFile:path atomically:YES];
    NSLog(@"UI_SMOKE %@: %@",ok?@"PASS":@"FAIL",message);
}
static void Check(BOOL ok, NSString *message) { if(!ok) { Result(NO,message); exit(2); } }
static void Later(void (^work)(void)) { dispatch_after(dispatch_time(DISPATCH_TIME_NOW,600*NSEC_PER_MSEC),dispatch_get_main_queue(),work); }
static void Invoke(id target, NSString *name) {
    SEL sel=NSSelectorFromString(name);
    ((void (*)(id,SEL))[target methodForSelector:sel])(target,sel);
}
static void Click(id target, NSString *name) {
    UIButton *button=[target valueForKey:name];
    Check(button.enabled && !button.hidden,[NSString stringWithFormat:@"%@ must be visible and enabled",name]);
    [button sendActionsForControlEvents:UIControlEventTouchUpInside];
}
static UIButton *FindButton(UIView *view, NSString *identifier) {
    if([view isKindOfClass:UIButton.class] && [view.accessibilityIdentifier isEqual:identifier]) return (UIButton *)view;
    for(UIView *child in view.subviews) { UIButton *found=FindButton(child,identifier); if(found) return found; }
    return nil;
}
static void LayoutCheck(UIView *view) {
    Check(!view.hasAmbiguousLayout,[NSString stringWithFormat:@"Ambiguous layout: %@",view.class]);
    for(UIView *child in view.subviews) if(!child.hidden) LayoutCheck(child);
}
static void Run(void) {
    UIViewController *root=Root();
    NSString *scenario=NSProcessInfo.processInfo.environment[@"GA_UI_SCENARIO"]?:@"flow";
    if([scenario isEqual:@"not-started"]) { [root.view layoutIfNeeded]; Result(YES,@"Initial screen rendered"); return; }
    Click(root,@"startButton");
    DroneBridge *bridge=[root valueForKey:@"bridge"];
    NSMutableDictionary *state=[bridge valueForKey:@"testState"];
    if(![scenario isEqual:@"offline"]) Click(root,@"connectButton");
    Invoke(root,@"refreshState");
    if(![scenario isEqual:@"flow"]) {
        if([scenario isEqual:@"camera"] || [scenario isEqual:@"procedure"]) Click(root,@"cameraButton");
        if([scenario isEqual:@"flight"]) { state[@"mock"]=@NO; state[@"armed"]=@YES; state[@"flightEnabled"]=@YES; }
        if([scenario isEqual:@"returning"]) { state[@"mock"]=@NO; state[@"returning"]=@YES; }
        if([scenario isEqual:@"pending"]) state[@"pendingTransitions"]=@1;
        if([scenario isEqual:@"release-failed"]) { state[@"releaseFailed"]=@YES; state[@"pendingTransitions"]=@1; }
        if([scenario isEqual:@"stale"]) { state[@"telemetryFresh"]=@NO; state[@"positionFresh"]=@NO; state[@"batteryFresh"]=@NO; }
        if([scenario isEqual:@"low-battery"]) { state[@"mock"]=@NO; state[@"battery"]=@24; }
        Invoke(root,@"refreshState");
        if([scenario isEqual:@"modal"]) Click(root,@"flightButton");
        if([scenario isEqual:@"log"]) Invoke(root,@"openLog");
        Later(^{
            [root.view layoutIfNeeded];
            if([scenario isEqual:@"procedure"]) {
                UIButton *action=[root valueForKey:@"flightButton"];
                UIView *ancestor=action.superview;
                while(ancestor && ![ancestor isKindOfClass:UIScrollView.class]) ancestor=ancestor.superview;
                Check(ancestor!=nil,@"Procedure action must be reachable by scrolling");
                [(UIScrollView *)ancestor scrollRectToVisible:[action convertRect:action.bounds toView:ancestor] animated:NO];
            }
            Result(YES,[scenario stringByAppendingString:@" rendered"]);
        });
        return;
    }
    // Exercise the actual production controller actions; the stand-in enforces the camera interlock.
    Click(root,@"cameraButton");
    Check([state[@"armed"] boolValue],@"Camera action must arm camera mode");
    Click(root,@"flightButton");
    Check(![state[@"armed"] boolValue],@"First flight-step action must STOP camera control");
    Check([[bridge valueForKey:@"flightRequests"] integerValue]==0,@"STOP must not auto-enable flight");
    Click(root,@"flightButton");
    Later(^{
        UIViewController *modal=root.presentedViewController;
        Check(modal!=nil,@"Separate confirmation must be presented");
        Click(modal,@"enable");
        Later(^{
            Check([state[@"flightEnabled"] boolValue],@"Separate confirmation must enable mock flight");
            Check([[bridge valueForKey:@"flightRequests"] integerValue]==1,@"Exactly one flight enable request expected");
            Invoke(root,@"openLog");
            Later(^{
                UIViewController *log=root.navigationController.topViewController;
                UIButton *stop=FindButton(log.view,@"log.stop"); Check(stop.enabled,@"STOP must remain accessible in the log");
                [stop sendActionsForControlEvents:UIControlEventTouchUpInside];
                Check(![state[@"flightEnabled"] boolValue],@"Log STOP must disable mock flight");
                Invoke(log,@"close");
                Later(^{
                    Click(root,@"flightButton");
                    Later(^{
                        UIViewController *confirm=root.presentedViewController;
                        [bridge.client disconnect]; state[@"telemetryFresh"]=@NO;
                        // Invoke the action directly to test final revalidation, before any timer refresh.
                        Invoke(confirm,@"go");
                        Check([[bridge valueForKey:@"flightRequests"] integerValue]==1,@"Stale/disconnected confirmation must not enable flight");
                        Check(![[confirm valueForKey:@"enable"] isEnabled],@"Confirm must become disabled on stale state");
                        UIButton *stopModal=FindButton(confirm.view,@"flight.stop"); Check(stopModal.enabled,@"Modal must offer STOP");
                        [stopModal sendActionsForControlEvents:UIControlEventTouchUpInside];
                        Result(YES,@"Camera STOP, separate confirmation, log STOP, stale-state rejection and modal STOP passed");
                    });
                });
            });
        });
    });
}

@interface GAUISmoke : NSObject @end
@implementation GAUISmoke
+ (void)load {
    [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){ Later(^{ Run(); }); }];
}
@end
