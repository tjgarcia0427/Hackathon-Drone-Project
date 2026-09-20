#import "DroneBridge.h"
#import "Navigation.h"
#import "GroundAnchor.h" // airborne anchor recovery
#import "PilotTakeoff.h" // pilot takeoff integration
#import "TelemetryDisplay.h" // display-only observations
#import <DJISDK/DJISDK.h>
#import <DJIWidget/DJIVideoPreviewer.h>
#import <QuartzCore/QuartzCore.h>
#include <math.h>

static void Main(dispatch_block_t block) {
    if(NSThread.isMainThread) block(); else dispatch_async(dispatch_get_main_queue(),block);
}
static BOOL Number(NSDictionary *d,NSString *key,double min,double max,double *out) {
    id v=d[key];
    if(![v isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)v)==CFBooleanGetTypeID()) return NO;
    double x=[v doubleValue]; if(!isfinite(x)||x<min||x>max) return NO;
    *out=x; return YES;
}
@interface DroneBridge () <DJISDKManagerDelegate,DJIFlightControllerDelegate,DJIBatteryDelegate,DJIGimbalDelegate,DJIVideoFeedListener,DJIVideoPreviewerFrameControlDelegate,DJIBaseProductDelegate> {
    GAPose _pose, _home, _target;
    GATakeoffPermit _takeoffPermit; BOOL _enableAfterTakeoff, _takeoffSubmitted; // autonomy integration
    double _takeoffPromptDeadline; // agent takeoff integration
    GATakeoff _pilotTakeoff; NSUInteger _takeoffID, _takeoffCancelID; double _takeoffCancelTime; BOOL _motorsOn; DJIFlightMode _takeoffMode; // pilot takeoff integration
    GATelemetrySample _displaySample; // display-only observations
    BOOL _homeSet, _flying, _gps, _armed, _flightEnabled, _enabling, _mock, _closed;
    BOOL _snapshotPending, _returning, _rthAccepted, _releaseFailed;
    double _gimbal, _battery, _horizontalSpeed, _verticalSpeed;
    double _fcTime, _batteryTime, _gimbalTime, _videoTime, _lastTick, _lastReport, _lastFrame, _stableSince;
    double _deadline, _yawTarget, _gimbalTarget, _enableTime, _snapshotTime;
    NSUInteger _generation, _pendingSDKTransitions, _snapshotID;
}
@property(nonatomic,strong,readwrite) BridgeClient *client;
@property(nonatomic,weak) UIView *preview;
@property(nonatomic,strong) DJIFlightController *fc;
@property(nonatomic,strong) DJIAircraft *aircraft;
@property(nonatomic,strong) NSTimer *timer;
@property(nonatomic,strong) NSArray *aircraftDiagnostics; // autonomy integration
@property(nonatomic,copy) NSString *aircraftFirmware, *lastTakeoffError; // autonomy integration
@property(nonatomic,strong) NSDictionary *active;
@property(nonatomic,strong) NSDictionary *remoteTakeoff; // agent takeoff integration
@property(nonatomic,strong) NSMutableDictionary<NSString *,NSDictionary *> *acks;
@property(nonatomic,strong) NSMutableArray<NSString *> *ackOrder;
@end

@implementation DroneBridge
- (instancetype)initWithPreview:(UIView *)preview mock:(BOOL)mock {
    if((self=[super init])) {
        _mock=mock; _battery=-1; self.preview=preview;
        self.client=[BridgeClient new]; self.client.mockHardware=mock; self.acks=[NSMutableDictionary new]; self.ackOrder=[NSMutableArray new];
        __weak typeof(self) weakSelf=self;
        self.client.command=^(NSDictionary *cmd){ [weakSelf accept:cmd]; };
        self.client.diagnostic=^(NSString *message){[weakSelf note:message];};
        self.client.stateChanged=^(BOOL online,NSString *message){
            [weakSelf note:message];
            if(!online) [weakSelf stopAutomation:@"Server link lost"];
        };
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(background) name:UIApplicationWillResignActiveNotification object:nil];
    }
    return self;
}
- (void)note:(NSString *)message { if(self.log) self.log(message); }

// Read-only presentation snapshot. Flight decisions remain in armFlight:/flightProblem.
- (NSDictionary *)telemetry {
    double now=CACurrentMediaTime();
    BOOL fcFresh=_mock || (_fcTime>0 && now-_fcTime<1.5);
    BOOL batteryFresh=_mock || (_batteryTime>0 && now-_batteryTime<5);
    BOOL poseFresh=fcFresh && _gps && _homeSet && GAValidPose(_pose) && GAValidPose(_home);
    NSDictionary *readout=[self aircraftReadout];
    NSString *blocked=nil;
    if(_closed) blocked=@"Bridge is closed";
    else if(_enabling || _returning || _pendingSDKTransitions) blocked=@"Wait for control transition / return to finish";
    else if(_releaseFailed) blocked=@"Control release is unconfirmed. Use RC takeover, then press STOP to retry.";
    else if(!self.client.connected) blocked=@"Connect to the server first";
    else if(!_mock && !self.aircraft) blocked=@"Connect the aircraft first";
    else if(_armed) blocked=@"Stop camera control before enabling flight";
    else blocked=[self flightProblem];
    NSString *action=self.active[@"action"], *identifier=self.active[@"cmd_id"];
    return @{@"started":@(_lastTick>0 && !_closed), @"mock":@(_mock),
             @"aircraft":@(_mock || self.aircraft!=nil), @"serverOnline":@(self.client.connected),
             @"battery":@(_battery), @"batteryFresh":@(batteryFresh), @"positionFresh":@(poseFresh),
             @"displayAltitude":readout[@"altitude_m"], @"displayHeading":readout[@"heading_deg"],
             @"altitudeFresh":@([readout[@"altitude_m"] isKindOfClass:NSNumber.class]),
             @"headingFresh":@([readout[@"heading_deg"] isKindOfClass:NSNumber.class]),
             @"gpsFresh":@([readout[@"latitude"] isKindOfClass:NSNumber.class]),
             @"altitude":@(_pose.altitude), @"heading":@(fmod(_pose.heading+360,360)),
             @"latitude":@(_pose.lat), @"longitude":@(_pose.lon), @"gps":@(_gps), @"homeSet":@(_homeSet),
             @"flying":@(_flying), @"telemetryFresh":@(fcFresh && batteryFresh),
             @"distanceFromHome":@(poseFresh?GADistance(_pose.lat,_pose.lon,_home.lat,_home.lon):-1),
             @"armed":@(_armed), @"flightEnabled":@(_flightEnabled), @"enabling":@(_enabling),
             @"returning":@(_returning), @"releaseFailed":@(_releaseFailed),
             @"agentTakeoffAuthorized":@(GATakeoffPermitValid(_takeoffPermit,now)), @"agentTakeoffSeconds":@(fmax(0,_takeoffPermit.expiresAt-now)),
             @"takeoffBusy":@(GATakeoffBusy(_pilotTakeoff)), @"takeoffStatus":[self takeoffStatus], @"takeoffBlockReason":[self takeoffProblem]?:@"",
             @"pendingTransitions":@(_pendingSDKTransitions), @"flightBlockReason":blocked?:@"",
             @"telemetryAt":@(_fcTime>0 ? NSDate.date.timeIntervalSince1970-(now-_fcTime) : 0),
             @"command":action?[NSString stringWithFormat:@"%@ (%@)",action,identifier?:@"?"]:@""};
}

