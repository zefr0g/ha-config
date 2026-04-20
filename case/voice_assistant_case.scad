// ══════════════════════════════════════════════════════════════
//  RPi 4 Voice Assistant — "Orbital" Tilted Puck
//  Adapted from ESP32-S3 satellite.scad (same form language).
//
//  Two pieces: body (print flat) + face plate (print top-down).
//  Join: 3× M2.5 heat-set inserts in body, M2.5 screws through face.
//
//  Body cross-section (Z from base):
//    └─ floor 0-3 mm  ─ honeycomb grille (speaker fires down)
//    └─ speaker zone 3-22 mm
//    └─ shelf/baffle 22-25 mm  (RPi standoffs + speaker ear screws)
//    └─ RPi + HAT  25-68 mm
//    └─ head room   -→  body_h
//    └─ tilted cut  →  face plate takes over
//
//  Face plate (z=0 = mating face, z=face_h = user-visible front):
//    └─ single recess  (ring_od+2) Ø, leaving 0.8 mm skin  [satellite approach]
//    └─ viewing window  33 mm Ø, cuts through skin
//    └─ connector notch at 6-o'clock
//    └─ INMP441 pocket + sound hole at 12-o'clock
// ══════════════════════════════════════════════════════════════

/* [Global] */
part = "assembly"; // [assembly, body, face]
wall = 2;
od   = 115;  // RPi corners sit at r=50.9 mm; ir=54.5 gives 3.6 mm clearance
tilt = 20;

/* [Speaker — 53 mm square + ears, fires down] */
spk_w        = 53;
spk_depth    = 16;    // basket depth (floor → top of frame)
// !! Measure centre-to-hole distance on your speaker and update spk_ear_off !!
spk_ear_off  = 21;   // 42 mm hole-to-hole spacing → ±21 mm from centre
spk_ear_hole = 2.7;  // M2.5 clearance

/* [Display — GC9A01 1.28"] */
dsp_window   = 33;   // viewing bore (< ring_id, leaves retaining rim)
dsp_pcb_dia  = 39;
dsp_pcb_t    = 1.6;
dsp_conn_w   = 23;   // connector width at 6-o'clock (pin header span)
dsp_conn_ext = 10;   // how far notch extends past PCB edge (adjust to cable clearance)

/* [LED Ring] */
ring_od   = 51;
ring_id   = 34;
ring_seat = 3;       // ring PCB thickness

/* [Face Plate] */
face_h         = 5;
face_clearance = 0.25;

/* [Body internals] */
rpi_body_h = 17;   // tallest RPi component (USB-A socket)
hat_h      = 15;
head_room  = 5;

/* [Grille] */
grille_dia = 50;
hex_cell   = 2;

/* [Mounting — M2.5 heat-set inserts] */
mount_pcd    = 88;  // informational; bosses sit at ir − boss_clearance
mount_d      = 2.7; // M2.5 screw clearance hole
mount_head   = 5.0; // M2.5 pan-head diameter
mount_count  = 3;
insert_d     = 3.8; // M2.5 heat-set insert OD
insert_depth = 5;

/* [Cable] */
cable_w = 15;  // USB-C wide axis
cable_h =  9;  // USB-C narrow axis

/* [INMP441 mic pocket — 12-o'clock, in face plate back face] */
mic_pcb_w     = 21;   // pocket width  (X)
mic_pcb_l     = 19;   // pocket length (Y, radially)
mic_pcb_depth =  4;   // pocket depth into face plate (leaves room for hot glue)
mic_hole_d    =  2.5; // sound-port bore through to front face
// Pocket centre radius from face centre (just outside ring OD/2 = 25.5 mm)
mic_r         = 37;

// ── Derived ──────────────────────────────────────────────────
r   = od / 2;
ir  = r - wall;
$fn = 120;
eps = 0.01;
big = od * 2;

// RPi 4: long axis (85 mm) along Y, USB-C/HDMI end at Y+ (rear).
// RPi centred at (0,0) in case XY.
rpi_w = 85;
rpi_d = 56;

