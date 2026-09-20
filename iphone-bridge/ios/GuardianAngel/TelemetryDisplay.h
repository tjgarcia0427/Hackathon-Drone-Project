#import <Foundation/Foundation.h>
#include <math.h>

// Observations for display only. Flight control continues to use its original
// GPS-gated pose, ground anchor, freshness checks and arming interlocks.
typedef struct {
    double latitude, longitude, altitude, heading, battery, gimbal;
    double fcTime, batteryTime, gimbalTime;
    BOOL aircraft, mock, gps, homeSet, flying;
    NSInteger gpsSignal, satellites;
} GATelemetrySample;

static inline id GAObservedNumber(double value, BOOL valid) {
    return valid && isfinite(value) ? @(value) : NSNull.null;
}

static inline NSDictionary *GATelemetryReadout(GATelemetrySample sample, double now) {
    BOOL fcFresh=sample.aircraft && sample.fcTime>0 && now>=sample.fcTime && now-sample.fcTime<1.5;
    BOOL batteryFresh=sample.aircraft && sample.batteryTime>0 && now>=sample.batteryTime && now-sample.batteryTime<5;
    BOOL gimbalFresh=sample.aircraft && sample.gimbalTime>0 && now>=sample.gimbalTime && now-sample.gimbalTime<1.5;
    BOOL positionFresh=fcFresh && sample.gps && isfinite(sample.latitude) && isfinite(sample.longitude) &&
        sample.latitude>-85 && sample.latitude<85 && sample.longitude>=-180 && sample.longitude<=180;
    double heading=fmod(sample.heading+360,360);
    return @{@"drone_id":@"air2", @"mock":@(sample.mock), @"aircraft_connected":@(sample.aircraft),
        @"latitude":GAObservedNumber(sample.latitude,positionFresh),
        @"longitude":GAObservedNumber(sample.longitude,positionFresh),
        @"altitude_m":GAObservedNumber(sample.altitude,fcFresh), @"altitude_reference":@"takeoff",
        @"heading_deg":GAObservedNumber(heading,fcFresh),
        @"battery_pct":GAObservedNumber(sample.battery,batteryFresh && sample.battery>=0 && sample.battery<=100),
        @"gimbal_pitch_deg":GAObservedNumber(sample.gimbal,gimbalFresh),
        @"gps_ok":@(fcFresh && sample.gps), @"ground_anchor_ok":@(sample.homeSet),
        @"gps_signal_level":fcFresh?@(sample.gpsSignal):NSNull.null,
        @"satellites":fcFresh?@(sample.satellites):NSNull.null,
        @"flying":fcFresh?@(sample.flying):NSNull.null,
        @"fc_age_ms":GAObservedNumber((now-sample.fcTime)*1000,sample.aircraft && sample.fcTime>0),
        @"battery_age_ms":GAObservedNumber((now-sample.batteryTime)*1000,sample.aircraft && sample.batteryTime>0),
        @"gimbal_age_ms":GAObservedNumber((now-sample.gimbalTime)*1000,sample.aircraft && sample.gimbalTime>0)};
}

// Keep a 5 Hz report schedule on the existing 10 Hz loop. Skip missed slots;
// never queue catch-up samples or change the flight-loop/video timer rates.
static inline BOOL GATelemetryReportDue(double now, double *lastReport) {
    const double interval=0.2;
    double elapsed=now-*lastReport;
    if(elapsed+1e-9<interval) return NO;
    *lastReport+=floor((elapsed+1e-9)/interval)*interval;
    return YES;
}