// BEGIN display-only readout.
- (NSDictionary *)aircraftReadout {
    GATelemetrySample sample=_displaySample;
    sample.latitude=_pose.lat; sample.longitude=_pose.lon;
    if(_mock) { sample.altitude=_pose.altitude; sample.heading=_pose.heading; sample.gpsSignal=5; sample.satellites=16; }
    sample.battery=_battery; sample.gimbal=_gimbal;
    sample.fcTime=_fcTime; sample.batteryTime=_batteryTime; sample.gimbalTime=_gimbalTime;
    sample.aircraft=_mock || self.fc!=nil; sample.mock=_mock;
    sample.gps=_gps; sample.homeSet=_homeSet; sample.flying=_flying;
    return GATelemetryReadout(sample,CACurrentMediaTime());
}
// END display-only readout.
- (void)start {
    _lastTick=CACurrentMediaTime();
    if(_mock) {
        _pose=(GAPose){25.7617,-80.1918,10,0}; _home=_pose; _homeSet=YES; _flying=YES; _gps=YES; _battery=90;
        [self note:@"MOCK hardware: simulated position in Miami; no real aircraft commands."];
    } else {
        NSString *key=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"DJISDKAppKey"];
        if(!key.length || [key containsString:@"REPLACE"]) [self note:@"Set DJI_APP_KEY in Config/Secrets.xcconfig first."];
        else [DJISDKManager registerAppWithDelegate:self];
        [[DJIVideoPreviewer instance] setView:self.preview];
        [DJIVideoPreviewer instance].enableHardwareDecode=NO; // software (FFmpeg) decode: slower but works on every model
        [DJIVideoPreviewer instance].type=DJIVideoPreviewerTypeAutoAdapt;
        // OcuSync 2 aircraft (Mavic Air 2, Mini 2, ...) embed decoding assist info in the feed. The previewer
        // asks its frameControlHandler to parse it via the SDK; without this the decoder never emits a frame.
        [DJIVideoPreviewer instance].frameControlHandler=self;
        [[DJIVideoPreviewer instance] start];
        [[DJISDKManager videoFeeder].primaryVideoFeed addListener:self withQueue:dispatch_get_main_queue()];
    }
    __weak typeof(self) weakSelf=self;
    self.timer=[NSTimer scheduledTimerWithTimeInterval:0.1 repeats:YES block:^(NSTimer *t){[weakSelf tick];}];
    [[NSRunLoop mainRunLoop] addTimer:self.timer forMode:NSRunLoopCommonModes];
}
- (void)appRegisteredWithError:(NSError *)error {
    Main(^{
        if(self->_closed) return;
        [self note:error?[NSString stringWithFormat:@"DJI registration: %@",error.localizedDescription]:@"DJI registered. Connect the controller cable; close DJI Fly."];
        if(!error) [DJISDKManager startConnectionToProduct];
    });
}
- (void)didUpdateDatabaseDownloadProgress:(NSProgress *)progress {}
- (void)productConnected:(DJIBaseProduct *)product {
    Main(^{
        if(self->_closed) return;
        [self stopAutomation:@"Aircraft connected; local control must be enabled again"];
        self->_pilotTakeoff=(GATakeoff){0}; ++self->_takeoffID; // pilot takeoff integration
        self->_homeSet=NO; self->_fcTime=0; self->_batteryTime=0;
        self.fc.delegate=nil; self.aircraft.battery.delegate=nil; self.aircraft.gimbal.delegate=nil;
        self.fc=nil; self.aircraft=nil; self->_gps=NO; self->_gimbalTime=0;
        self->_releaseFailed=NO;
        if(![product isKindOfClass:DJIAircraft.class] || ![product.model isEqualToString:DJIAircraftModelNameMavicAir2]) {
            [self note:[NSString stringWithFormat:@"Expected Mavic Air 2; detected %@. Control unavailable.",product.model]]; return;
        }
        self.aircraft=(DJIAircraft *)product; self.fc=self.aircraft.flightController;
        [self attachTakeoffDiagnostics:product]; // autonomy integration
        self.fc.delegate=self; self.aircraft.battery.delegate=self; self.aircraft.gimbal.delegate=self;
        // The previewer's H.264 decoder needs the encoder profile of the connected product (DJI's sample does this
        // in its VideoPreviewerAdapter). Without it the feed is pushed but never decodes to frames.
        [DJIVideoPreviewer instance].encoderType=H264EncoderType_MavicAir2;
        [[DJIVideoPreviewer instance] reset];
        [self note:@"Mavic Air 2 connected. Establish GPS on the ground before takeoff."];
    });
}
- (void)productChanged:(DJIBaseProduct *)product { [self productConnected:product]; }
- (void)componentConnectedWithKey:(NSString *)key andIndex:(NSInteger)index {
    Main(^{
        if(self->_closed || !self.aircraft) return;
        DJIFlightController *controller=self.aircraft.flightController;
        if(controller!=self.fc) {
            [self stopAutomation:@"Flight controller component changed"];
            self->_pilotTakeoff=(GATakeoff){0}; ++self->_takeoffID; // pilot takeoff integration
            self->_homeSet=NO; self->_fcTime=0; self.fc.delegate=nil; self.fc=controller;
        }
        self.fc.delegate=self; self.aircraft.battery.delegate=self; self.aircraft.gimbal.delegate=self;
    });
}
- (void)productDisconnected {
    Main(^{
        [self stopAutomation:@"Aircraft disconnected"];
        self.fc.delegate=nil; self.aircraft.battery.delegate=nil; self.aircraft.gimbal.delegate=nil;
        self->_pilotTakeoff=(GATakeoff){0}; ++self->_takeoffID; // pilot takeoff integration
        self.fc=nil; self.aircraft=nil; self->_fcTime=0; self->_homeSet=NO;
        self->_gps=NO; self->_gimbalTime=0;
    });
}
- (void)flightController:(DJIFlightController *)fc didUpdateState:(DJIFlightControllerState *)state {
    Main(^{
        if(fc!=self.fc || self->_closed) return;
        CLLocation *location=state.aircraftLocation;
        // BEGIN display-only SDK observations (barometric altitude does not need GPS).
        self->_displaySample.altitude=state.altitude;
        self->_displaySample.heading=state.attitude.yaw;
        self->_displaySample.gpsSignal=state.GPSSignalLevel;
        self->_displaySample.satellites=state.satelliteCount;
        // END display-only SDK observations.
        self->_gps=location && CLLocationCoordinate2DIsValid(location.coordinate) && state.GPSSignalLevel>=DJIGPSSignalLevel4 && state.GPSSignalLevel<=DJIGPSSignalLevel5;
        if(self->_gps) self->_pose=(GAPose){location.coordinate.latitude,location.coordinate.longitude,state.altitude,state.attitude.yaw};
        self->_flying=state.isFlying;
        self->_motorsOn=state.areMotorsOn; self->_takeoffMode=state.flightMode; // pilot takeoff integration
        self->_horizontalSpeed=hypot(state.velocityX,state.velocityY); self->_verticalSpeed=fabs(state.velocityZ);
        self->_fcTime=CACurrentMediaTime();
        if(!self->_homeSet && self->_gps && !state.isFlying) {
            self->_home=self->_pose; self->_homeSet=YES;
            [self note:@"Ground GPS anchor recorded. Restart server state before moving launch site."];
        }
        // BEGIN airborne anchor recovery.
        if(!self->_homeSet && state.homeLocation && CLLocationCoordinate2DIsValid(state.homeLocation.coordinate)) {
            GAPose djiHome={state.homeLocation.coordinate.latitude,state.homeLocation.coordinate.longitude,0,0};
            if(GARecoverAircraftHome(self->_gps,state.isFlying,state.isHomeLocationSet,self->_pose,djiHome,&self->_home)) {
                self->_homeSet=YES;
                [self note:@"Airborne: ground anchor recovered from the aircraft's DJI home point. Reconnect server, then tap Enable flight."];
            }
        }
        // END airborne anchor recovery.
        if(self->_flightEnabled && !self->_returning && (state.flightMode==DJIFlightModeGoHome || state.flightMode==DJIFlightModeAutoLanding))
            [self stopAutomation:@"Aircraft has entered its own return/landing mode; pilot control"];
    });
}
- (void)battery:(DJIBattery *)battery didUpdateState:(DJIBatteryState *)state {
    Main(^{if(battery==self.aircraft.battery){self->_battery=state.chargeRemainingInPercent; self->_batteryTime=CACurrentMediaTime();}});
}
- (void)gimbal:(DJIGimbal *)gimbal didUpdateState:(DJIGimbalState *)state {
    Main(^{if(gimbal==self.aircraft.gimbal){self->_gimbal=state.attitudeInDegrees.pitch; self->_gimbalTime=CACurrentMediaTime();}});
}
- (void)videoFeed:(DJIVideoFeed *)videoFeed didUpdateVideoData:(NSData *)videoData {
    if(_closed || _mock) return;
    _videoTime=CACurrentMediaTime();
    [[DJIVideoPreviewer instance] push:(uint8_t *)videoData.bytes length:(int)videoData.length];
}
#pragma mark - DJIVideoPreviewerFrameControlDelegate (mirrors DJI's sample VideoPreviewerAdapter)
- (BOOL)parseDecodingAssistInfoWithBuffer:(uint8_t *)buffer length:(int)length assistInfo:(DJIDecodingAssistInfo *)assistInfo {
    return [[DJISDKManager videoFeeder].primaryVideoFeed parseDecodingAssistInfoWithBuffer:buffer length:length assistInfo:(void *)assistInfo];
}
- (BOOL)isNeedFitFrameWidth { return YES; }
- (void)syncDecoderStatus:(BOOL)isNormal { [[DJISDKManager videoFeeder].primaryVideoFeed syncDecoderStatus:isNormal]; }
- (void)decodingDidSucceedWithTimestamp:(uint32_t)timestamp { [[DJISDKManager videoFeeder].primaryVideoFeed decodingDidSucceedWithTimestamp:timestamp]; }
- (void)decodingDidFail { [[DJISDKManager videoFeeder].primaryVideoFeed decodingDidFail]; }