// Mounting hole positions in case XY (from official RPi 4 datasheet):
//   x across 56 mm (GPIO edge = −28, USB-A edge = +28)
//   y along  85 mm (USB-C end = +42.5, SD-card end = −42.5)
//   Holes at x_board=3.5/52.5 and y_board=3.5/61.5 from USB-C corner.
rpi_holes = [
    [-rpi_d/2 + 3.5,  rpi_w/2 - 3.5 ],   // H1 (−24.5, +39.0)
    [ rpi_d/2 - 3.5,  rpi_w/2 - 3.5 ],   // H2 (+24.5, +39.0)
    [-rpi_d/2 + 3.5,  rpi_w/2 - 61.5],   // H3 (−24.5, −19.0)
    [ rpi_d/2 - 3.5,  rpi_w/2 - 61.5],   // H4 (+24.5, −19.0)
];

rpi_z   = wall + spk_depth + 5;  // approx RPi board height for cable slot
cable_z = rpi_z + 2;

// body_h: lowest point of the tilted cut must clear the HAT top.
// Same formula as satellite.scad.
body_h = rpi_z + rpi_body_h + hat_h + head_room
       + face_h * cos(tilt) + r * sin(tilt)
       + 5;                                // margin

body_rear_h  = body_h + r * sin(tilt);
body_front_h = body_h - r * sin(tilt);

echo(str("body_h (centre): ", body_h));
echo(str("body_rear_h:     ", body_rear_h));
echo(str("body_front_h:    ", body_front_h));

// ── Part selector ─────────────────────────────────────────────
if (part == "assembly") {
    color("dimgray") body();
    color("white")
        translate([0, 0, body_h])
            rotate([tilt, 0, 0])
                translate([0, 0, -face_h])
                    face();
}
if (part == "body") body();
if (part == "face") face();

// ══════════════════════════════════════════════════════════════
//  BODY
// ══════════════════════════════════════════════════════════════
module body() {
    difference() {
        union() {
            // Outer cylindrical shell, cut at tilted plane by the difference below
            difference() {
                cylinder(h = body_rear_h + 1, r = r);
                translate([0, 0, wall])
                    cylinder(h = body_rear_h + 2, r = ir);
            }

            // Speaker ear bosses — 2 mm tall tapped pads on floor interior
            // Speaker frame rests on these; M2.5 screws from above through ears.
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx*spk_ear_off, sy*spk_ear_off, wall])
                    difference() {
                        cylinder(d = 7, h = 2);
                        cylinder(d = 2.2, h = 3);  // M2.5 tap
                    }

            // Heat-set insert bosses along inner wall (same approach as satellite)
            for (i = [0 : mount_count - 1]) {
                a  = i * 360 / mount_count + 270;
                bR = ir - (insert_d + 2) / 2 + 0.1;
                translate([bR*cos(a), bR*sin(a), wall])
                    cylinder(h = body_rear_h, d = insert_d + 2);
            }
        }

        // ── Cut everything above the lower tilted plane (face takes over)
        translate([0, 0, body_h])
            rotate([tilt, 0, 0])
                translate([0, 0, -face_h + big])
                    cube([big*2, big*2, big*2], center = true);

        // ── Honeycomb grille in floor (under speaker cone)
        translate([0, 0, -eps])
            honeycomb_grid(grille_dia/2, wall + 2*eps, hex_cell, hex_cell*0.3);

        // ── Heat-set insert holes — drilled on the tilted face plane
        translate([0, 0, body_h])
            rotate([tilt, 0, 0])
                translate([0, 0, -face_h])
                    for (i = [0 : mount_count - 1]) {
                        a   = i * 360 / mount_count + 270;
                        bR  = ir - (insert_d + 2) / 2 + 0.1;
                        wx  = bR * cos(a);
                        wy  = bR * sin(a);
                        fpy = (wy - face_h * sin(tilt)) / cos(tilt);
                        translate([wx, fpy, -insert_depth])
                            cylinder(h = insert_depth + 1, d = insert_d);
                    }

        // ── USB-C exit — rear wall (Y+), at RPi board height
        translate([0, r, cable_z])
            rotate([90, 0, 0])
                hull() {
                    translate([ (cable_w - cable_h)/2, 0, 0])
                        cylinder(h = wall*4, d = cable_h, center = true);
                    translate([-(cable_w - cable_h)/2, 0, 0])
                        cylinder(h = wall*4, d = cable_h, center = true);
                }
    }
}

