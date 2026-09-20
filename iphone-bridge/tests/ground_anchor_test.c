#include "GroundAnchor.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    GAPose launch={25.7617,-80.1918,0,0}, aircraft=GAOffset(launch,90,10), out={0};
    aircraft.altitude=1.2; aircraft.heading=45;
    assert(GARecoverAircraftHome(true,true,true,aircraft,launch,&out));
    assert(out.lat==launch.lat && out.lon==launch.lon && out.altitude==0);
    assert(out.lon!=aircraft.lon); // Must not move the fence to the airborne position.
    assert(!GAInsideFence(aircraft,out)); // Recovery at low hover does not bypass flight altitude limits.
    aircraft.altitude=8;
    assert(GAInsideFence(aircraft,out));
    assert(!GARecoverAircraftHome(false,true,true,aircraft,launch,&out));
    assert(!GARecoverAircraftHome(true,false,true,aircraft,launch,&out));
    assert(!GARecoverAircraftHome(true,true,false,aircraft,launch,&out));
    GAPose invalid=launch; invalid.lat=NAN;
    assert(!GARecoverAircraftHome(true,true,true,aircraft,invalid,&out));
    invalid=launch; invalid.lon=181;
    assert(!GARecoverAircraftHome(true,true,true,aircraft,invalid,&out));
    invalid=launch; invalid.lat=90;
    assert(!GARecoverAircraftHome(true,true,true,aircraft,invalid,&out));
    assert(!GARecoverAircraftHome(true,true,true,aircraft,(GAPose){0},&out));
    aircraft=GAOffset(launch,0,41); aircraft.altitude=8;
    assert(!GARecoverAircraftHome(true,true,true,aircraft,launch,&out));
    assert(!GARecoverAircraftHome(true,true,true,aircraft,launch,NULL));
    puts("Airborne home recovery, exact launch coordinates, invalid GPS/home rejection and unchanged flight envelope passed.");
}