// BEGIN agent takeoff request methods.
- (void)finishTakeoffRequest:(BOOL)ok error:(NSString *)error {
    if(!self.remoteTakeoff) return;
    NSString *identifier=self.remoteTakeoff[@"cmd_id"];
    self.remoteTakeoff=nil; _takeoffPromptDeadline=0;
    if(!ok) _enableAfterTakeoff=NO;
    if(self.dismissTakeoffPrompt) self.dismissTakeoffPrompt();
    [self ack:identifier ok:ok error:error];
}
- (void)requestPilotTakeoff:(NSDictionary *)cmd {
    if([self.remoteTakeoff[@"cmd_id"] isEqual:cmd[@"cmd_id"]]) return;
    NSString *problem=[self takeoffProblem];
    if(self.remoteTakeoff || !self.takeoffPrompt || problem || !cmd[@"expires_at_ms"]) {
        [self ack:cmd[@"cmd_id"] ok:NO error:problem?:@"Pilot confirmation unavailable or another request is active"]; return;
    }
    self.lastTakeoffError=nil;
    self.remoteTakeoff=cmd;
    if(GATakeoffConsumePermit(&_takeoffPermit,CACurrentMediaTime())) {
        _enableAfterTakeoff=YES;
        [self note:@"Using the pilot's one-use authorization: takeoff, then enable flight after confirmed hover."];
        [self pilotTakeoff]; return;
    }
    _takeoffPromptDeadline=CACurrentMediaTime()+20;
    NSString *identifier=cmd[@"cmd_id"];
    __weak typeof(self) weakSelf=self;
    [self note:@"Agent requested takeoff. Waiting up to 20 seconds for the pilot; nothing launches automatically."];
    self.takeoffPrompt(identifier,^(BOOL approved){Main(^{
        DroneBridge *s=weakSelf;
        if(!s || ![s.remoteTakeoff[@"cmd_id"] isEqual:identifier] || !s->_takeoffPromptDeadline) return;
        BOOL expired=CACurrentMediaTime()>s->_takeoffPromptDeadline;
        s->_takeoffPromptDeadline=0;
        if(!approved || expired) { [s finishTakeoffRequest:NO error:expired?@"Pilot confirmation expired":@"Pilot declined takeoff"]; return; }
        NSString *issue=[s takeoffProblem];
        if(issue) { [s finishTakeoffRequest:NO error:issue]; return; }
        [s pilotTakeoff]; // same locally-confirmed takeoff path; never arms AI
    });});
}
- (void)updateTakeoffRequest {
    if(!self.remoteTakeoff) return;
    if(_takeoffPromptDeadline) {
        if(CACurrentMediaTime()>_takeoffPromptDeadline) [self finishTakeoffRequest:NO error:@"Pilot confirmation expired"];
    } else if(!GATakeoffBusy(_pilotTakeoff)) {
        [self finishTakeoffRequest:NO error:self.lastTakeoffError?:@"Takeoff did not complete; pilot must verify aircraft state"];
    }
}
- (NSDictionary *)agentControlStatus {
    NSString *problem=[self takeoffProblem];
    return @{@"takeoff_authorized":@(GATakeoffPermitValid(_takeoffPermit,CACurrentMediaTime())),
             @"takeoff_authorization_seconds":@(fmax(0,_takeoffPermit.expiresAt-CACurrentMediaTime())),
             @"takeoff_auto_enable_pending":@(_enableAfterTakeoff), @"flight_enable_pending":@(_enabling),
             @"takeoff_last_error":self.lastTakeoffError?:@"",
             @"takeoff_diagnostics":[self takeoffDiagnostics],
             @"flight_limits":@{@"min_altitude_m":@(GA_MIN_ALTITUDE_M),@"max_altitude_m":@(GA_MAX_ALTITUDE_M),@"max_radius_m":@40,@"max_speed_mps":@1},
             @"takeoff_request_supported":@YES,@"takeoff_ready":@(problem==nil && self.remoteTakeoff==nil),
             @"takeoff_problem":problem?:@"",@"takeoff_pending":@(self.remoteTakeoff!=nil || GATakeoffBusy(_pilotTakeoff)),
             @"camera_enabled":@(_armed),@"flight_enabled":@(_flightEnabled),
             @"home":_homeSet?@[@(_home.lat),@(_home.lon)]:NSNull.null};
}
// END agent takeoff request methods.

