#ifndef GA_NAVIGATION_H
#define GA_NAVIGATION_H
#include <stdbool.h>
#define GA_MIN_ALTITUDE_M 1.0
#define GA_MAX_ALTITUDE_M 30.0
#define GA_MAX_SPEED_MPS 1.0  // horizontal speed cap applied by GANavigate
typedef struct { double lat, lon, altitude, heading; } GAPose;
typedef struct { double north, east, up, yaw; bool arrived; } GAControl;
double GAWrap(double degrees);
double GADistance(double lat1, double lon1, double lat2, double lon2);
GAPose GAOffset(GAPose origin, double bearing, double distance);
bool GAValidPose(GAPose p);
bool GAInsideFence(GAPose p, GAPose home);
GAControl GANavigate(GAPose current, GAPose target);
#endif
