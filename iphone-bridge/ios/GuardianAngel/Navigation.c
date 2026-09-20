#include "Navigation.h"
#include <math.h>
static const double R = 6371000.0;
static const double D = 0.017453292519943295;
static double clip(double x, double m) { return fmax(-m, fmin(m, x)); }
double GAWrap(double a) { return a - 360.0 * floor((a + 180.0) / 360.0); }
double GADistance(double a, double b, double c, double d) {
    double s = pow(sin((c-a)*D/2),2) + cos(a*D)*cos(c*D)*pow(sin((d-b)*D/2),2);
    return 2*R*asin(sqrt(fmax(0, fmin(1,s))));
}
GAPose GAOffset(GAPose p, double bearing, double distance) {
    double a=p.lat*D, b=p.lon*D, t=bearing*D, q=distance/R;
    double c=asin(sin(a)*cos(q)+cos(a)*sin(q)*cos(t));
    p.lon=GAWrap((b+atan2(sin(t)*sin(q)*cos(a),cos(q)-sin(a)*sin(c)))/D);
    p.lat=c/D;
    return p;
}
bool GAValidPose(GAPose p) {
    return isfinite(p.lat)&&isfinite(p.lon)&&isfinite(p.altitude)&&isfinite(p.heading)
        && fabs(p.lat)<=90 && fabs(p.lon)<=180;
}
bool GAInsideFence(GAPose p, GAPose home) {
    return GAValidPose(p)&&GAValidPose(home)&&p.altitude>=GA_MIN_ALTITUDE_M&&p.altitude<=GA_MAX_ALTITUDE_M
        && GADistance(p.lat,p.lon,home.lat,home.lon)<=40;
}
GAControl GANavigate(GAPose p, GAPose target) {
    GAControl c={0};
    if (!GAValidPose(p)||!GAValidPose(target)) return c;
    double n=(target.lat-p.lat)*D*R;
    double e=GAWrap(target.lon-p.lon)*D*R*cos(p.lat*D);
    double dist=hypot(n,e), dz=target.altitude-p.altitude;
    c.arrived=dist<=2.0 && fabs(dz)<=0.7;
    // Complete vertical adjustment before translating. No terrain avoidance.
    c.up=fabs(dz)>0.4 ? clip(dz*0.5,0.5) : 0;
    if (fabs(dz)<1.0 && dist>1.2) {
        double speed=fmin(1.0,dist*0.35);
        c.north=n/dist*speed; c.east=e/dist*speed;
    }
    if (c.arrived) c.north=c.east=c.up=0;
    return c;
}