// BEGIN autonomy methods.
- (void)authorizeAgentTakeoff {
    NSString *problem=[self takeoffProblem];
    if(problem) { [self note:problem]; return; }
    _takeoffPermit=(GATakeoffPermit){CACurrentMediaTime()+300};
    [self note:@"One agent takeoff + flight enable authorized for 5 minutes. STOP, disconnect or leaving the app revokes it."];
}
- (void)attachTakeoffDiagnostics:(DJIBaseProduct *)product {
    self.aircraftDiagnostics=@[]; self.aircraftFirmware=@"unknown"; self.lastTakeoffError=nil;
    product.delegate=self;
    [product getFirmwarePackageVersionWithCompletion:^(NSString *version,NSError *error){Main(^{
        if(product==self.aircraft && !self->_closed) self.aircraftFirmware=version?:@"unknown";
    });}];
}
- (void)product:(DJIBaseProduct *)product didUpdateDiagnosticsInformation:(NSArray *)information {
    Main(^{
        if(product!=self.aircraft || self->_closed) return;
        NSMutableArray *items=[NSMutableArray new];
        for(DJIDiagnostics *d in information) {
            [items addObject:@{@"code":@(d.code),@"component":@(d.component),@"reason":d.reason?:@"",@"solution":d.solution?:@""}];
        }
        self.aircraftDiagnostics=items;
        if(items.count) [self note:[NSString stringWithFormat:@"DJI diagnostics: %@",items]];
    });
}
- (NSDictionary *)takeoffDiagnostics {
    return @{@"firmware":self.aircraftFirmware?:@"unknown",@"flight_mode":@(_takeoffMode),
             @"flying":@(_flying),@"motors_on":@(_motorsOn),@"gps_ok":@(_gps),
             @"battery_pct":@(isfinite(_battery)?_battery:-1),
             @"altitude_m":isfinite(_pose.altitude)?@(_pose.altitude):NSNull.null,
             @"messages":self.aircraftDiagnostics?:@[]};
}
- (BOOL)canPrepareTakeoff:(NSUInteger)request controller:(DJIFlightController *)controller {
    return request==_takeoffID && controller==self.fc && !_closed &&
        _pilotTakeoff.active && !_pilotTakeoff.interrupted;
}
- (void)failTakeoff:(NSError *)error stage:(NSString *)stage {
    GATakeoffStartResult(&_pilotTakeoff,true); _enableAfterTakeoff=NO;
    // A rejected command does not prove the aircraft stayed grounded.
    if(_flying || _motorsOn || _takeoffMode==DJIFlightModeAutoTakeoff || _takeoffMode==DJIFlightModeAssistedTakeoff) _pilotTakeoff.uncertain=true;
    self.lastTakeoffError=[NSString stringWithFormat:@"%@: %@ (domain %@, code %ld). Check DJI diagnostics; do not auto-retry.",stage,error.localizedDescription,error.domain,(long)error.code];
    [self note:self.lastTakeoffError];
    [self note:[NSString stringWithFormat:@"Takeoff diagnostic snapshot: %@",[self takeoffDiagnostics]]];
    [self finishTakeoffRequest:NO error:self.lastTakeoffError];
}
- (void)launchPreparedTakeoff:(NSUInteger)request controller:(DJIFlightController *)controller {
    if(![self canPrepareTakeoff:request controller:controller]) return;
    const char *problem=GATakeoffProblem((GATakeoff){0},[self takeoffObservation]);
    if(problem) {
        [self failTakeoff:[NSError errorWithDomain:@"GuardianAngel.Takeoff" code:1 userInfo:@{NSLocalizedDescriptionKey:@(problem)}] stage:@"Pre-launch recheck"]; return;
    }
    [self note:[NSString stringWithFormat:@"Submitting DJI takeoff once: %@",[self takeoffDiagnostics]]];
    _takeoffSubmitted=YES;
    [controller startTakeoffWithCompletion:^(NSError *error){Main(^{
        if(request!=self->_takeoffID || controller!=self.fc || self->_closed) return;
        if(error) { [self failTakeoff:error stage:@"DJI takeoff response"]; return; }
        BOOL cancelAgain=GATakeoffStartResult(&self->_pilotTakeoff,false);
        if(!self->_pilotTakeoff.interrupted) [self note:@"DJI accepted takeoff; waiting for fresh telemetry confirming a stable hover."];
        if(cancelAgain) [self cancelPilotTakeoff];
    });}];
}
// END autonomy methods.

