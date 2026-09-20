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
    if([scenario isEqual:@"agent-authorization"]) {
        state[@"flying"]=@NO; state[@"altitude"]=@0; state[@"displayAltitude"]=@0;
        Invoke(root,@"refreshState"); Click(root,@"authorizeTakeoffButton");
        Later(^{
            Check([root.presentedViewController.title isEqual:@"Authorize one agent launch?"],@"Local permission must be explicit");
            Check(![state[@"agentTakeoffAuthorized"] boolValue],@"Opening prompt must not grant permission");
            Check([[bridge valueForKey:@"takeoffRequests"] integerValue]==0,@"Authorization must not immediately launch");
            [root dismissViewControllerAnimated:NO completion:^{
                [bridge authorizeAgentTakeoff]; Invoke(root,@"refreshState");
                Check([state[@"agentTakeoffAuthorized"] boolValue],@"Authorized state must be shown");
                Click(root,@"authorizeTakeoffButton"); Invoke(root,@"refreshState");
                Check(![state[@"agentTakeoffAuthorized"] boolValue],@"Second tap revokes permission");
                Check(bridge.client.connected && [state[@"homeSet"] boolValue],@"Revocation preserves link and anchor");
                Result(YES,@"Agent authorization prompt, countdown state and revocation passed");
            }];
        }); return;
    }
    if([scenario isEqual:@"agent-takeoff-prompt"]) {
        __block NSUInteger responses=0;
        Check(bridge.takeoffPrompt!=nil,@"Agent takeoff prompt must be wired");
        bridge.takeoffPrompt(@"test-request",^(BOOL approved){responses++;});
        Later(^{
            Check([root.presentedViewController isKindOfClass:UIAlertController.class],@"Agent must present a pilot confirmation");
            Check([root.presentedViewController.title isEqual:@"Agent requests takeoff"],@"Agent request must be distinguished from local launch");
            Check(responses==0 && [[bridge valueForKey:@"takeoffRequests"] integerValue]==0,@"Presenting request must not launch or approve");
            Check(bridge.client.connected && [state[@"homeSet"] boolValue],@"Request must retain server and anchor");
            bridge.dismissTakeoffPrompt();
            Later(^{ Check(root.presentedViewController==nil,@"Expired/cancelled request must dismiss"); Result(YES,@"Agent pilot prompt and dismissal passed; no launch"); });
        }); return;
    }
    if([scenario hasPrefix:@"takeoff-"]) {
        state[@"mock"]=@NO; state[@"flying"]=@NO; state[@"altitude"]=@0; state[@"displayAltitude"]=@0;
        Invoke(root,@"refreshState");
        UIButton *takeoff=[root valueForKey:@"takeoffButton"];
        Check(takeoff.enabled && !takeoff.hidden,@"Ready ground state must offer pilot takeoff");
        if([scenario isEqual:@"takeoff-confirm"]) {
            Click(root,@"takeoffButton");
            Later(^{
                Check([root.presentedViewController isKindOfClass:UIAlertController.class],@"Pilot must get a separate confirmation");
                Check([[bridge valueForKey:@"takeoffRequests"] integerValue]==0,@"Opening confirmation must not launch");
                Check(bridge.client.connected && [state[@"homeSet"] boolValue],@"Opening confirmation must retain connection and anchor");
                Result(YES,@"Pilot takeoff confirmation preserves state and does not launch automatically");
            }); return;
        }
        if([scenario isEqual:@"takeoff-pending"]) {
            [bridge pilotTakeoff]; Invoke(root,@"refreshState");
            Check([[bridge valueForKey:@"takeoffRequests"] integerValue]==1,@"Exactly one mock takeoff");
            Check(bridge.client.connected && [state[@"homeSet"] boolValue],@"Takeoff must retain server and ground anchor");
            Check(![state[@"armed"] boolValue] && ![state[@"flightEnabled"] boolValue],@"Takeoff must not enable AI");
            Check(![[root valueForKey:@"flightButton"] isEnabled],@"Flight control must be blocked during takeoff");
            [bridge pilotTakeoff]; Check([[bridge valueForKey:@"takeoffRequests"] integerValue]==1,@"Duplicate launch blocked");
        }
        Later(^{ Result(YES,[scenario stringByAppendingString:@" passed"]); }); return;
    }
    if(![scenario isEqual:@"flow"]) {
        if([scenario isEqual:@"camera"] || [scenario isEqual:@"procedure"]) Click(root,@"cameraButton");
        if([scenario isEqual:@"flight"]) { state[@"mock"]=@NO; state[@"armed"]=@YES; state[@"flightEnabled"]=@YES; }
        if([scenario isEqual:@"returning"]) { state[@"mock"]=@NO; state[@"returning"]=@YES; }
        if([scenario isEqual:@"pending"]) state[@"pendingTransitions"]=@1;
        if([scenario isEqual:@"release-failed"]) { state[@"releaseFailed"]=@YES; state[@"pendingTransitions"]=@1; }
        if([scenario isEqual:@"stale"]) { state[@"telemetryFresh"]=@NO; state[@"positionFresh"]=@NO; state[@"batteryFresh"]=@NO; state[@"altitudeFresh"]=@NO; state[@"headingFresh"]=@NO; state[@"gpsFresh"]=@NO; }
        if([scenario isEqual:@"gps-waiting"]) { state[@"mock"]=@NO; state[@"gps"]=@NO; state[@"homeSet"]=@NO; state[@"positionFresh"]=@NO; state[@"gpsFresh"]=@NO; state[@"displayAltitude"]=@0; }
        if([scenario isEqual:@"low-battery"]) { state[@"mock"]=@NO; state[@"battery"]=@24; }
        Invoke(root,@"refreshState");
        if([scenario isEqual:@"modal"]) { Click(root,@"flightButton"); Check(root.presentedViewController==nil,@"No checklist required"); }
        if([scenario isEqual:@"log"]) Invoke(root,@"openLog");
        Later(^{
            [root.view layoutIfNeeded];
            if([scenario isEqual:@"gps-waiting"] || [scenario isEqual:@"stale"]) {
                NSArray *cells=[root valueForKey:@"cells"];
                UILabel *altitude=[cells[1] valueForKey:@"value"];
                Check([altitude.text isEqual:[scenario isEqual:@"gps-waiting"]?@"0.0 m":@"—"],@"Fresh grounded altitude must display without GPS; stale altitude must be hidden");
            }
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
    Check(root.presentedViewController==nil,@"Enable flight must not show a checklist/modal");
    Check([state[@"flightEnabled"] boolValue],@"Local enable tap must enable mock flight");
    Check([[bridge valueForKey:@"flightRequests"] integerValue]==1,@"Exactly one flight enable request expected");
    Invoke(root,@"openLog");
    Later(^{
        UIViewController *log=root.navigationController.topViewController;
        UIButton *stop=FindButton(log.view,@"log.stop"); Check(stop.enabled,@"STOP must remain accessible in the log");
        [stop sendActionsForControlEvents:UIControlEventTouchUpInside];
        Check(![state[@"flightEnabled"] boolValue],@"Log STOP must disable mock flight");
        Invoke(log,@"close");
        Later(^{
            [bridge.client disconnect]; state[@"telemetryFresh"]=@NO;
            Invoke(root,@"flight");
            Check([[bridge valueForKey:@"flightRequests"] integerValue]==1,@"Stale/disconnected direct action must not enable flight");
            Check(root.presentedViewController==nil,@"No checklist modal on rejected requests");
            Result(YES,@"Direct local enable, camera STOP interlock, log STOP and stale-state rejection passed");
        });
    });
}

@interface GAUISmoke : NSObject @end
@implementation GAUISmoke
+ (void)load {
    // Foreground-only production prompts legitimately refuse while launch is still
    // inactive. Start once after activation, not after an arbitrary launch delay.
    [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
        static dispatch_once_t once; dispatch_once(&once,^{ Later(^{ Run(); }); });
    }];
}
@end
