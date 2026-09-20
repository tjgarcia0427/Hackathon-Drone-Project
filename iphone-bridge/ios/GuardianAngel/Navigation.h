#ifndef GA_NAVIGATION_H
#define GA_NAVIGATION_H
#include <stdbool.h>
typedef struct { double lat, lon, altitude, heading; } GAPose;
typedef struct { double north, east, up, yaw; bool arrived; } GAControl;
double GAWrap(double degrees);
double GADistance(double lat1, double lon1, double lat2, double lon2);
GAPose GAOffset(GAPose origin, double bearing, double distance);
bool GAValidPose(GAPose p);
bool GAInsideFence(GAPose p, GAPose home);
GAControl GANavigate(GAPose current, GAPose target);
#endif
