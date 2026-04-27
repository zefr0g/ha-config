// ══════════════════════════════════════════════════════════════
//  CONCEPT B — "Hub"
//  Low wedge base, Nest-Hub-Mini style.
//  Display face tilted up ~35° toward user, LED ring as halo.
//  Speaker fires out the back through a grille.
// ══════════════════════════════════════════════════════════════

$fn = 120;

base_w   = 130;
base_d   = 95;
base_h   = 62;
front_h  = 22;
tilt     = 35;

ring_od  = 51;
dsp_od   = 33;
face_od  = 72;

// ── Wedge body (rounded ends, flat bottom) ───────────────────
color("dimgray")
difference() {
    hull() {
        // front lip (rounded bar)
        translate([-base_w/2 + front_h/2, -base_d/2 + front_h/2, front_h/2])
            sphere(d = front_h);
        translate([ base_w/2 - front_h/2, -base_d/2 + front_h/2, front_h/2])
            sphere(d = front_h);
        // rear top (rounded bar, higher)
        translate([-base_w/2 + base_h/2,  base_d/2 - base_h/2, base_h/2])
            sphere(d = base_h);
        translate([ base_w/2 - base_h/2,  base_d/2 - base_h/2, base_h/2])
            sphere(d = base_h);
    }
    // Speaker grille — circle of holes on rear slope
    for (x = [-30:10:30], z = [22:10:52])
        translate([x, base_d/2 - 4, z])
            rotate([90,0,0])
                cylinder(h = 10, d = 4, center = true, $fn = 6);
}

// ── Tilted face plate ────────────────────────────────────────
// Sits on the sloping upper-front surface of the wedge.
face_cy = -base_d/2 + 32;
face_cz = front_h + 20;

translate([0, face_cy, face_cz])
rotate([90 - tilt, 0, 0]) {
    color("gainsboro")
    translate([0, 0, -2])
        cylinder(h = 2.2, d = face_od);
    color("royalblue", 0.95)
    translate([0, 0, 0.1])
    difference() {
        cylinder(h = 0.8, d = ring_od);
        translate([0,0,-0.1]) cylinder(h = 1.2, d = ring_od - 7);
    }
    color("black")
    translate([0, 0, 0.2])
        cylinder(h = 1.6, d = dsp_od);
}
