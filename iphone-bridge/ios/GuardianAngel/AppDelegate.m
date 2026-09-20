#import <UIKit/UIKit.h>
#import "DroneBridge.h"
@interface BridgeViewController : UIViewController
@property(nonatomic,strong) DroneBridge *bridge;
@property(nonatomic,strong) UIView *preview;
@property(nonatomic,strong) UITextField *address;
@property(nonatomic,strong) UISwitch *mockSwitch;
@property(nonatomic,strong) UILabel *status, *takeoffHelp;
@property(nonatomic,strong) UITextView *logView;
@property(nonatomic,strong) UIButton *hardwareButton;
@property(nonatomic,strong) UIButton *takeoffButton, *stopButton;
@end
@implementation BridgeViewController
- (UIButton *)button:(NSString *)title selector:(SEL)selector color:(UIColor *)color {
    UIButton *b=[UIButton buttonWithType:UIButtonTypeSystem];
    [b setTitle:title forState:UIControlStateNormal]; b.titleLabel.font=[UIFont boldSystemFontOfSize:16];
    b.backgroundColor=color; [b setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    b.layer.cornerRadius=10; [b.heightAnchor constraintEqualToConstant:44].active=YES;
    [b addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside]; return b;
}
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor=UIColor.systemBackgroundColor;
    self.title=@"Guardian Angel";
    UIScrollView *scroll=[UIScrollView new]; scroll.translatesAutoresizingMaskIntoConstraints=NO; [self.view addSubview:scroll];
    UIStackView *stack=[UIStackView new]; stack.axis=UILayoutConstraintAxisVertical; stack.spacing=10; stack.translatesAutoresizingMaskIntoConstraints=NO; [scroll addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [scroll.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor],
        [scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],
        [scroll.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor],
        [stack.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor constant:16],
        [stack.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor constant:-16],
        [stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:12],
        [stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-16],
        [stack.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor constant:-32]]];
    UILabel *intro=[UILabel new]; intro.text=@"Local iPhone bridge • Mavic Air 2"; intro.font=[UIFont preferredFontForTextStyle:UIFontTextStyleHeadline]; [stack addArrangedSubview:intro];
    self.preview=[UIView new]; self.preview.backgroundColor=UIColor.blackColor; self.preview.layer.cornerRadius=10; self.preview.clipsToBounds=YES;
    [self.preview.heightAnchor constraintEqualToAnchor:self.preview.widthAnchor multiplier:9.0/16].active=YES; [stack addArrangedSubview:self.preview];
    self.status=[UILabel new]; self.status.numberOfLines=0; self.status.font=[UIFont monospacedSystemFontOfSize:13 weight:UIFontWeightRegular]; self.status.text=@"Start hardware or mock mode below."; [stack addArrangedSubview:self.status];
    UIStackView *mode=[UIStackView new]; mode.axis=UILayoutConstraintAxisHorizontal;
    UILabel *mockLabel=[UILabel new]; mockLabel.text=@"Mock hardware (no drone needed)";
    self.mockSwitch=[UISwitch new]; self.mockSwitch.on=YES;
    [mode addArrangedSubview:mockLabel]; [mode addArrangedSubview:self.mockSwitch]; [stack addArrangedSubview:mode];
    self.hardwareButton=[self button:@"1. Start bridge" selector:@selector(start) color:UIColor.systemBlueColor]; [stack addArrangedSubview:self.hardwareButton];
    self.address=[UITextField new]; self.address.borderStyle=UITextBorderStyleRoundedRect; self.address.keyboardType=UIKeyboardTypeURL;
    self.address.autocapitalizationType=UITextAutocapitalizationTypeNone; self.address.autocorrectionType=UITextAutocorrectionTypeNo;
    self.address.placeholder=@"http://YOUR-LAPTOP-IP:8000";
    self.address.text=[[NSUserDefaults standardUserDefaults] stringForKey:@"serverURL"]?:@"http://192.168.1.100:8000";
    self.address.accessibilityLabel=@"Server base URL"; [stack addArrangedSubview:self.address];
    [stack addArrangedSubview:[self button:@"2. Connect / reconnect server" selector:@selector(connect) color:UIColor.systemBlueColor]];
    self.takeoffButton=[self button:@"3. Take off (pilot)" selector:@selector(takeoff) color:UIColor.systemBlueColor];
    self.takeoffButton.enabled=NO; self.takeoffButton.accessibilityIdentifier=@"pilot.takeoff"; [stack addArrangedSubview:self.takeoffButton];
    self.takeoffHelp=[UILabel new]; self.takeoffHelp.numberOfLines=0; self.takeoffHelp.font=[UIFont systemFontOfSize:12]; self.takeoffHelp.text=@"Start the bridge and connect the server before takeoff."; [stack addArrangedSubview:self.takeoffHelp];
    UIStackView *arms=[UIStackView new]; arms.axis=UILayoutConstraintAxisHorizontal; arms.spacing=8; arms.distribution=UIStackViewDistributionFillEqually;
    [arms addArrangedSubview:[self button:@"Camera only" selector:@selector(camera) color:UIColor.systemTealColor]];
    [arms addArrangedSubview:[self button:@"Enable flight" selector:@selector(flight) color:UIColor.systemOrangeColor]]; [stack addArrangedSubview:arms];
    self.stopButton=[self button:@"STOP AI • return control to pilot" selector:@selector(stop) color:UIColor.systemRedColor]; [stack addArrangedSubview:self.stopButton];
    UILabel *hint=[UILabel new]; hint.numberOfLines=0; hint.font=[UIFont systemFontOfSize:12]; hint.text=@"Use Take off here, then climb with the RC to 5–30 m before enabling AI flight. Keep this app in the foreground. STOP also requests cancellation during takeoff. Otherwise it releases AI flight control; DJI return-to-home continues until the pilot cancels it with the controller."; [stack addArrangedSubview:hint];
    self.logView=[UITextView new]; self.logView.editable=NO; self.logView.font=[UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    self.logView.backgroundColor=UIColor.secondarySystemBackgroundColor; [self.logView.heightAnchor constraintEqualToConstant:190].active=YES; [stack addArrangedSubview:self.logView];
    UIApplication.sharedApplication.idleTimerDisabled=YES;
}
- (void)append:(NSString *)line {
    NSString *text=[self.logView.text stringByAppendingFormat:@"%@ %@\n",[NSDateFormatter localizedStringFromDate:NSDate.date dateStyle:NSDateFormatterNoStyle timeStyle:NSDateFormatterMediumStyle],line];
    if(text.length>12000) text=[text substringFromIndex:text.length-10000];
    self.logView.text=text; [self.logView scrollRangeToVisible:NSMakeRange(text.length,0)];
}
- (void)start {
    if(self.bridge) return;
    self.mockSwitch.enabled=NO; self.hardwareButton.enabled=NO;
    self.bridge=[[DroneBridge alloc] initWithPreview:self.preview mock:self.mockSwitch.on];
    __weak typeof(self) weakSelf=self;
    self.bridge.log=^(NSString *s){[weakSelf append:s];};
    self.bridge.takeoffPrompt=^(NSString *identifier, void (^respond)(BOOL)) {
        if(!weakSelf || weakSelf.presentedViewController || UIApplication.sharedApplication.applicationState!=UIApplicationStateActive) { respond(NO); return; }
        UIAlertController *prompt=[UIAlertController alertControllerWithTitle:@"Agent requests takeoff" message:@"The agent is asking the pilot to launch. Confirm only with a clear launch area and the RC ready. This request expires in 20 seconds. DJI will rise to about 1.2 m; AI stays disabled. Then climb with the RC to 5-30 m and enable flight separately." preferredStyle:UIAlertControllerStyleAlert];
        [prompt addAction:[UIAlertAction actionWithTitle:@"Decline" style:UIAlertActionStyleCancel handler:^(UIAlertAction *a){respond(NO);}]];
        [prompt addAction:[UIAlertAction actionWithTitle:@"Take off" style:UIAlertActionStyleDefault handler:^(UIAlertAction *a){respond(YES);}]];
        __weak UIAlertController *weakPrompt=prompt;
        weakSelf.bridge.dismissTakeoffPrompt=^{[weakPrompt dismissViewControllerAnimated:YES completion:nil];};
        [weakSelf presentViewController:prompt animated:YES completion:nil];
    };
    self.bridge.updated=^(NSString *s){weakSelf.status.text=s; NSString *reason=[weakSelf.bridge takeoffProblem]; weakSelf.takeoffButton.enabled=reason==nil; weakSelf.takeoffHelp.text=reason?:@"Ready for pilot takeoff. Confirm locally; AI stays disabled."; [weakSelf.stopButton setTitle:[weakSelf.bridge pilotTakeoffBusy]?@"STOP • cancel takeoff":@"STOP AI • return control to pilot" forState:UIControlStateNormal];};
    [self.bridge start];
}
- (void)connect {
    [self.view endEditing:YES];
    if(!self.bridge) { [self append:@"Start bridge first"]; return; }
    if([self.bridge.client connect:self.address.text]) [[NSUserDefaults standardUserDefaults] setObject:self.address.text forKey:@"serverURL"];
    else [self append:@"Use a server origin such as http://192.168.1.20:8000 (no path)"];
}
- (void)takeoff {
    [self.view endEditing:YES];
    if(!self.bridge || self.presentedViewController) return;
    NSString *problem=[self.bridge takeoffProblem];
    if(problem) { [self append:problem]; return; }
    UIAlertController *a=[UIAlertController alertControllerWithTitle:@"Pilot takeoff?" message:@"Confirm the launch area is clear and the pilot has the RC ready. DJI will take off to about 1.2 m. Keep Guardian Angel open: the server connection and ground anchor stay in place. AI flight control stays disabled. Then use the RC to climb to 5-30 m before enabling flight." preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [a addAction:[UIAlertAction actionWithTitle:@"Take off" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action){[self.bridge pilotTakeoff];}]];
    [self presentViewController:a animated:YES completion:nil];
}
- (void)camera { [self.bridge armFlight:NO]; }
- (void)flight {
    UIAlertController *a=[UIAlertController alertControllerWithTitle:@"Enable supervised flight?" message:@"The pilot must have the aircraft airborne at 5–30 m in an open area, within 40 m of the recorded launch point. The server can now move it. Keep the RC ready." preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [a addAction:[UIAlertAction actionWithTitle:@"Enable" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action){[self.bridge armFlight:YES];}]];
    [self presentViewController:a animated:YES completion:nil];
}
- (void)stop { [self.bridge stopAutomation:@"Local STOP pressed; pilot control"]; }
@end

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation AppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController=[[UINavigationController alloc] initWithRootViewController:[BridgeViewController new]];
    [self.window makeKeyAndVisible]; return YES;
}
@end
int main(int argc,char *argv[]) {
    @autoreleasepool { return UIApplicationMain(argc,argv,nil,NSStringFromClass(AppDelegate.class)); }
}
