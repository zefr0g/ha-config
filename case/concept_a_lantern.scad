// ══════════════════════════════════════════════════════════════
//  CONCEPT A — "Lantern"
//  Upright cylinder with frosted dome.
//  Ring glows through dome; display faces up at the apex.
//  Speaker fires down through a honeycomb base.
// ══════════════════════════════════════════════════════════════

$fn = 120;

od       = 80;   // body diameter
body_h   = 70;   // opaque lower body
dome_h   = 45;   // translucent dome height
wall     = 2;

ring_od  = 51;
ring_h   = 3;

dsp_od   = 33;   // visible display window at apex

// ── Opaque base/body ──────────────────────────────────────────
color("dimgray")
difference() {
    cylinder(h = body_h, d = od);
    translate([0, 0, wall]) cylinder(h = body_h, d = od - 2*wall);
    // USB-C rear exit
    translate([0, od/2 - wall/2, 15])
        rotate([90,0,0]) cylinder(h = wall*3, d = 10, center=true);
    // Honeycomb-ish base pattern (suggested as 50mm disk)
    for (a = [0:60:359], r = [6,14,22])
        translate([r*cos(a), r*sin(a), -0.1])
            cylinder(h = wall + 0.2, d = 4, $fn=6);
}

// ── LED ring (indicative) ─────────────────────────────────────
color("royalblue", 0.9)
translate([0, 0, body_h + 2])
    difference() {
        cylinder(h = ring_h, d = ring_od);
        translate([0,0,-0.1]) cylinder(h = ring_h+0.2, d = 34);
    }

// ── Frosted dome ──────────────────────────────────────────────
color("white", 0.35)
translate([0, 0, body_h + ring_h + 1])
    difference() {
        union() {
            // short cylindrical skirt so dome clears the ring
            cylinder(h = 6, d = od);
            translate([0, 0, 6]) scale([1,1,dome_h/(od/2)])
                sphere(d = od);
        }
        // hollow
        translate([0,0,-0.1]) cylinder(h = 6.1, d = od - 2*wall);
        translate([0, 0, 6]) scale([1,1,(dome_h-wall)/(od/2)])
            sphere(d = od - 2*wall);
        // display window at apex
        translate([0, 0, 6 + dome_h - 5])
            cylinder(h = 20, d = dsp_od);
    }

// ── Display (indicative disc at apex) ────────────────────────
color("black")
translate([0, 0, body_h + ring_h + 6 + dome_h - 4])
    cylinder(h = 1.6, d = dsp_od + 4);
