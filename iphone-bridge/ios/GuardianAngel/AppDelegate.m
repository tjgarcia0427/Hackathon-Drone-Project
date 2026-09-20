#import <UIKit/UIKit.h>
#import "DroneBridge.h"
#import "Navigation.h"
#import "BridgePresentation.h"
#import <QuartzCore/QuartzCore.h>

// ---------------------------------------------------------------------------
// Design tokens (Guardian Angel redesign handoff, turn 2 / #2a). Public-safety
// direction: USWDS-style palette, square corners, no shadows, no motion.
// Public Sans / Roboto Mono are not bundled; SF Pro / SF Mono at the same
// sizes and weights are the sanctioned fallback.
// ---------------------------------------------------------------------------
static UIColor *Hex(uint32_t rgb) { return [UIColor colorWithRed:((rgb>>16)&0xFF)/255.0 green:((rgb>>8)&0xFF)/255.0 blue:(rgb&0xFF)/255.0 alpha:1]; }
#define GA_NAVY        Hex(0x162E51)
#define GA_PRIMARY     Hex(0x1A4480)
#define GA_INK         Hex(0x1B1B1B)
#define GA_SECONDARY   Hex(0x565C65)
#define GA_MUTED       Hex(0x71767A)
#define GA_DISABLED    Hex(0xA9AEB1)
#define GA_BORDER      Hex(0xDFE1E2)
#define GA_DIVIDER     Hex(0xF0F0F0)
#define GA_PAGE        Hex(0xF0F0F0)
#define GA_CARD        UIColor.whiteColor
#define GA_STOP        Hex(0xB50909)
#define GA_STOP_PRESS  Hex(0x8B0A03)
#define GA_ERROR       Hex(0xD83933)
#define GA_ERROR_TINT  Hex(0xFDF2F2)
#define GA_CAUTION     Hex(0xFFBE2E)
#define GA_CAUTION_DK  Hex(0xE5A000)
#define GA_OK          Hex(0x00A91C)
#define GA_APPROVED    Hex(0x4D8055)
#define GA_INFO_TINT   Hex(0xEFF6FB)
#define GA_UNIT_ID     @"MA2-01"

static UIFont *Sans(CGFloat size, UIFontWeight weight) { return [UIFont systemFontOfSize:size weight:weight]; }
static UIFont *Mono(CGFloat size, UIFontWeight weight) { return [UIFont monospacedSystemFontOfSize:size weight:weight]; }
static UILabel *Label(NSString *text, UIFont *font, UIColor *color) {
    UILabel *l=[UILabel new]; l.text=text; l.font=font; l.textColor=color; l.numberOfLines=0; return l;
}
static void SetCaps(UILabel *l, NSString *text, CGFloat spacing) {
    l.attributedText=[[NSAttributedString alloc] initWithString:(text?:@"").uppercaseString attributes:@{NSKernAttributeName:@(spacing)}];
}
static UILabel *Caps(NSString *text, CGFloat size, UIFontWeight weight, CGFloat spacing, UIColor *color) {
    UILabel *l=[UILabel new]; l.font=Sans(size,weight); l.textColor=color; l.numberOfLines=1; SetCaps(l,text,spacing); return l;
}
static UIView *Card(void) {
    UIView *v=[UIView new]; v.backgroundColor=GA_CARD; v.layer.borderWidth=1; v.layer.borderColor=GA_BORDER.CGColor; v.layer.cornerRadius=4; v.clipsToBounds=YES; return v;
}
static UIView *Rule(UIColor *color) {
    UIView *v=[UIView new]; v.backgroundColor=color; [v.heightAnchor constraintEqualToConstant:1].active=YES; return v;
}
static UIView *Spacer(CGFloat h) { UIView *v=[UIView new]; [v.heightAnchor constraintEqualToConstant:h].active=YES; return v; }
static UIView *Gap(void) { UIView *v=[UIView new]; [v setContentHuggingPriority:1 forAxis:UILayoutConstraintAxisHorizontal]; return v; }
static UIStackView *VStack(CGFloat spacing) {
    UIStackView *s=[UIStackView new]; s.axis=UILayoutConstraintAxisVertical; s.spacing=spacing; return s;
}
static UIStackView *HStack(CGFloat spacing) {
    UIStackView *s=[UIStackView new]; s.axis=UILayoutConstraintAxisHorizontal; s.spacing=spacing; s.alignment=UIStackViewAlignmentCenter; return s;
}
static void Pin(UIView *child, UIView *parent, UIEdgeInsets in) {
    child.translatesAutoresizingMaskIntoConstraints=NO;
    [NSLayoutConstraint activateConstraints:@[
        [child.leadingAnchor constraintEqualToAnchor:parent.leadingAnchor constant:in.left],
        [child.trailingAnchor constraintEqualToAnchor:parent.trailingAnchor constant:-in.right],
        [child.topAnchor constraintEqualToAnchor:parent.topAnchor constant:in.top],
        [child.bottomAnchor constraintEqualToAnchor:parent.bottomAnchor constant:-in.bottom]]];
}
static void PinBottomRule(UIView *rule, UIView *parent) {
    rule.translatesAutoresizingMaskIntoConstraints=NO; [parent addSubview:rule];
    [NSLayoutConstraint activateConstraints:@[[rule.leadingAnchor constraintEqualToAnchor:parent.leadingAnchor],[rule.trailingAnchor constraintEqualToAnchor:parent.trailingAnchor],[rule.bottomAnchor constraintEqualToAnchor:parent.bottomAnchor]]];
}
// Card section header: `TITLE` left, optional meta view right, 1 pt bottom border.
static UIView *CardHeader(NSString *title, UIView *meta, UIEdgeInsets pad) {
    UIView *h=[UIView new];
    UIStackView *row=HStack(8);
    [row addArrangedSubview:Caps(title,11,UIFontWeightBold,1,GA_SECONDARY)];
    if(meta) { [row addArrangedSubview:Gap()]; [row addArrangedSubview:meta]; }
    [h addSubview:row]; Pin(row,h,pad);
    PinBottomRule(Rule(GA_BORDER),h);
    return h;
}