// ══════════════════════════════════════════════════════════════
//  FACE PLATE
//  z=0 = mating (back) face.  z=face_h = user-visible (front) face.
//  Print top-face-down (rotate 180° around X before slicing).
//  Same recess strategy as satellite.scad:
//    • one large bore (ring_od+2) leaves a 0.8 mm front skin
//    • display window cuts through the skin
//    • ring + display both float in the recess; hot-glue to fix
// ══════════════════════════════════════════════════════════════
module face() {
    difference() {
        // ── Flush outer profile (identical to satellite.scad)
        intersection() {
            cylinder(h = face_h, r = od);
            body_cyl_in_face_frame(r - face_clearance);
        }

        // ── Central recess: ring_od+2 bore, leaving 0.8 mm front skin
        translate([0, 0, -eps])
            cylinder(h = face_h - 0.8 + eps, d = ring_od + 2);

        // ── Display viewing window through the 0.8 mm skin
        translate([0, 0, -1])
            cylinder(h = face_h + 2, d = dsp_window);

        // ── LCD connector notch at 6-o'clock (Y−), same as satellite
        translate([-dsp_conn_w/2, -(dsp_pcb_dia/2 + dsp_conn_ext), -eps])
            cube([dsp_conn_w, dsp_conn_ext, face_h - 0.8 + 2*eps]);

        // ── INMP441 pocket at 12-o'clock (Y+), from back face
        // PCB slides in from the body side; hot-glue fills gap.
        // Sound-port bore goes through to front face.
        translate([-mic_pcb_w/2, mic_r - mic_pcb_l/2, -eps])
            cube([mic_pcb_w, mic_pcb_l, mic_pcb_depth + eps]);
        translate([0, mic_r, -1])
            cylinder(h = face_h + 2, d = mic_hole_d);

        // ── M2.5 through-holes + pan-head counterbore
        for (i = [0 : mount_count - 1]) {
            a   = i * 360 / mount_count + 270;
            bR  = ir - (insert_d + 2) / 2 + 0.1;
            wx  = bR * cos(a);
            wy  = bR * sin(a);
            fpy = (wy - face_h * sin(tilt)) / cos(tilt);
            translate([wx, fpy, -1]) {
                cylinder(h = face_h + 2, d = mount_d);
                translate([0, 0, face_h + 1 - 2.5])
                    cylinder(h = 3, d1 = mount_d, d2 = mount_head);
            }
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  HELPERS  (verbatim from satellite.scad)
// ══════════════════════════════════════════════════════════════

// Vertical body cylinder expressed in the face plate's tilted frame.
// Inverse transform: Tz(face_h)·Rx(−tilt)·Tz(−body_h).
module body_cyl_in_face_frame(radius) {
    translate([0, 0, face_h])
        rotate([-tilt, 0, 0])
            translate([0, 0, -body_h - 100])
                cylinder(h = 300, r = radius);
}

// Honeycomb grille — identical to satellite.scad
module honeycomb_grid(radius, h, cell, wall_t) {
    spacing = cell + wall_t;
    rows    = ceil(radius * 2 / (spacing * 0.866));
    cols    = ceil(radius * 2 / spacing);
    intersection() {
        cylinder(h = h, r = radius);
        translate([0, 0, -eps])
            for (row = [-rows : rows])
                for (col = [-cols : cols]) {
                    x = col * spacing + (row % 2) * spacing / 2;
                    y = row * spacing * 0.866;
                    if (sqrt(x*x + y*y) < radius - cell/2)
                        translate([x, y, 0])
                            cylinder(h = h + 2*eps, d = cell, $fn = 6);
                }
    }
}