// BEGIN pilot takeoff methods.
- (BOOL)pilotTakeoffBusy { return GATakeoffBusy(_pilotTakeoff); }
- (GATakeoffObservation)takeoffObservation {
    double now=CACurrentMediaTime();
    BOOL autoFlight=_takeoffMode==DJIFlightModeAutoTakeoff || _takeoffMode==DJIFlightModeAssistedTakeoff ||
        _takeoffMode==DJIFlightModeGoHome || _takeoffMode==DJIFlightModeAutoLanding;
    return (GATakeoffObservation){
        .foreground=!_closed && _lastTick>0 && UIApplication.sharedApplication.applicationState==UIApplicationStateActive,
        .connected=self.client.connected && now-self.client.lastPong<4,
        .aircraft=_mock || self.fc!=nil, .gps=_gps && GAValidPose(_pose), .anchor=_homeSet && GAValidPose(_home),
        .flying=_flying, .motorsOn=_motorsOn, .autoFlight=autoFlight,
        .aiBusy=_armed || _flightEnabled || _enabling || _returning || _releaseFailed || _pendingSDKTransitions || self.active!=nil,
        .now=now, .fcTime=_fcTime, .batteryTime=_batteryTime, .battery=_battery, .altitude=_pose.altitude,
        .distance=GADistance(_pose.lat,_pose.lon,_home.lat,_home.lon),
        .horizontalSpeed=_horizontalSpeed, .verticalSpeed=_verticalSpeed};
}
- (NSString *)takeoffProblem {
    if(_takeoffPromptDeadline) return @"Answer the pending agent takeoff request"; // agent takeoff integration
    const char *problem=GATakeoffProblem(_pilotTakeoff,[self takeoffObservation]);
    return problem?[NSString stringWithUTF8String:problem]:nil;
}
- (NSString *)takeoffStatus {
    if(_pilotTakeoff.cancelPending) return @"Cancelling takeoff; keep the RC ready";
    if(_pilotTakeoff.uncertain) return @"Takeoff outcome unconfirmed; use RC / STOP to retry cancellation";
    if(_pilotTakeoff.interrupted && _pilotTakeoff.startPending) return @"Waiting for interrupted takeoff response; use RC";
    return @"Taking off; AI flight control remains disabled";
}
- (void)pilotTakeoff {
    // Local confirmation or a consumed local one-use authorization is required.
    NSString *problem=[self takeoffProblem];
    if(problem) { [self note:problem]; return; }
    _takeoffPermit=(GATakeoffPermit){0}; _takeoffSubmitted=NO; self.lastTakeoffError=nil;
    GATakeoffBegin(&_pilotTakeoff,CACurrentMediaTime()); NSUInteger request=++_takeoffID;
    [self note:@"Pilot requested takeoff. Server connection and ground anchor retained; AI remains disabled."];
    if(_mock) { _takeoffSubmitted=YES; GATakeoffStartResult(&_pilotTakeoff,false); _motorsOn=YES; _flying=YES; _pose.altitude=1.2; return; }
    DJIFlightController *controller=self.fc;
    // DJI Fly / a prior session can leave a different control mode on the aircraft.
    // Read it, release it if necessary, and revalidate before issuing ONE launch.
    ++_pendingSDKTransitions;
    [controller getVirtualStickModeEnabledWithCompletion:^(BOOL enabled,NSError *error){Main(^{
        --self->_pendingSDKTransitions;
        if(![self canPrepareTakeoff:request controller:controller]) return;
        if(error) { [self failTakeoff:error stage:@"Read virtual-stick mode"]; return; }
        [self note:enabled?@"Takeoff preparation: releasing virtual-stick mode":@"Takeoff preparation: virtual-stick mode is off"];
        if(!enabled) { [self launchPreparedTakeoff:request controller:controller]; return; }
        ++self->_pendingSDKTransitions;
        [controller setVirtualStickModeEnabled:NO withCompletion:^(NSError *releaseError){Main(^{
            --self->_pendingSDKTransitions;
            if(![self canPrepareTakeoff:request controller:controller]) return;
            if(releaseError) { [self failTakeoff:releaseError stage:@"Release virtual-stick mode"]; return; }
            [self launchPreparedTakeoff:request controller:controller];
        });}];
    });}];
}
- (void)cancelPilotTakeoff {
    if(!_takeoffSubmitted && GATakeoffBusy(_pilotTakeoff)) {
        _pilotTakeoff=(GATakeoff){0}; ++_takeoffID;
        [self note:@"Takeoff preparation cancelled before any launch command was sent."]; return;
    }
    if(!GATakeoffRequestCancel(&_pilotTakeoff)) return;
    [self note:@"Takeoff cancellation requested. Keep the RC ready; this does not stop motors or land the aircraft."];
    if(_mock) { GATakeoffCancelResult(&_pilotTakeoff,false); return; }
    DJIFlightController *controller=self.fc; NSUInteger request=_takeoffID, cancellation=++_takeoffCancelID;
    _takeoffCancelTime=CACurrentMediaTime();
    if(!controller) { GATakeoffCancelResult(&_pilotTakeoff,true); return; }
    [controller cancelTakeoffWithCompletion:^(NSError *error){Main(^{
        if(request!=self->_takeoffID || cancellation!=self->_takeoffCancelID || controller!=self.fc || self->_closed) return;
        GATakeoffCancelResult(&self->_pilotTakeoff,error!=nil);
        [self note:error?[@"Takeoff cancellation unconfirmed; use RC, press STOP to retry: " stringByAppendingString:error.localizedDescription]:@"DJI confirmed takeoff cancellation. Pilot control; AI remains disabled."];
    });}];
}
- (void)updatePilotTakeoff {
    if(_pilotTakeoff.cancelPending && CACurrentMediaTime()-_takeoffCancelTime>5) {
        ++_takeoffCancelID; GATakeoffCancelResult(&_pilotTakeoff,true);
        [self note:@"Takeoff cancellation timed out. Use RC; press STOP to retry. AI remains disabled."];
    }
    GATakeoffEvent event=GATakeoffObserve(&_pilotTakeoff,[self takeoffObservation]);
    if(event==GATakeoffCancelRequired) {
        [self note:@"Takeoff timed out or live checks were lost; requesting cancellation. Use the RC."];
        [self cancelPilotTakeoff];
    } else if(event==GATakeoffComplete) {
        BOOL enable=_enableAfterTakeoff; _enableAfterTakeoff=NO;
        [self finishTakeoffRequest:YES error:nil]; // agent takeoff integration
        [self note:enable?@"Takeoff hover confirmed. Applying the pilot's authorization to enable flight.":@"Takeoff hover confirmed. Tap Enable flight when ready (1-30 m above takeoff)."];
        if(enable) [self armFlight:YES];
    }
}
// END pilot takeoff methods.