// Filled button with a pressed colour and a disabled style. Radius 4, height 48.
@interface GAButton : UIButton
@property(nonatomic,strong) UIColor *fill, *pressedFill;
@property(nonatomic,strong) NSLayoutConstraint *height;
@end
@implementation GAButton
+ (instancetype)primary:(NSString *)title target:(id)t action:(SEL)a {
    GAButton *b=[GAButton buttonWithType:UIButtonTypeCustom];
    b.fill=GA_PRIMARY; b.pressedFill=GA_NAVY; b.backgroundColor=GA_PRIMARY;
    [b setTitle:title forState:UIControlStateNormal]; b.titleLabel.font=Sans(16,UIFontWeightBold);
    [b setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    [b setTitleColor:GA_SECONDARY forState:UIControlStateDisabled];
    b.layer.cornerRadius=4; b.height=[b.heightAnchor constraintEqualToConstant:48]; b.height.active=YES;
    [b addTarget:t action:a forControlEvents:UIControlEventTouchUpInside]; return b;
}
- (void)setHighlighted:(BOOL)highlighted { [super setHighlighted:highlighted]; if(self.enabled) self.backgroundColor=highlighted?self.pressedFill:self.fill; }
- (void)setEnabled:(BOOL)enabled {
    [super setEnabled:enabled];
    self.backgroundColor=enabled?self.fill:GA_BORDER; self.alpha=enabled?1:0.6;
}
@end

// Gradient scrim used for the camera overlay bars.
@interface GAGradientView : UIView
- (instancetype)initTop:(BOOL)top;
@end
@implementation GAGradientView
+ (Class)layerClass { return CAGradientLayer.class; }
- (instancetype)initTop:(BOOL)top {
    if((self=[super initWithFrame:CGRectZero])) {
        CAGradientLayer *g=(CAGradientLayer *)self.layer;
        UIColor *dark=[UIColor colorWithWhite:0 alpha:0.55], *clear=[UIColor colorWithWhite:0 alpha:0];
        g.colors=top?@[(id)dark.CGColor,(id)clear.CGColor]:@[(id)clear.CGColor,(id)dark.CGColor];
    }
    return self;
}
@end

// One pre-flight procedure row: 24 pt square box, title/detail, uppercase tag.
typedef NS_ENUM(NSInteger, GAStepState) { GAStepLocked, GAStepInProgress, GAStepComplete, GAStepReleased };
@interface GAStepRow : UIView
@property(nonatomic,strong) UIView *box;
@property(nonatomic,strong) UILabel *glyph, *title, *detail, *statusTag;
@property(nonatomic,strong) UIImageView *icon;
- (instancetype)initWithNumber:(NSInteger)n title:(NSString *)title;
- (void)setState:(GAStepState)state detail:(NSString *)detail;
@end
@implementation GAStepRow
- (instancetype)initWithNumber:(NSInteger)n title:(NSString *)title {
    if((self=[super initWithFrame:CGRectZero])) {
        self.box=[UIView new]; self.box.layer.cornerRadius=2; self.box.layer.borderWidth=2;
        [self.box.widthAnchor constraintEqualToConstant:24].active=YES; [self.box.heightAnchor constraintEqualToConstant:24].active=YES;
        self.glyph=[UILabel new]; self.glyph.font=Mono(12,UIFontWeightMedium); self.glyph.textAlignment=NSTextAlignmentCenter; self.glyph.text=[@(n) stringValue];
        self.icon=[UIImageView new]; self.icon.tintColor=UIColor.whiteColor; self.icon.contentMode=UIViewContentModeCenter;
        self.icon.preferredSymbolConfiguration=[UIImageSymbolConfiguration configurationWithPointSize:12 weight:UIImageSymbolWeightBold];
        [self.box addSubview:self.glyph]; Pin(self.glyph,self.box,UIEdgeInsetsZero);
        [self.box addSubview:self.icon]; Pin(self.icon,self.box,UIEdgeInsetsZero);
        self.title=Label(title,Sans(15,UIFontWeightBold),GA_INK);
        self.detail=Label(@"",Sans(12,UIFontWeightRegular),GA_SECONDARY);
        UIStackView *text=VStack(0); [text addArrangedSubview:self.title]; [text addArrangedSubview:self.detail];
        self.statusTag=Caps(@"Locked",10,UIFontWeightBold,0.8,GA_MUTED);
        [self.statusTag setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
        UIStackView *row=HStack(12); [row addArrangedSubview:self.box]; [row addArrangedSubview:text]; [row addArrangedSubview:self.statusTag];
        [self addSubview:row]; Pin(row,self,UIEdgeInsetsMake(10,12,10,12));
        PinBottomRule(Rule(GA_BORDER),self);
    }
    return self;
}
- (void)setState:(GAStepState)state detail:(NSString *)detail {
    self.detail.text=detail; self.icon.hidden=YES; self.glyph.hidden=NO; self.title.textColor=GA_INK; self.backgroundColor=UIColor.clearColor;
    switch(state) {
        case GAStepComplete:
            self.box.backgroundColor=GA_PRIMARY; self.box.layer.borderColor=GA_PRIMARY.CGColor;
            self.icon.image=[UIImage systemImageNamed:@"checkmark"]; self.icon.hidden=NO; self.glyph.hidden=YES;
            SetCaps(self.statusTag,@"Complete",0.8); self.statusTag.textColor=GA_APPROVED; break;
        case GAStepInProgress:
            self.box.backgroundColor=UIColor.whiteColor; self.box.layer.borderColor=GA_PRIMARY.CGColor; self.glyph.textColor=GA_PRIMARY;
            SetCaps(self.statusTag,@"In progress",0.8); self.statusTag.textColor=GA_PRIMARY; self.backgroundColor=GA_INFO_TINT; break;
        case GAStepReleased:
            self.box.backgroundColor=GA_STOP; self.box.layer.borderColor=GA_STOP.CGColor;
            self.icon.image=[UIImage systemImageNamed:@"xmark"]; self.icon.hidden=NO; self.glyph.hidden=YES;
            SetCaps(self.statusTag,@"Released",0.8); self.statusTag.textColor=GA_STOP; self.backgroundColor=GA_ERROR_TINT; break;
        default:
            self.box.backgroundColor=UIColor.whiteColor; self.box.layer.borderColor=GA_DISABLED.CGColor; self.glyph.textColor=GA_DISABLED;
            self.title.textColor=GA_MUTED; SetCaps(self.statusTag,@"Locked",0.8); self.statusTag.textColor=GA_MUTED; break;
    }
}
@end

// Telemetry cell: uppercase label over a mono value. Dividers are drawn by the grid.
@interface GATeleCell : UIView
@property(nonatomic,strong) UILabel *label, *value;
- (instancetype)initWithLabel:(NSString *)label;
@end
@implementation GATeleCell
- (instancetype)initWithLabel:(NSString *)label {
    if((self=[super initWithFrame:CGRectZero])) {
        self.label=Caps(label,10,UIFontWeightRegular,0.8,GA_SECONDARY);
        self.label.adjustsFontSizeToFitWidth=YES; self.label.minimumScaleFactor=0.75;
        self.value=Label(@"—",Mono(17,UIFontWeightMedium),GA_INK); self.value.numberOfLines=1; self.value.adjustsFontSizeToFitWidth=YES; self.value.minimumScaleFactor=0.7;
        UIStackView *v=VStack(2); [v addArrangedSubview:self.label]; [v addArrangedSubview:self.value];
        [self addSubview:v]; Pin(v,self,UIEdgeInsetsMake(10,12,10,12));
    }
    return self;
}
@end

// Mono log line: timestamp in muted, message wraps, 1 pt divider.
static UIView *LogRow(NSString *time, NSString *msg, CGFloat size, UIEdgeInsets pad) {
    UIView *row=[UIView new];
    UILabel *t=Label(time,Mono(size,UIFontWeightRegular),GA_MUTED); t.numberOfLines=1;
    [t setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    [t setContentHuggingPriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    UILabel *m=Label(msg,Mono(size,UIFontWeightRegular),GA_INK);
    UIStackView *h=HStack(10); h.alignment=UIStackViewAlignmentTop; [h addArrangedSubview:t]; [h addArrangedSubview:m];
    [row addSubview:h]; Pin(h,row,pad);
    PinBottomRule(Rule(GA_DIVIDER),row);
    return row;
}

// Navy header shared by the root screen and the pushed log screen (extends under the status bar).
static UIView *NavyHeader(UIView *content) {
    UIView *h=[UIView new]; h.backgroundColor=GA_NAVY;
    [h addSubview:content]; content.translatesAutoresizingMaskIntoConstraints=NO;
    [NSLayoutConstraint activateConstraints:@[
        [content.leadingAnchor constraintEqualToAnchor:h.leadingAnchor constant:16],
        [content.trailingAnchor constraintEqualToAnchor:h.trailingAnchor constant:-16],
        [content.topAnchor constraintEqualToAnchor:h.safeAreaLayoutGuide.topAnchor],
        [content.bottomAnchor constraintEqualToAnchor:h.bottomAnchor constant:-12]]];
    return h;
}

// ---------------------------------------------------------------------------
// Event log (pushed). Full history, newest at the bottom.
// ---------------------------------------------------------------------------
@interface LogViewController : UIViewController
@property(nonatomic,copy) void (^stopAI)(void);
@property(nonatomic,strong) NSArray<NSDictionary *> *entries;
@property(nonatomic,strong) UIStackView *rows;
@property(nonatomic,strong) UIScrollView *scroll;
- (void)reload:(NSArray<NSDictionary *> *)entries;
@end
@implementation LogViewController
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor=GA_PAGE;
    UIStackView *head=HStack(8);
    [head addArrangedSubview:Label(@"Event log",Sans(18,UIFontWeightHeavy),UIColor.whiteColor)];
    [head addArrangedSubview:Gap()];
    UIButton *close=[UIButton buttonWithType:UIButtonTypeSystem];
    [close setTitle:@" Close" forState:UIControlStateNormal]; close.titleLabel.font=Sans(14,UIFontWeightBold); close.tintColor=UIColor.whiteColor;
    [close setImage:[UIImage systemImageNamed:@"xmark"] forState:UIControlStateNormal];
    [close setPreferredSymbolConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:12 weight:UIImageSymbolWeightBold] forImageInState:UIControlStateNormal];
    [close addTarget:self action:@selector(close) forControlEvents:UIControlEventTouchUpInside];
    [head addArrangedSubview:close];
    UIView *header=NavyHeader(head); [self.view addSubview:header]; header.translatesAutoresizingMaskIntoConstraints=NO;
    self.scroll=[UIScrollView new]; [self.view addSubview:self.scroll]; self.scroll.translatesAutoresizingMaskIntoConstraints=NO;
    GAButton *stop=[GAButton primary:@"STOP AI — return control to pilot" target:self action:@selector(stopPressed)];
    stop.fill=GA_STOP; stop.pressedFill=GA_STOP_PRESS; stop.enabled=self.stopAI!=nil;
    stop.titleLabel.adjustsFontSizeToFitWidth=YES; stop.accessibilityIdentifier=@"log.stop";
    [self.view addSubview:stop]; stop.translatesAutoresizingMaskIntoConstraints=NO;
    [NSLayoutConstraint activateConstraints:@[
        [stop.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:16],
        [stop.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-16],
        [stop.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-10]]];
    UIView *card=Card(); [self.scroll addSubview:card]; card.translatesAutoresizingMaskIntoConstraints=NO;
    self.rows=VStack(0); [card addSubview:self.rows]; Pin(self.rows,card,UIEdgeInsetsZero);
    [NSLayoutConstraint activateConstraints:@[
        [header.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[header.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],[header.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.scroll.topAnchor constraintEqualToAnchor:header.bottomAnchor],[self.scroll.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[self.scroll.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],[self.scroll.bottomAnchor constraintEqualToAnchor:stop.topAnchor constant:-10],
        [card.topAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.topAnchor constant:12],[card.bottomAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.bottomAnchor constant:-32],
        [card.leadingAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.leadingAnchor constant:16],[card.trailingAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.trailingAnchor constant:-16],
        [card.widthAnchor constraintEqualToAnchor:self.scroll.frameLayoutGuide.widthAnchor constant:-32]]];
    [self reload:self.entries];
}
- (void)reload:(NSArray<NSDictionary *> *)entries {
    self.entries=entries; if(!self.rows) return;
    for(UIView *v in self.rows.arrangedSubviews.copy) { [self.rows removeArrangedSubview:v]; [v removeFromSuperview]; }
    for(NSDictionary *e in entries) [self.rows addArrangedSubview:LogRow(e[@"t"],e[@"msg"],12,UIEdgeInsetsMake(8,12,8,12))];
    if(!entries.count) [self.rows addArrangedSubview:LogRow(@"",@"No events yet.",12,UIEdgeInsetsMake(8,12,8,12))];
    [self.view layoutIfNeeded];
    CGFloat y=self.scroll.contentSize.height-self.scroll.bounds.size.height+self.scroll.adjustedContentInset.bottom;
    if(y>0) [self.scroll setContentOffset:CGPointMake(0,y) animated:NO];
}
- (void)close { [self.navigationController popViewControllerAnimated:YES]; }
- (void)stopPressed { if(self.stopAI) self.stopAI(); }
@end

// ---------------------------------------------------------------------------
// Flight enable is a direct local pilot action; bridge interlocks remain.

// ---------------------------------------------------------------------------
// Bridge (root). Header / status strip / scroll content / pinned STOP bar.
// ---------------------------------------------------------------------------

@interface BridgeViewController : UIViewController <UITextFieldDelegate>
@property(nonatomic,strong) DroneBridge *bridge;
@property(nonatomic,strong) NSDictionary *telemetry;
@property(nonatomic,strong) NSMutableArray<NSDictionary *> *entries;
@property(nonatomic) NSUInteger logChars;
// header
@property(nonatomic,strong) UILabel *serverText, *aircraftText;
@property(nonatomic,strong) UIView *serverDot, *aircraftDot;
// status strip
@property(nonatomic,strong) UIView *strip;
@property(nonatomic,strong) UIImageView *stripIcon;
@property(nonatomic,strong) UILabel *stripLabel, *stripSub;
// camera
@property(nonatomic,strong) UIView *preview;
@property(nonatomic,strong) UILabel *camSource, *camCoords, *camClock;
@property(nonatomic,strong) UILabel *mockPreview;
// telemetry
@property(nonatomic,strong) NSArray<GATeleCell *> *cells;
// procedure
@property(nonatomic,strong) NSArray<GAStepRow *> *steps;
@property(nonatomic,strong) UILabel *progress;
@property(nonatomic,strong) UIView *actionArea;
@property(nonatomic,strong) UIStackView *actionStack;
@property(nonatomic,strong) UITextField *address;
@property(nonatomic,strong) UISwitch *mockSwitch;
@property(nonatomic,strong) UIView *mockRow, *commandRow;
@property(nonatomic,strong) GAButton *startButton, *connectButton, *cameraButton, *flightButton, *stopButton, *takeoffButton, *authorizeTakeoffButton;
@property(nonatomic,strong) UILabel *cameraHelp, *flightHelp, *commandText;
// log
@property(nonatomic,strong) UIStackView *logTail;
@property(nonatomic,strong) UILabel *logCount;
@property(nonatomic,strong) NSDateFormatter *clock;
@property(nonatomic,strong) UILabel *commandTitle;
@property(nonatomic,strong) NSTimer *displayTimer;
@end

@implementation BridgeViewController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor=GA_PAGE; self.entries=[NSMutableArray new];
    self.clock=[NSDateFormatter new]; self.clock.dateFormat=@"HH:mm:ss";

    // Header ---------------------------------------------------------------
    UIStackView *left=VStack(2);
    [left addArrangedSubview:Caps([NSString stringWithFormat:@"Drone bridge · Unit %@",GA_UNIT_ID],11,UIFontWeightSemibold,1,GA_DISABLED)];
    UILabel *title=Label(@"Guardian Angel",Sans(20,UIFontWeightHeavy),UIColor.whiteColor); title.numberOfLines=1;
    title.attributedText=[[NSAttributedString alloc] initWithString:@"Guardian Angel" attributes:@{NSKernAttributeName:@(-0.2)}];
    [left addArrangedSubview:title];
    UIStackView *right=VStack(4); right.alignment=UIStackViewAlignmentTrailing;
    self.serverDot=[self dot]; self.serverText=Label(@"SERVER OFFLINE",Mono(11,UIFontWeightRegular),GA_BORDER);
    self.aircraftDot=[self dot]; self.aircraftText=Label(@"NO AIRCRAFT",Mono(11,UIFontWeightRegular),GA_BORDER);
    UIStackView *r1=HStack(6); [r1 addArrangedSubview:self.serverDot]; [r1 addArrangedSubview:self.serverText];
    UIStackView *r2=HStack(6); [r2 addArrangedSubview:self.aircraftDot]; [r2 addArrangedSubview:self.aircraftText];
    [right addArrangedSubview:r1]; [right addArrangedSubview:r2];
    UIStackView *headRow=HStack(12); headRow.alignment=UIStackViewAlignmentBottom;
    [headRow addArrangedSubview:left]; [headRow addArrangedSubview:Gap()]; [headRow addArrangedSubview:right];
    UIView *header=NavyHeader(headRow);

    // Status strip -----------------------------------------------------------
    self.strip=[UIView new];
    self.stripIcon=[UIImageView new]; self.stripIcon.contentMode=UIViewContentModeCenter;
    self.stripIcon.preferredSymbolConfiguration=[UIImageSymbolConfiguration configurationWithPointSize:22 weight:UIImageSymbolWeightBold];
    [self.stripIcon.widthAnchor constraintEqualToConstant:28].active=YES;
    self.stripLabel=Caps(@"Not started",15,UIFontWeightHeavy,0.6,GA_INK); self.stripLabel.numberOfLines=0;
    self.stripSub=Label(@"",Sans(13,UIFontWeightRegular),GA_INK); self.stripSub.alpha=0.9;
    UIStackView *stripText=VStack(0); [stripText addArrangedSubview:self.stripLabel]; [stripText addArrangedSubview:self.stripSub];
    UIStackView *stripRow=HStack(12); [stripRow addArrangedSubview:self.stripIcon]; [stripRow addArrangedSubview:stripText];
    [self.strip addSubview:stripRow]; Pin(stripRow,self.strip,UIEdgeInsetsMake(12,16,12,16));

    // Scroll content -----------------------------------------------------------
    UIScrollView *scroll=[UIScrollView new]; scroll.keyboardDismissMode=UIScrollViewKeyboardDismissModeInteractive;
    UIStackView *stack=VStack(12);
    [stack addArrangedSubview:[self buildCamera]];
    [stack addArrangedSubview:[self buildTelemetry]];
    [stack addArrangedSubview:[self buildProcedure]];
    [stack addArrangedSubview:[self buildLog]];
    UILabel *foot=Label(@"Pilot takeoff required: use Take off here, or authorize one agent launch. Keep this app in the foreground. STOP requests takeoff cancellation or releases AI flight control; DJI return-to-home and motor control remain with the aircraft and the pilot's RC. No obstacle or terrain avoidance is provided.",Sans(11,UIFontWeightRegular),GA_SECONDARY);
    [stack addArrangedSubview:foot];
    [scroll addSubview:stack];

    // STOP bar -------------------------------------------------------------------
    UIView *bar=[UIView new]; bar.backgroundColor=UIColor.whiteColor;
    UIView *barRule=Rule(GA_BORDER); [bar addSubview:barRule]; barRule.translatesAutoresizingMaskIntoConstraints=NO;
    self.stopButton=[GAButton primary:@"" target:self action:@selector(stop)];
    self.stopButton.fill=GA_STOP; self.stopButton.pressedFill=GA_STOP_PRESS; self.stopButton.backgroundColor=GA_STOP; self.stopButton.height.constant=56;
    [self.stopButton setAttributedTitle:[[NSAttributedString alloc] initWithString:@"STOP AI — RETURN CONTROL TO PILOT" attributes:@{NSKernAttributeName:@(0.8),NSFontAttributeName:Sans(15,UIFontWeightHeavy),NSForegroundColorAttributeName:UIColor.whiteColor}] forState:UIControlStateNormal];
    [self.stopButton setImage:[UIImage systemImageNamed:@"hand.raised.fill"] forState:UIControlStateNormal];
    self.stopButton.tintColor=UIColor.whiteColor;
    [self.stopButton setPreferredSymbolConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:20 weight:UIImageSymbolWeightBold] forImageInState:UIControlStateNormal];
    self.stopButton.imageEdgeInsets=UIEdgeInsetsMake(0,0,0,10);
    self.stopButton.titleLabel.adjustsFontSizeToFitWidth=YES; self.stopButton.titleLabel.minimumScaleFactor=0.8;
    self.stopButton.enabled=NO; self.stopButton.accessibilityIdentifier=@"bridge.stop";
    [bar addSubview:self.stopButton]; self.stopButton.translatesAutoresizingMaskIntoConstraints=NO;

    for(UIView *v in @[header,self.strip,scroll,bar]) { v.translatesAutoresizingMaskIntoConstraints=NO; [self.view addSubview:v]; }
    stack.translatesAutoresizingMaskIntoConstraints=NO;
    [NSLayoutConstraint activateConstraints:@[
        [header.topAnchor constraintEqualToAnchor:self.view.topAnchor],[header.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[header.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.strip.topAnchor constraintEqualToAnchor:header.bottomAnchor],[self.strip.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[self.strip.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [scroll.topAnchor constraintEqualToAnchor:self.strip.bottomAnchor],[scroll.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[scroll.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],[scroll.bottomAnchor constraintEqualToAnchor:bar.topAnchor],
        [bar.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[bar.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],[bar.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
        [barRule.topAnchor constraintEqualToAnchor:bar.topAnchor],[barRule.leadingAnchor constraintEqualToAnchor:bar.leadingAnchor],[barRule.trailingAnchor constraintEqualToAnchor:bar.trailingAnchor],
        [self.stopButton.topAnchor constraintEqualToAnchor:bar.topAnchor constant:10],[self.stopButton.leadingAnchor constraintEqualToAnchor:bar.leadingAnchor constant:16],[self.stopButton.trailingAnchor constraintEqualToAnchor:bar.trailingAnchor constant:-16],
        [self.stopButton.bottomAnchor constraintEqualToAnchor:bar.safeAreaLayoutGuide.bottomAnchor constant:-10],
        [stack.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor constant:16],
        [stack.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor constant:-16],
        [stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:12],
        [stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-8],
        [stack.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor constant:-32]]];
    UIApplication.sharedApplication.idleTimerDisabled=YES;
    [self render];
}
- (void)viewWillAppear:(BOOL)animated { [super viewWillAppear:animated]; [self.navigationController setNavigationBarHidden:YES animated:NO]; }
- (UIView *)dot { UIView *d=[UIView new]; d.layer.cornerRadius=4; d.backgroundColor=GA_STOP; [d.widthAnchor constraintEqualToConstant:8].active=YES; [d.heightAnchor constraintEqualToConstant:8].active=YES; return d; }

- (UIView *)buildCamera {
    self.preview=[UIView new]; self.preview.backgroundColor=UIColor.blackColor; self.preview.layer.cornerRadius=4; self.preview.clipsToBounds=YES;
    self.preview.layer.borderWidth=1; self.preview.layer.borderColor=GA_SECONDARY.CGColor;
    [self.preview.heightAnchor constraintEqualToAnchor:self.preview.widthAnchor multiplier:9.0/16].active=YES;
    // Overlays live in a sibling so DJIVideoPreviewer keeps sole ownership of the preview's sublayers.
    UIView *overlay=[UIView new]; overlay.userInteractionEnabled=NO; overlay.layer.cornerRadius=4; overlay.clipsToBounds=YES;
    GAGradientView *top=[[GAGradientView alloc] initTop:YES], *bottom=[[GAGradientView alloc] initTop:NO];
    self.camSource=Label(@"NO FEED",Mono(11,UIFontWeightRegular),UIColor.whiteColor); self.camSource.numberOfLines=1;
    UIStackView *topRow=HStack(8); [topRow addArrangedSubview:self.camSource]; [topRow addArrangedSubview:Gap()];
    [topRow addArrangedSubview:Label(@"PREVIEW",Mono(11,UIFontWeightRegular),UIColor.whiteColor)];
    [top addSubview:topRow]; Pin(topRow,top,UIEdgeInsetsMake(8,10,8,10));
    self.camCoords=Label(@"—",Mono(11,UIFontWeightRegular),UIColor.whiteColor); self.camCoords.numberOfLines=1;
    self.camClock=Label(@"",Mono(11,UIFontWeightRegular),UIColor.whiteColor); self.camClock.numberOfLines=1;
    UIStackView *bottomRow=HStack(8); [bottomRow addArrangedSubview:self.camCoords]; [bottomRow addArrangedSubview:Gap()]; [bottomRow addArrangedSubview:self.camClock];
    [bottom addSubview:bottomRow]; Pin(bottomRow,bottom,UIEdgeInsetsMake(8,10,8,10));
    [overlay addSubview:top]; [overlay addSubview:bottom]; top.translatesAutoresizingMaskIntoConstraints=NO; bottom.translatesAutoresizingMaskIntoConstraints=NO;
    [NSLayoutConstraint activateConstraints:@[
        [top.topAnchor constraintEqualToAnchor:overlay.topAnchor],[top.leadingAnchor constraintEqualToAnchor:overlay.leadingAnchor],[top.trailingAnchor constraintEqualToAnchor:overlay.trailingAnchor],
        [bottom.bottomAnchor constraintEqualToAnchor:overlay.bottomAnchor],[bottom.leadingAnchor constraintEqualToAnchor:overlay.leadingAnchor],[bottom.trailingAnchor constraintEqualToAnchor:overlay.trailingAnchor]]];
    UIView *wrap=[UIView new]; [wrap addSubview:self.preview]; Pin(self.preview,wrap,UIEdgeInsetsZero); [wrap addSubview:overlay]; Pin(overlay,wrap,UIEdgeInsetsZero);
    self.mockPreview=Label(@"MOCK HARDWARE\nNo live camera\nTest frames are sent to the server",Mono(12,UIFontWeightRegular),UIColor.whiteColor);
    self.mockPreview.textAlignment=NSTextAlignmentCenter; self.mockPreview.hidden=YES;
    [overlay addSubview:self.mockPreview]; self.mockPreview.translatesAutoresizingMaskIntoConstraints=NO;
    [NSLayoutConstraint activateConstraints:@[
        [self.mockPreview.centerYAnchor constraintEqualToAnchor:overlay.centerYAnchor],
        [self.mockPreview.leadingAnchor constraintEqualToAnchor:overlay.leadingAnchor constant:16],
        [self.mockPreview.trailingAnchor constraintEqualToAnchor:overlay.trailingAnchor constant:-16]]];
    return wrap;
}
- (UIView *)buildTelemetry {
    UIView *card=Card(); UIStackView *v=VStack(0);
    [v addArrangedSubview:CardHeader(@"Telemetry",nil,UIEdgeInsetsMake(8,12,9,12))];
    NSArray *labels=@[@"Battery",@"Altitude",@"Heading",@"GPS fix",@"Ground anchor",@"Speed cap"];
    NSMutableArray *cells=[NSMutableArray new];
    for(int row=0;row<2;row++) {
        UIStackView *h=HStack(0); h.alignment=UIStackViewAlignmentFill; h.distribution=UIStackViewDistributionFillEqually;
        for(int col=0;col<3;col++) {
            GATeleCell *c=[[GATeleCell alloc] initWithLabel:labels[row*3+col]]; [cells addObject:c];
            if(col>0) {
                UIView *vr=[UIView new]; vr.backgroundColor=GA_BORDER; [c addSubview:vr]; vr.translatesAutoresizingMaskIntoConstraints=NO;
                [NSLayoutConstraint activateConstraints:@[[vr.widthAnchor constraintEqualToConstant:1],[vr.leadingAnchor constraintEqualToAnchor:c.leadingAnchor],[vr.topAnchor constraintEqualToAnchor:c.topAnchor],[vr.bottomAnchor constraintEqualToAnchor:c.bottomAnchor]]];
            }
            [h addArrangedSubview:c];
        }
        [v addArrangedSubview:h]; if(row==0) [v addArrangedSubview:Rule(GA_BORDER)];
    }
    self.cells=cells; self.cells[5].value.text=[NSString stringWithFormat:@"%.1f m/s",GA_MAX_SPEED_MPS];
    [card addSubview:v]; Pin(v,card,UIEdgeInsetsZero); return card;
}
- (UIView *)buildProcedure {
    UIView *card=Card(); UIStackView *v=VStack(0);
    self.progress=Label(@"0 / 4",Mono(11,UIFontWeightRegular),GA_SECONDARY); self.progress.numberOfLines=1;
    [v addArrangedSubview:CardHeader(@"Pre-flight procedure",self.progress,UIEdgeInsetsMake(8,12,9,12))];
    NSArray *titles=@[@"Start bridge",@"Connect server",@"Arm camera only",@"Enable flight"];
    NSMutableArray *steps=[NSMutableArray new];
    for(NSUInteger i=0;i<titles.count;i++) { GAStepRow *r=[[GAStepRow alloc] initWithNumber:i+1 title:titles[i]]; [steps addObject:r]; [v addArrangedSubview:r]; }
    self.steps=steps;
    // Action area: every variant is built once; render shows the one for the in-progress step.
    self.actionArea=[UIView new]; self.actionStack=VStack(8);
    self.mockRow=[UIView new]; UIStackView *mr=HStack(8);
    [mr addArrangedSubview:Label(@"Mock hardware (no drone needed)",Sans(14,UIFontWeightRegular),GA_INK)];
    [mr addArrangedSubview:Gap()];
    self.mockSwitch=[UISwitch new]; self.mockSwitch.on=YES; self.mockSwitch.onTintColor=GA_PRIMARY;
    [self.mockSwitch addTarget:self action:@selector(render) forControlEvents:UIControlEventValueChanged];
    [mr addArrangedSubview:self.mockSwitch];
    [self.mockRow addSubview:mr]; Pin(mr,self.mockRow,UIEdgeInsetsMake(0,2,4,0));
    self.startButton=[GAButton primary:@"Start bridge" target:self action:@selector(start)];
    self.startButton.accessibilityIdentifier=@"bridge.start";
    self.address=[UITextField new]; self.address.borderStyle=UITextBorderStyleRoundedRect; self.address.keyboardType=UIKeyboardTypeURL;
    self.address.autocapitalizationType=UITextAutocapitalizationTypeNone; self.address.autocorrectionType=UITextAutocorrectionTypeNo;
    self.address.placeholder=@"http://YOUR-LAPTOP-IP:8000"; self.address.font=Mono(14,UIFontWeightRegular); self.address.delegate=self;
    self.address.text=[[NSUserDefaults standardUserDefaults] stringForKey:@"serverURL"]?:@"http://192.168.1.100:8000";
    self.address.accessibilityLabel=@"Server base URL"; [self.address.heightAnchor constraintEqualToConstant:44].active=YES;
    self.connectButton=[GAButton primary:@"Connect server" target:self action:@selector(connect)];
    self.connectButton.accessibilityIdentifier=@"bridge.connect";
    self.takeoffButton=[GAButton primary:@"Take off (pilot)" target:self action:@selector(takeoff)];
    self.takeoffButton.accessibilityIdentifier=@"pilot.takeoff";
    self.authorizeTakeoffButton=[GAButton primary:@"Authorize one agent launch" target:self action:@selector(authorizeTakeoff)];
    self.authorizeTakeoffButton.accessibilityIdentifier=@"agent.authorizeTakeoff";
    self.cameraButton=[GAButton primary:@"Arm camera only" target:self action:@selector(camera)];
    self.cameraButton.accessibilityIdentifier=@"bridge.camera";
    self.cameraHelp=Label(@"Optional camera check. Server can tilt the gimbal; aircraft flight stays with the pilot.",Sans(12,UIFontWeightRegular),GA_SECONDARY); self.cameraHelp.textAlignment=NSTextAlignmentCenter;
    self.flightButton=[GAButton primary:@"Enable flight" target:self action:@selector(flight)];
    self.flightButton.accessibilityIdentifier=@"bridge.flight";
    self.flightHelp=Label(@"Aircraft airborne at 1–30 m, within 40 m of the anchor. Tap Enable flight when ready.",Sans(12,UIFontWeightRegular),GA_SECONDARY); self.flightHelp.textAlignment=NSTextAlignmentCenter;
    self.commandRow=[UIView new]; UIStackView *cr=HStack(12);
    UIView *amber=[UIView new]; amber.backgroundColor=GA_CAUTION_DK; amber.layer.cornerRadius=5;
    [amber.widthAnchor constraintEqualToConstant:10].active=YES; [amber.heightAnchor constraintEqualToConstant:10].active=YES;
    UIStackView *ct=VStack(0); self.commandTitle=Label(@"Awaiting server command",Sans(14,UIFontWeightBold),GA_INK); [ct addArrangedSubview:self.commandTitle];
    self.commandText=Label(@"Awaiting server command",Mono(12,UIFontWeightRegular),GA_SECONDARY); [ct addArrangedSubview:self.commandText];
    [cr addArrangedSubview:amber]; [cr addArrangedSubview:ct]; [self.commandRow addSubview:cr]; Pin(cr,self.commandRow,UIEdgeInsetsZero);
    for(UIView *x in @[self.mockRow,self.startButton,self.address,self.connectButton,self.takeoffButton,self.authorizeTakeoffButton,self.cameraButton,self.cameraHelp,self.flightButton,self.flightHelp,self.commandRow]) { x.hidden=YES; [self.actionStack addArrangedSubview:x]; }
    [self.actionArea addSubview:self.actionStack]; Pin(self.actionStack,self.actionArea,UIEdgeInsetsMake(12,12,12,12));
    [v addArrangedSubview:self.actionArea];
    [card addSubview:v]; Pin(v,card,UIEdgeInsetsZero); return card;
}
- (UIView *)buildLog {
    UIView *card=Card(); UIStackView *v=VStack(0);
    UIStackView *meta=HStack(6);
    self.logCount=Label(@"0 entries",Mono(11,UIFontWeightRegular),GA_SECONDARY); self.logCount.numberOfLines=1;
    UIImageView *arrow=[[UIImageView alloc] initWithImage:[UIImage systemImageNamed:@"arrow.up.right"]]; arrow.tintColor=GA_SECONDARY;
    arrow.preferredSymbolConfiguration=[UIImageSymbolConfiguration configurationWithPointSize:10 weight:UIImageSymbolWeightBold];
    [meta addArrangedSubview:self.logCount]; [meta addArrangedSubview:arrow];
    UIView *header=CardHeader(@"Event log",meta,UIEdgeInsetsMake(8,12,9,12));
    [header addGestureRecognizer:[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(openLog)]];
    header.isAccessibilityElement=YES; header.accessibilityTraits=UIAccessibilityTraitButton; header.accessibilityLabel=@"Open event log";
    [v addArrangedSubview:header];
    self.logTail=VStack(0); [v addArrangedSubview:self.logTail];
    [card addSubview:v]; Pin(v,card,UIEdgeInsetsZero); return card;
}

// Log ----------------------------------------------------------------------------
- (void)append:(NSString *)line {
    if(!NSThread.isMainThread) { dispatch_async(dispatch_get_main_queue(),^{ [self append:line]; }); return; }
    NSString *msg=line?:@"";
    [self.entries addObject:@{@"t":[self.clock stringFromDate:NSDate.date],@"msg":msg}]; self.logChars+=msg.length+10;
    // Same 12 000-char budget as the previous text view: trim the oldest entries back to ~10 000.
    if(self.logChars>12000) { while(self.entries.count && self.logChars>10000) { self.logChars-=[self.entries[0][@"msg"] length]+10; [self.entries removeObjectAtIndex:0]; } }
    for(UIView *x in self.logTail.arrangedSubviews.copy) { [self.logTail removeArrangedSubview:x]; [x removeFromSuperview]; }
    NSUInteger n=self.entries.count, from=n>4?n-4:0;
    for(NSUInteger i=from;i<n;i++) [self.logTail addArrangedSubview:LogRow(self.entries[i][@"t"],self.entries[i][@"msg"],11.5,UIEdgeInsetsMake(6,12,6,12))];
    self.logCount.text=[NSString stringWithFormat:@"%lu entries",(unsigned long)n];
    UIViewController *top=self.navigationController.topViewController;
    if([top isKindOfClass:LogViewController.class]) [(LogViewController *)top reload:self.entries.copy];
}
- (void)openLog {
    LogViewController *l=[LogViewController new]; l.entries=self.entries.copy;
    __weak typeof(self) weakSelf=self;
    if(self.bridge) l.stopAI=^{ [weakSelf stop]; };
    [self.navigationController pushViewController:l animated:YES];
}

// State ---------------------------------------------------------------------------
- (void)refreshState {
    self.telemetry=self.bridge?[self.bridge telemetry]:nil;
    [self render];
}
- (void)render {
    NSDictionary *t=self.telemetry; GAOpState s=GAStateForTelemetry(t);
    BOOL started=self.bridge!=nil, mock=[t[@"mock"] boolValue], online=[t[@"serverOnline"] boolValue], aircraft=[t[@"aircraft"] boolValue];
    BOOL armed=[t[@"armed"] boolValue], flight=[t[@"flightEnabled"] boolValue];
    BOOL batteryFresh=[t[@"batteryFresh"] boolValue];
    double battery=t?[t[@"battery"] doubleValue]:-1;
    self.serverText.text=online?@"SERVER ONLINE":@"SERVER OFFLINE"; self.serverDot.backgroundColor=online?GA_OK:GA_STOP;
    self.aircraftText.text=started && mock?@"MOCK HARDWARE":started && aircraft?@"MAVIC AIR 2":@"NO AIRCRAFT";
    self.aircraftDot.backgroundColor=started && mock?GA_DISABLED:started && aircraft?GA_OK:GA_STOP;

    UIColor *bg=GA_BORDER, *fg=GA_INK; NSString *icon=@"power", *label=@"Not started", *sub=@"Start the bridge to begin the procedure.";
    switch(s) {
        case GAMock: icon=@"testtube.2"; label=@"Mock mode — no aircraft"; sub=online?@"Simulated hardware. Server online. Nothing will fly.":@"Simulated hardware. Connect the server to continue."; break;
        case GADisarmed: bg=GA_SECONDARY; fg=UIColor.whiteColor; icon=@"lock.fill"; label=@"Disarmed"; sub=aircraft?@"Aircraft connected. App flight control is disabled.":@"Waiting for the aircraft. App control is disabled."; break;
        case GACameraOnly: bg=GA_PRIMARY; fg=UIColor.whiteColor; icon=@"video.fill"; label=mock?@"Mock — camera only":@"Camera only"; sub=mock?@"Simulated gimbal commands. No aircraft will move.":@"Server may tilt the gimbal. Flight stays with the pilot."; break;
        case GAFlight: bg=GA_CAUTION; icon=@"exclamationmark.triangle.fill"; label=mock?@"Mock flight active":@"AI flight control active"; sub=mock?@"Simulated commands only. No aircraft will move.":@"Server may move the aircraft. Keep the RC ready for takeover."; break;
        case GAReturning: bg=GA_SECONDARY; fg=UIColor.whiteColor; icon=@"house.fill"; label=mock?@"Mock return in progress":@"DJI return in progress"; sub=mock?@"Simulated return. No aircraft will move.":@"DJI controls the return. STOP does not cancel DJI return-to-home."; break;
        case GALowBattery: bg=GA_STOP; fg=UIColor.whiteColor; icon=@"battery.25"; label=[NSString stringWithFormat:@"Flight disabled — battery %.0f%%",MAX(battery,0)]; sub=@"At least 30% battery is required to enable flight."; break;
        case GAControlPending: bg=GA_CAUTION; icon=@"clock.fill"; label=[t[@"enabling"] boolValue]?@"Enabling flight control":@"Control change pending"; sub=@"Waiting for DJI confirmation. Keep the RC ready."; break;
        case GAReleaseFailed: bg=GA_STOP; fg=UIColor.whiteColor; icon=@"exclamationmark.triangle.fill"; label=@"Control release unconfirmed"; sub=@"Use RC pause / mode switch. Press STOP to retry release."; break;
        default: break;
    }
    if([t[@"takeoffBusy"] boolValue]) { bg=GA_CAUTION; fg=GA_INK; icon=@"airplane.departure"; label=@"Pilot takeoff"; sub=t[@"takeoffStatus"]?:@"Keep the RC ready"; }
    self.stripIcon.image=[UIImage systemImageNamed:icon]; self.stripIcon.tintColor=fg;
    SetCaps(self.stripLabel,label,0.6); self.stripLabel.textColor=fg; self.stripSub.text=sub; self.stripSub.textColor=fg;
    if(![self.strip.backgroundColor isEqual:bg]) {
        if(UIAccessibilityIsReduceMotionEnabled()) self.strip.backgroundColor=bg;
        else [UIView animateWithDuration:0.2 animations:^{ self.strip.backgroundColor=bg; }];
    }

    // No recording/FPS claim: neither is provided by the bridge's read-only snapshot.
    self.camSource.text=!started?@"NO FEED":mock?@"MOCK — NO CAMERA":aircraft?@"DJI CAMERA":@"NO AIRCRAFT";
    self.mockPreview.hidden=!(started && mock);
    if([t[@"gpsFresh"] boolValue]) {
        double la=[t[@"latitude"] doubleValue], lo=[t[@"longitude"] doubleValue];
        self.camCoords.text=[NSString stringWithFormat:@"%.6f %@  %.6f %@",fabs(la),la<0?@"S":@"N",fabs(lo),lo<0?@"W":@"E"];
        NSTimeInterval at=[t[@"telemetryAt"] doubleValue];
        self.camClock.text=at>0?[self.clock stringFromDate:[NSDate dateWithTimeIntervalSince1970:at]]:@"";
    } else { self.camCoords.text=started?@"GPS / telemetry unavailable":@"—"; self.camClock.text=@""; }
    self.cells[0].value.text=batteryFresh && battery>=0?[NSString stringWithFormat:@"%.0f%%",battery]:@"—";
    self.cells[0].value.textColor=batteryFresh && battery>=0 && battery<30?GA_STOP:GA_INK;
    self.cells[1].value.text=[t[@"altitudeFresh"] boolValue]?[NSString stringWithFormat:@"%.1f m",[t[@"displayAltitude"] doubleValue]]:@"—";
    self.cells[2].value.text=[t[@"headingFresh"] boolValue]?[NSString stringWithFormat:@"%.0f°",[t[@"displayHeading"] doubleValue]]:@"—";
    self.cells[3].value.text=[t[@"gpsFresh"] boolValue]?@"OK":started?@"waiting":@"—";
    self.cells[4].value.text=[t[@"homeSet"] boolValue]?@"Recorded":started?@"waiting":@"—";

    BOOL done[4]={started,online,armed,flight}; NSInteger completed=0;
    NSInteger next=!started?0:!online?1:!armed?2:!flight?3:-1;
    for(int i=0;i<4;i++) {
        if(done[i]) completed++;
        GAStepState rowState=done[i]?GAStepComplete:(i==next?GAStepInProgress:GAStepLocked);
        NSString *detail=@"";
        if(i==0) detail=!started?@"Choose mock or live hardware":mock?@"Mock hardware · no aircraft":aircraft?@"Mavic Air 2 connected":@"Bridge started · waiting for aircraft";
        if(i==1) detail=self.address.text.length?self.address.text:@"Server origin";
        if(i==2) detail=flight?@"Camera included in flight mode":armed?@"Gimbal under server control":@"Optional camera check before flight";
        if(i==3) detail=flight?@"Supervised control enabled":@"Stop camera control first · then enable flight";
        [self.steps[i] setState:rowState detail:detail];
        if(i==2 && online && !armed) SetCaps(self.steps[i].statusTag,@"Optional",0.8);
        if(i==3 && (s==GAControlPending || s==GAReleaseFailed || s==GAReturning)) {
            [self.steps[i] setState:GAStepLocked detail:sub];
            SetCaps(self.steps[i].statusTag,s==GAControlPending?@"Pending":@"Blocked",0.8);
        }
    }
    self.progress.text=[NSString stringWithFormat:@"%ld / 4",(long)completed];
    for(UIView *x in self.actionStack.arrangedSubviews) x.hidden=YES;
    BOOL takeoffBusy=[t[@"takeoffBusy"] boolValue];
    BOOL busy=s==GAControlPending || s==GAReleaseFailed || s==GAReturning || takeoffBusy;
    if(takeoffBusy) sub=t[@"takeoffStatus"]?:@"Takeoff pending; keep the RC ready";
    self.takeoffButton.enabled=started && [t[@"takeoffBlockReason"] isKindOfClass:NSString.class] && ![t[@"takeoffBlockReason"] length];
    self.authorizeTakeoffButton.enabled=self.takeoffButton.enabled || [t[@"agentTakeoffAuthorized"] boolValue];
    [self.authorizeTakeoffButton setTitle:[t[@"agentTakeoffAuthorized"] boolValue]?[NSString stringWithFormat:@"Revoke agent launch (%ld s)",(long)[t[@"agentTakeoffSeconds"] doubleValue]]:@"Authorize one agent launch" forState:UIControlStateNormal];
    self.cameraButton.enabled=started && online && aircraft && !busy && !armed;
    self.flightButton.enabled=started && online && aircraft && !busy;
    [self.flightButton setTitle:armed && !flight?@"Stop camera control":@"Enable flight" forState:UIControlStateNormal];
    if(!started) { self.mockRow.hidden=NO; self.startButton.hidden=NO; }
    else if(!online) { self.address.hidden=NO; self.connectButton.hidden=NO; }
    else if(busy) { self.flightHelp.hidden=NO; self.flightHelp.text=sub; }
    else if(flight) {
        self.commandRow.hidden=NO; NSString *cmd=t[@"command"];
        self.commandTitle.text=cmd.length?@"Server command in progress":@"Awaiting server command";
        self.commandText.text=cmd.length?[NSString stringWithFormat:@"Executing %@",cmd]:@"Supervised flight is enabled";
    } else {
        self.flightButton.hidden=NO; self.flightHelp.hidden=NO;
        self.takeoffButton.hidden=armed || [t[@"flying"] boolValue];
        self.authorizeTakeoffButton.hidden=self.takeoffButton.hidden;
        if(armed) self.flightHelp.text=@"Stop camera control, then tap Enable flight. This button only stops control.";
        else {
            self.cameraButton.hidden=NO; self.cameraHelp.hidden=NO;
            NSString *reason=![t[@"flying"] boolValue] && [t[@"takeoffBlockReason"] length]?t[@"takeoffBlockReason"]:t[@"flightBlockReason"];
            self.flightHelp.text=reason.length?reason:@"Tap Enable flight when the pilot is ready.";
        }
    }
    [self.stopButton setAttributedTitle:[[NSAttributedString alloc] initWithString:takeoffBusy?@"STOP — CANCEL TAKEOFF":@"STOP AI — RETURN CONTROL TO PILOT" attributes:@{NSKernAttributeName:@(0.8),NSFontAttributeName:Sans(15,UIFontWeightHeavy),NSForegroundColorAttributeName:UIColor.whiteColor}] forState:UIControlStateNormal];
    self.mockSwitch.enabled=!started; self.startButton.enabled=!started; self.stopButton.enabled=started;
}

// Actions -----------------------------------------------------------------------------
- (void)start {
    if(self.bridge) return;
    [self.view endEditing:YES];
    self.bridge=[[DroneBridge alloc] initWithPreview:self.preview mock:self.mockSwitch.on];
    __weak typeof(self) weakSelf=self;
    self.bridge.log=^(NSString *s){ [weakSelf append:s]; };
    self.bridge.takeoffPrompt=^(NSString *identifier, void (^respond)(BOOL)) {
        if(!weakSelf || weakSelf.presentedViewController || UIApplication.sharedApplication.applicationState!=UIApplicationStateActive) { respond(NO); return; }
        UIAlertController *prompt=[UIAlertController alertControllerWithTitle:@"Agent requests takeoff" message:@"The agent is asking the pilot to launch. Confirm only with a clear launch area and the RC ready. This request expires in 20 seconds. DJI will rise to about 1.2 m; AI stays disabled. Then enable flight separately." preferredStyle:UIAlertControllerStyleAlert];
        [prompt addAction:[UIAlertAction actionWithTitle:@"Decline" style:UIAlertActionStyleCancel handler:^(UIAlertAction *a){respond(NO);}]];
        [prompt addAction:[UIAlertAction actionWithTitle:@"Take off" style:UIAlertActionStyleDefault handler:^(UIAlertAction *a){respond(YES);}]];
        __weak UIAlertController *weakPrompt=prompt;
        weakSelf.bridge.dismissTakeoffPrompt=^{[weakPrompt dismissViewControllerAnimated:YES completion:nil];};
        [weakSelf presentViewController:prompt animated:YES completion:nil];
    };
    self.bridge.stateUpdated=^(NSDictionary *t){
        __strong typeof(weakSelf) me=weakSelf; if(!me) return;
        if(!NSThread.isMainThread) { dispatch_async(dispatch_get_main_queue(),^{ me.telemetry=t; [me render]; }); return; }
        me.telemetry=t; [me render];
    };
    [self.bridge start];
    [self refreshState];
    self.displayTimer=[NSTimer scheduledTimerWithTimeInterval:0.25 repeats:YES block:^(NSTimer *timer){ [weakSelf refreshState]; }];
    [[NSRunLoop mainRunLoop] addTimer:self.displayTimer forMode:NSRunLoopCommonModes];
}
- (void)connect {
    [self.view endEditing:YES];
    if(!self.bridge) { [self append:@"Start bridge first"]; return; }
    if([self.bridge.client connect:self.address.text]) [[NSUserDefaults standardUserDefaults] setObject:self.address.text forKey:@"serverURL"];
    else [self append:@"Use a server origin such as http://192.168.1.20:8000 (no path)"];
    [self render];
}
- (void)authorizeTakeoff {
    [self.view endEditing:YES];
    if(!self.bridge || self.presentedViewController) return;
    if([[self.bridge telemetry][@"agentTakeoffAuthorized"] boolValue]) { [self.bridge stopAutomation:@"Pilot revoked agent launch"]; return; }
    NSString *problem=[self.bridge takeoffProblem]; if(problem) { [self append:problem]; return; }
    UIAlertController *a=[UIAlertController alertControllerWithTitle:@"Authorize one agent launch?" message:@"For the next 5 minutes, the agent may take off once without another confirmation and enable flight after a stable hover. Confirm the launch area is clear and keep the RC ready. Flight stays within 1–30 m above takeoff and the existing distance/speed limits. STOP, disconnection or leaving this app revokes permission." preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [a addAction:[UIAlertAction actionWithTitle:@"Authorize" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action){[self.bridge authorizeAgentTakeoff];}]];
    [self presentViewController:a animated:YES completion:nil];
}
- (void)takeoff {
    [self.view endEditing:YES];
    if(!self.bridge || self.presentedViewController) return;
    NSString *problem=[self.bridge takeoffProblem];
    if(problem) { [self append:problem]; return; }
    UIAlertController *a=[UIAlertController alertControllerWithTitle:@"Pilot takeoff?" message:@"Confirm the launch area is clear and the pilot has the RC ready. DJI will take off to about 1.2 m. Keep Guardian Angel open: the server connection and ground anchor stay in place. AI flight control stays disabled. Then enable flight when ready." preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [a addAction:[UIAlertAction actionWithTitle:@"Take off" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action){[self.bridge pilotTakeoff];}]];
    [self presentViewController:a animated:YES completion:nil];
}
- (void)camera { [self.bridge armFlight:NO]; [self refreshState]; }
- (void)flight {
    [self refreshState];
    if([self.telemetry[@"armed"] boolValue] && ![self.telemetry[@"flightEnabled"] boolValue]) {
        [self.bridge stopAutomation:@"Camera control stopped locally; tap Enable flight to enable flight"];
        [self refreshState]; return;
    }
    if(!self.bridge || self.presentedViewController || [self.telemetry[@"flightEnabled"] boolValue]) return;
    // The local tap is the pilot's explicit enable action. Recheck the live
    // snapshot, then let DroneBridge independently validate and call DJI.
    if(GACanConfirmFlight([self.bridge telemetry])) [self.bridge armFlight:YES];
    [self refreshState];
}
- (void)stop { [self.bridge stopAutomation:@"Local STOP pressed; pilot control"]; [self refreshState]; }
- (void)dealloc { [self.displayTimer invalidate]; }
- (BOOL)textFieldShouldReturn:(UITextField *)textField { [textField resignFirstResponder]; return YES; }
- (void)textFieldDidEndEditing:(UITextField *)textField { [self render]; }
@end

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation AppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UINavigationController *nav=[[UINavigationController alloc] initWithRootViewController:[BridgeViewController new]];
    nav.navigationBarHidden=YES;
    self.window.rootViewController=nav;
    self.window.overrideUserInterfaceStyle=UIUserInterfaceStyleLight;
    [self.window makeKeyAndVisible]; return YES;
}
@end
int main(int argc,char *argv[]) {
    @autoreleasepool { return UIApplicationMain(argc,argv,nil,NSStringFromClass(AppDelegate.class)); }
}
