#ifndef GA_GROUND_ANCHOR_H
#define GA_GROUND_ANCHOR_H
#include "Navigation.h"
#include <math.h>

// Reconnect recovery uses the current aircraft's DJI home point, never its
// airborne position or a cached "OK" flag. Does not enable any flight control.
static inline bool GARecoverAircraftHome(bool gps, bool flying, bool homeLocationSet,
                                        GAPose aircraft, GAPose djiHome, GAPose *out) {
    if(!out || !gps || !flying || !homeLocationSet || !GAValidPose(aircraft) || !GAValidPose(djiHome)) return false;
    if(fabs(aircraft.lat)>=85 || fabs(djiHome.lat)>=85) return false;
    if(GADistance(aircraft.lat,aircraft.lon,djiHome.lat,djiHome.lon)>40) return false;
    *out=(GAPose){djiHome.lat,djiHome.lon,0,aircraft.heading};
    return true;
}
#endif