- (NSString *)flightProblem {
    if(GATakeoffBusy(_pilotTakeoff)) return [self takeoffStatus]; // pilot takeoff integration
    double now=CACurrentMediaTime();
    if(!_mock && !self.fc) return @"No aircraft connection";
    if(!_homeSet || !_gps || !GAValidPose(_pose)) return @"Need strong GPS and a ground anchor or live DJI home point within 40 m";
    if(now-_fcTime>1.5 || now-_batteryTime>5) return @"Aircraft telemetry is stale";
    if(_battery<30) return @"Battery must be at least 30% to enable flight";
    if(!_flying) return @"Aircraft must take off before enabling flight (1–30 m above takeoff)";
    if(!GAInsideFence(_pose,_home)) return @"Outside local limits: 40 m radius and 1–30 m relative altitude";
    return nil;
}
- (void)armFlight:(BOOL)flight {
    if(self.remoteTakeoff) { [self note:@"Finish or cancel the pilot takeoff request first"]; return; } // agent takeoff integration
    if(GATakeoffBusy(_pilotTakeoff)) { [self note:[self takeoffStatus]]; return; } // pilot takeoff integration
    if(_closed || _enabling || _returning || _pendingSDKTransitions) { [self note:@"Wait for control transition / return to finish"]; return; }
    if(_releaseFailed) { [self note:@"Control release is unconfirmed. Use RC takeover, then press STOP to retry release."]; return; }
    if(!self.client.connected) { [self note:@"Connect to the server first"]; return; }
    if(!_mock && !self.aircraft) { [self note:@"Connect the aircraft first"]; return; }
    if(_armed) { [self note:@"Stop AI control before changing control mode"]; return; }
    if(!flight) { _armed=YES; [self note:@"Camera commands enabled; flight commands remain disabled"]; return; }
    NSString *problem=[self flightProblem]; if(problem) { [self note:problem]; return; }
    _enabling=YES; _enableTime=CACurrentMediaTime(); NSUInteger epoch=++_generation;
    if(_mock) { _enabling=NO; _armed=YES; _flightEnabled=YES; [self note:@"MOCK flight enabled"]; return; }
    DJIFlightController *controller=self.fc;
    controller.rollPitchControlMode=DJIVirtualStickRollPitchControlModeVelocity;
    controller.rollPitchCoordinateSystem=DJIVirtualStickFlightCoordinateSystemGround;
    controller.verticalControlMode=DJIVirtualStickVerticalControlModeVelocity;
    controller.yawControlMode=DJIVirtualStickYawControlModeAngularVelocity;
    ++_pendingSDKTransitions;
    [controller setVirtualStickModeEnabled:YES withCompletion:^(NSError *error){Main(^{
        --self->_pendingSDKTransitions;
        if(epoch!=self->_generation || self->_closed || controller!=self.fc) {
            [self releaseController:controller]; return;
        }
        self->_enabling=NO;
        NSString *issue=[self flightProblem];
        if(error || issue || !self.client.connected) {
            [self releaseController:controller];
            [self note:error.localizedDescription?:issue?:@"Server disconnected"]; return;
        }
        self->_armed=YES; self->_flightEnabled=YES;
        [self note:@"Flight enabled locally. 1 m/s max; controller pilot remains in charge."];
    });}];
}
- (void)sendControl:(GAControl)c {
    if(_mock) {
        _pose=GAOffset(_pose,atan2(c.east,c.north)*180/M_PI,hypot(c.north,c.east)*0.1);
        _pose.altitude+=c.up*0.1; _pose.heading=GAWrap(_pose.heading+c.yaw*0.1);
        _horizontalSpeed=hypot(c.north,c.east); _verticalSpeed=fabs(c.up); return;
    }
    DJIFlightController *controller=self.fc; if(!controller) return;
    // DJI Ground/Velocity uses roll=north, pitch=east (not aircraft-body axes).
    DJIVirtualStickFlightControlData data={0};
    data.roll=c.north; data.pitch=c.east; data.verticalThrottle=c.up; data.yaw=c.yaw;
    NSUInteger epoch=_generation;
    [controller sendVirtualStickFlightControlData:data withCompletion:^(NSError *error){
        if(error) Main(^{if(epoch==self->_generation && self->_flightEnabled) [self stopAutomation:[@"Flight command failed: " stringByAppendingString:error.localizedDescription]];});
    }];
}
- (void)releaseController:(DJIFlightController *)controller {
    if(!controller || _mock) return;
    ++_pendingSDKTransitions;
    [controller setVirtualStickModeEnabled:NO withCompletion:^(NSError *error){Main(^{
        --self->_pendingSDKTransitions;
        if(controller==self.fc) self->_releaseFailed=error!=nil;
        if(error) [self note:[@"Control release failed—use RC pause/mode switch: " stringByAppendingString:error.localizedDescription]];
    });}];
}
- (void)stopAutomation:(NSString *)reason {
    _takeoffPermit=(GATakeoffPermit){0}; _enableAfterTakeoff=NO; // autonomy integration
    [self finishTakeoffRequest:NO error:reason]; // agent takeoff integration
    [self cancelPilotTakeoff]; // pilot takeoff integration
    BOOL hadControl=_flightEnabled || _enabling || _releaseFailed;
    ++_generation; _armed=NO; _flightEnabled=NO; _enabling=NO;
    if(self.active) [self finish:NO error:reason];
    if(hadControl) {
        [self sendControl:(GAControl){0}];
        [self releaseController:self.fc];
    }
    // Do not cancel DJI's own RTH/landing when app or network goes away.
    [self note:reason];
}
- (void)ack:(NSString *)identifier ok:(BOOL)ok error:(NSString *)error {
    if(!identifier.length) return;
    NSMutableDictionary *a=[@{@"type":@"ack",@"cmd_id":identifier,@"ok":@(ok)} mutableCopy];
    if(error.length) a[@"error"]=error;
    self.acks[identifier]=a; [self.ackOrder addObject:identifier];
    if(self.ackOrder.count>256) { [self.acks removeObjectForKey:self.ackOrder.firstObject]; [self.ackOrder removeObjectAtIndex:0]; }
    [self.client send:a];
    [self note:[NSString stringWithFormat:@"%@ %@%@",identifier,ok?@"completed":@"failed",error.length?[@": " stringByAppendingString:error]:@""]];
}
- (void)finish:(BOOL)ok error:(NSString *)error {
    NSString *identifier=self.active[@"cmd_id"]; self.active=nil; _stableSince=0;
    [self ack:identifier ok:ok error:error];
}
- (void)accept:(NSDictionary *)cmd {
    NSString *identifier=cmd[@"cmd_id"], *action=cmd[@"action"];
    if(![identifier isKindOfClass:NSString.class] || !identifier.length || identifier.length>128) return;
    if(self.acks[identifier]) { [self.client send:self.acks[identifier]]; return; }
    if([self.active[@"cmd_id"] isEqual:identifier]) return;
    if([self.remoteTakeoff[@"cmd_id"] isEqual:identifier]) return; // agent takeoff integration
    if(![action isKindOfClass:NSString.class]) { [self ack:identifier ok:NO error:@"Missing action"]; return; }
    if(cmd[@"expires_at_ms"]) {
        double expires;
        if(!Number(cmd,@"expires_at_ms",0,1e15,&expires) || NSDate.date.timeIntervalSince1970*1000>expires) {
            [self ack:identifier ok:NO error:@"Command expired; check server/phone clocks"]; return;
        }
    }
    if([action isEqual:@"stop"]) { [self stopAutomation:@"Server requested stop; pilot control"]; [self ack:identifier ok:YES error:nil]; return; }
    if([action isEqual:@"request_takeoff"]) { [self requestPilotTakeoff:cmd]; return; } // agent takeoff integration
    if(self.remoteTakeoff) { [self ack:identifier ok:NO error:@"Pilot takeoff request pending"]; return; } // agent takeoff integration
    if(!_armed) { [self ack:identifier ok:NO error:@"Local control is disabled"]; return; }
    BOOL hold=[action isEqual:@"hold"], rtl=[action isEqual:@"rtl"];
    if(self.active && !hold && !rtl) { [self ack:identifier ok:NO error:@"Another command is active"]; return; }
    if(_returning) { [self ack:identifier ok:NO error:@"DJI RTH is active; pilot must cancel using the RC"]; return; }
    double a=0,b=0,c=0;
    if([action isEqual:@"gimbal"]) {
        if(!Number(cmd,@"pitch",-90,0,&a)) { [self ack:identifier ok:NO error:@"pitch must be -90..0"]; return; }
        if(!_mock && !self.aircraft.gimbal) { [self ack:identifier ok:NO error:@"Gimbal unavailable"]; return; }
    } else if([action isEqual:@"yaw"]) {
        if(!_flightEnabled || !Number(cmd,@"deg",-180,180,&a)) { [self ack:identifier ok:NO error:@"Enable flight locally; deg must be -180..180"]; return; }
    } else if([action isEqual:@"goto"] || [action isEqual:@"move"]) {
        NSString *issue=[self flightProblem];
        if(!_flightEnabled || issue) { [self ack:identifier ok:NO error:issue?:@"Flight control disabled"]; return; }
        if([action isEqual:@"goto"]) {
            if(!Number(cmd,@"lat",-90,90,&a)||!Number(cmd,@"lng",-180,180,&b)||!Number(cmd,@"alt",GA_MIN_ALTITUDE_M,GA_MAX_ALTITUDE_M,&c)) { [self ack:identifier ok:NO error:@"Invalid goto: lat, lng, alt (1..30 m) required"]; return; }
            _target=(GAPose){a,b,c,_pose.heading};
        } else {
            if(!Number(cmd,@"bearing",0,359.999999,&a)||!Number(cmd,@"dist",0,5,&b)) { [self ack:identifier ok:NO error:@"move requires bearing 0..<360 and dist 0..5 m"]; return; }
            _target=GAOffset(_pose,a,b);
        }
        if(!GAInsideFence(_target,_home)) { [self ack:identifier ok:NO error:@"Target outside 40 m / 1..30 m local fence"]; return; }
    } else if(rtl) {
        if(!_flightEnabled || !_flying || (!_mock && !self.fc)) { [self ack:identifier ok:NO error:@"Flight must be enabled and airborne for RTH"]; return; }
    } else if(!hold) { [self ack:identifier ok:NO error:@"Unsupported action"]; return; }
    if(hold && _flying && !_flightEnabled) { [self ack:identifier ok:NO error:@"Hold requires locally enabled flight control"]; return; }
    if(self.active) [self finish:NO error:@"Preempted by hold/rtl"];
    self.active=cmd; _stableSince=0;
    _deadline=CACurrentMediaTime()+([action isEqual:@"goto"]?110:rtl?170:23);
    [self note:[NSString stringWithFormat:@"Executing %@ (%@)",action,identifier]];
    if([action isEqual:@"yaw"]) _yawTarget=GAWrap(_pose.heading+a);
    if([action isEqual:@"gimbal"]) {
        _gimbalTarget=a;
        if(_mock) { _gimbal=a; return; }
        DJIGimbalRotation *rotation=[DJIGimbalRotation gimbalRotationWithPitchValue:@(a) rollValue:nil yawValue:nil time:1 mode:DJIGimbalRotationModeAbsoluteAngle ignore:YES];
        [self.aircraft.gimbal rotateWithRotation:rotation completion:^(NSError *error){Main(^{
            if(error && [self.active[@"cmd_id"] isEqual:identifier]) [self finish:NO error:error.localizedDescription];
        });}];
    }
    if(rtl) {
        _returning=YES; _rthAccepted=NO; _armed=NO;
        [self sendControl:(GAControl){0}]; _flightEnabled=NO;
        if(_mock) { _rthAccepted=YES; _target=_home; _target.altitude=_pose.altitude; return; }
        NSUInteger epoch=++_generation; DJIFlightController *controller=self.fc;
        ++_pendingSDKTransitions;
        [controller setVirtualStickModeEnabled:NO withCompletion:^(NSError *error){Main(^{
            --self->_pendingSDKTransitions;
            if(epoch!=self->_generation || ![self.active[@"cmd_id"] isEqual:identifier]) { self->_returning=NO; return; }
            if(error) { self->_returning=NO; [self finish:NO error:error.localizedDescription]; return; }
            [controller startGoHomeWithCompletion:^(NSError *goError){Main(^{
                if(goError && [self.active[@"cmd_id"] isEqual:identifier]) { self->_returning=NO; [self finish:NO error:goError.localizedDescription]; }
                else if(!goError) {
                    self->_rthAccepted=YES;
                    [self note:@"DJI RTH initiated; acknowledgment waits for landing. Pilot may need to confirm landing on RC."];
                }
            });}];
        });}];
    }
}
- (void)tick {
    if(_closed) return;
    double now=CACurrentMediaTime(), gap=now-_lastTick; _lastTick=now;
    if(_mock) _fcTime=_batteryTime=_gimbalTime=now;
    [self updatePilotTakeoff]; // pilot takeoff integration
    [self updateTakeoffRequest]; // agent takeoff integration
    if(_enabling && now-_enableTime>5) [self stopAutomation:@"Timed out enabling flight control"];
    if(_armed || _flightEnabled) {
        NSString *problem=nil;
        if(gap>0.6) problem=@"Control loop stalled; pilot control";
        else if(!self.client.connected || now-self.client.lastPong>4) problem=@"Server heartbeat expired";
        else if(!_mock && !self.fc) problem=@"Aircraft link lost";
        else if(_flightEnabled && (now-_fcTime>1.5 || now-_batteryTime>5 || !_gps)) problem=@"Flight telemetry/GPS lost";
        else if(_flightEnabled && _battery<25) problem=@"Low battery; pilot must return and land";
        else if(_flightEnabled && (!_flying || !GAInsideFence(_pose,_home))) problem=@"Aircraft left local flight envelope; pilot control";
        else if(_flightEnabled && !_mock && ![self.fc isVirtualStickControlModeAvailable]) problem=@"Virtual stick unavailable; pilot control";
        if(problem) [self stopAutomation:problem];
    }
    if(self.active && now>_deadline) [self stopAutomation:@"Command completion timed out; pilot control (DJI RTH continues if active)"];
    GAControl control={0}; BOOL arrived=NO;
    // Simulate DJI's independent RTH even if the app cancels its pending acknowledgment.
    if(_mock && _returning) {
        GAControl returningControl={0};
        if(GADistance(_pose.lat,_pose.lon,_home.lat,_home.lon)>2) returningControl=GANavigate(_pose,_target);
        else { returningControl.up=-0.5; if(_pose.altitude<=0.2) {_flying=NO;_pose.altitude=0;returningControl.up=0;} }
        [self sendControl:returningControl];
    }
    NSString *action=self.active[@"action"];
    if([action isEqual:@"goto"] || [action isEqual:@"move"]) { control=GANavigate(_pose,_target); arrived=control.arrived; }
    else if([action isEqual:@"yaw"]) {
        double error=GAWrap(_yawTarget-_pose.heading);
        control.yaw=fmax(-10,fmin(10,error*0.8)); arrived=fabs(error)<3;
        if(arrived) control.yaw=0;
    } else if([action isEqual:@"gimbal"]) arrived=now-_gimbalTime<1.5 && fabs(_gimbal-_gimbalTarget)<3;
    else if([action isEqual:@"hold"]) arrived=!_flying || (_horizontalSpeed<0.4 && _verticalSpeed<0.3);
    else if([action isEqual:@"rtl"]) {
        arrived=_rthAccepted && !_flying && now-_fcTime<1.5;
    }
    if(_flightEnabled) [self sendControl:control];
    if(self.active) {
        BOOL settled=arrived && ([action isEqual:@"gimbal"] || [action isEqual:@"rtl"] || (_horizontalSpeed<0.4 && _verticalSpeed<0.3));
        if(settled) { if(!_stableSince) _stableSince=now; if(now-_stableSince>=1.0) [self finish:YES error:nil]; }
        else _stableSince=0;
    }
    if(_returning && !_flying && now-_fcTime<1.5) _returning=NO;
    // BEGIN display-only reporting. The complete navigation packet keeps its original gates.
    if(GATelemetryReportDue(now,&_lastReport)) {
        NSDictionary *readout=[self aircraftReadout];
        NSString *status=_returning?@"rtl":self.active?@"searching":@"idle";
        if(_gps && _homeSet && GAValidPose(_pose) && now-_fcTime<1.5 && now-_batteryTime<5 && _battery>=0)
            [self.client send:@{@"type":@"telemetry",@"drone_id":@"air2",@"latitude":@(_pose.lat),@"longitude":@(_pose.lon),@"altitude_m":@(_pose.altitude),@"heading_deg":@(fmod(_pose.heading+360,360)),@"gimbal_pitch_deg":@(_gimbal),@"battery_pct":@(_battery),@"status":status,@"home_latitude":@(_home.lat),@"home_longitude":@(_home.lon),@"aircraft":readout,@"control":[self agentControlStatus]}];
        else
            [self.client send:@{@"type":@"aircraft_status",@"aircraft":readout,@"control":[self agentControlStatus]}];
        NSString *(^value)(NSString *,NSString *)=^NSString *(NSString *key,NSString *format) {
            id number=readout[key]; return [number isKindOfClass:NSNumber.class]?[NSString stringWithFormat:format,[number doubleValue]]:@"—";
        };
        if(self.updated) self.updated([NSString stringWithFormat:@"%@ • %@\nBattery %@ • Alt %@ (takeoff) • Heading %@\nPosition %@, %@\nGPS %@ • Ground anchor %@ • %@",_mock?@"MOCK":self.aircraft?@"Mavic Air 2":@"No aircraft",self.client.connected?@"Server online":@"Server offline",value(@"battery_pct",@"%.0f%%"),value(@"altitude_m",@"%.1f m"),value(@"heading_deg",@"%.0f°"),value(@"latitude",@"%.6f"),value(@"longitude",@"%.6f"),[readout[@"gps_ok"] boolValue]?@"OK":@"waiting",_homeSet?@"OK":@"waiting",GATakeoffBusy(_pilotTakeoff)?[self takeoffStatus]:_returning?@"DJI RETURNING":_flightEnabled?@"FLIGHT ENABLED":_armed?@"CAMERA ONLY":@"DISARMED"]);
        if(self.stateUpdated) self.stateUpdated([self telemetry]);
    }
    // END display-only reporting.
    if(now-_lastFrame>=1 && self.client.connected) { _lastFrame=now; [self frame]; }
}
- (void)frame {
    if(_mock) {
        UIGraphicsImageRendererFormat *format=[UIGraphicsImageRendererFormat defaultFormat]; format.scale=1;
        UIGraphicsImageRenderer *renderer=[[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(640,360) format:format];
        UIImage *im=[renderer imageWithActions:^(UIGraphicsImageRendererContext *context){
            [UIColor.darkGrayColor setFill]; UIRectFill(CGRectMake(0,0,640,360));
            [@"MOCK DRONE — NO CAMERA\nNetwork test only; no person detection" drawInRect:CGRectMake(24,130,590,130) withAttributes:@{NSFontAttributeName:[UIFont systemFontOfSize:24],NSForegroundColorAttributeName:UIColor.whiteColor}];
        }];
        [self.client uploadJPEG:UIImageJPEGRepresentation(im,0.6)]; return;
    }
    double requested=CACurrentMediaTime();
    if(_snapshotPending && requested-_snapshotTime>2) { _snapshotPending=NO; ++_snapshotID; }
    if(_snapshotPending || requested-_videoTime>1) return;
    _snapshotPending=YES; _snapshotTime=requested;
    NSUInteger snapshotID=++_snapshotID, connectionID=self.client.connectionID;
    __weak typeof(self) weakSelf=self;
    [[DJIVideoPreviewer instance] snapshotPreview:^(UIImage *snapshot){Main(^{
        DroneBridge *s=weakSelf; if(!s || snapshotID!=s->_snapshotID) return; s->_snapshotPending=NO;
        if(s->_closed || connectionID!=s.client.connectionID || !snapshot || snapshot.size.width<=0 || snapshot.size.height<=0 || CACurrentMediaTime()-requested>2 || CACurrentMediaTime()-s->_videoTime>1) return;
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
            CGFloat scale=640.0/MAX(snapshot.size.width,snapshot.size.height);
            UIGraphicsImageRendererFormat *format=[UIGraphicsImageRendererFormat defaultFormat]; format.scale=1;
            UIGraphicsImageRenderer *renderer=[[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(snapshot.size.width*scale,snapshot.size.height*scale) format:format];
            UIImage *small=[renderer imageWithActions:^(UIGraphicsImageRendererContext *ctx){[snapshot drawInRect:CGRectMake(0,0,snapshot.size.width*scale,snapshot.size.height*scale)];}];
            NSData *jpeg=UIImageJPEGRepresentation(small,0.65);
            Main(^{if(!s->_closed && connectionID==s.client.connectionID && CACurrentMediaTime()-requested<2) [s.client uploadJPEG:jpeg];});
        });
    });}];
}
- (void)background { ++_snapshotID; _snapshotPending=NO; [self stopAutomation:@"App inactive; pilot control"]; [self.client disconnect]; }
- (void)shutdown {
    [self stopAutomation:@"Bridge closed"]; _closed=YES;
    [self.client disconnect]; [self.timer invalidate]; self.timer=nil;
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    if(!_mock) { [DJIVideoPreviewer instance].frameControlHandler=nil; [[DJISDKManager videoFeeder].primaryVideoFeed removeListener:self]; [[DJIVideoPreviewer instance] unSetView]; [[DJIVideoPreviewer instance] close]; }
}
- (void)dealloc { [[NSNotificationCenter defaultCenter] removeObserver:self]; }
@end
