#import <Foundation/Foundation.h>
#import "TelemetryDisplay.h"
#include <assert.h>
int main(void) { @autoreleasepool {
    GATelemetrySample sample={0};
    NSDictionary *readout=GATelemetryReadout(sample,100);
    assert(readout[@"altitude_m"]==NSNull.null);
    sample.aircraft=YES; sample.fcTime=sample.batteryTime=sample.gimbalTime=100;
    sample.altitude=0; sample.heading=0; sample.battery=80;
    readout=GATelemetryReadout(sample,100);
    assert([readout[@"altitude_m"] isEqual:@0]); // grounded zero, no GPS/anchor
    assert(readout[@"latitude"]==NSNull.null);
    sample.altitude=12.5; sample.heading=-90;
    readout=GATelemetryReadout(sample,100.2);
    assert([readout[@"altitude_m"] isEqual:@12.5]);
    assert([readout[@"heading_deg"] isEqual:@270]);
    assert(![readout[@"gps_ok"] boolValue]);
    sample.gps=YES; sample.latitude=25.7617; sample.longitude=-80.1918;
    readout=GATelemetryReadout(sample,100.2);
    assert([readout[@"latitude"] isEqual:@25.7617]);
    assert(![readout[@"ground_anchor_ok"] boolValue]); // display can work before navigation can
    readout=GATelemetryReadout(sample,101.5);
    assert(readout[@"altitude_m"]==NSNull.null && readout[@"latitude"]==NSNull.null);
    assert([readout[@"battery_pct"] isEqual:@80]);
    assert(GATelemetryReadout(sample,105)[@"battery_pct"]==NSNull.null);
    sample.altitude=NAN; sample.heading=INFINITY;
    readout=GATelemetryReadout(sample,100.1);
    assert(readout[@"altitude_m"]==NSNull.null && readout[@"heading_deg"]==NSNull.null);
    assert([NSJSONSerialization isValidJSONObject:readout]);
    sample.aircraft=NO;
    assert(GATelemetryReadout(sample,100.1)[@"battery_pct"]==NSNull.null);
    double reportAt=100; int reports=0;
    for(int i=1;i<=100;i++) if(GATelemetryReportDue(100+i*0.1,&reportAt)) reports++;
    assert(reports==50); // five reports/sec without changing the 10 Hz flight loop
    assert(GATelemetryReportDue(120,&reportAt));
    assert(!GATelemetryReportDue(120,&reportAt)); // no catch-up burst
    puts("Telemetry display: GPS-independent altitude, zero, freshness, finite JSON and 5 Hz cadence passed.");
} return 0; }
