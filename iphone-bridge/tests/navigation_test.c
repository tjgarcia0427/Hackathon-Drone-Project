#include "../ios/GuardianAngel/Navigation.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
int main(void) {
    GAPose home={25.7617,-80.1918,10,0};
    GAPose n=GAOffset(home,0,20), e=GAOffset(home,90,20);
    assert(n.lat>home.lat && fabs(n.lon-home.lon)<1e-9);
    assert(e.lon>home.lon && fabs(e.lat-home.lat)<1e-7);
    assert(fabs(GADistance(home.lat,home.lon,n.lat,n.lon)-20)<0.001);
    assert(GAWrap(359)==-1 && GAWrap(-181)==179);
    GAControl c=GANavigate(home,n); assert(c.north>0.99 && fabs(c.east)<1e-6);
    c=GANavigate(home,e); assert(c.east>0.99 && fabs(c.north)<0.001);
    GAPose west=GAOffset(home,270,20); c=GANavigate(home,west); assert(c.east<-.99);
    GAPose high=n; high.altitude=20; c=GANavigate(home,high);
    assert(c.up==0.5 && c.north==0 && c.east==0);
    assert(GAInsideFence(n,home)); assert(!GAInsideFence(GAOffset(home,0,41),home));
    high.altitude=31; assert(!GAInsideFence(high,home));
    high.altitude=NAN; assert(!GAInsideFence(high,home));
    // Integrate bounded velocity commands until arrival from multiple bearings.
    for(int bearing=0;bearing<360;bearing+=30) {
        GAPose p=home, target=GAOffset(home,bearing,25); target.altitude=15;
        int i;
        for(i=0;i<1200;i++) {
            c=GANavigate(p,target);
            assert(hypot(c.north,c.east)<=1.00001 && fabs(c.up)<=0.5);
            if(c.arrived) break;
            p=GAOffset(p,atan2(c.east,c.north)*180/3.141592653589793,hypot(c.north,c.east)*.1);
            p.altitude+=c.up*.1;
        }
        assert(i<1200 && GADistance(p.lat,p.lon,target.lat,target.lon)<=2.01);
    }
    GAPose dateLine={0,179.99999,10,0};
    c=GANavigate(dateLine,GAOffset(dateLine,90,10)); assert(c.east>0);
    puts("Navigation tests passed (bounds, axes, wrap, fence, convergence). ");
}
