// ══════════════════════════════════════════════════════════
//  ESP32-S3 Voice Satellite — "Orbital" Tilted Puck
//  Body wall stops at lower tilted plane; face plate
//  continues the cylinder wall flush to the top.
// ══════════════════════════════════════════════════════════

/* [Global] */
part = "body"; // [assembly, body, face]
wall = 2;          // [2:0.5:5]
od   = 90;
tilt = 15;         // [0:1:25]

/* [Speaker] */
spk_dia       = 40;
spk_depth     = 18;
spk_collar_h  = 5;     // height of the press-fit collar above the base
spk_tol       = 0.2;   // press-fit radial tolerance (reduce to tighten)

/* [Display] */
dsp_window   = 34;
dsp_pcb_dia  = 36;
dsp_pcb_seat = 1.5;
dsp_conn_w   = 24;    // connector notch width (6-pin 2.54mm header ≈ 15.24mm)
dsp_conn_ext = 12;     // how far the connector protrudes past the PCB edge

/* [LED Ring] */
ring_od        = 50;
ring_id        = 38;
ring_seat      = 1.5;
ring_mount_pcd = 47;
ring_mount_d   = 2.2;

/* [Face Plate] */
face_h = 7;
face_clearance = 0.2;   // radial gap between face edge and body wall

/* [Body internals] */
grille_dia     = 41;
hex_cell       = 2;
spk_shelf_z    = 18;
esp_shelf_z    = 22;
esp_shelf_hole = 50;

/* [Mounting] */
mount_pcd    = 78;
mount_d      = 3.2;
mount_head   = 5.8;
mount_count  = 3;
insert_d     = 4.2;
insert_depth = 5;

/* [Cable & Mic] */
cable_w = 14;      // cable hole width  (USB-C wide axis)
cable_h = 8;       // cable hole height (USB-C flat axis)
cable_z = 24;      // center height from base — between spk shelf (z≈21) and esp shelf (z≈27)
mic_d   = 2.5;

// ── Derived ──────────────────────────────────────────────
r    = od / 2;
ir   = r - wall;
$fn  = 120;
eps  = 0.01;
big  = od * 2;

// Body height: lower tilted plane must clear ESP shelf at
// the front edge (lowest point).
//   lower_plane_front_z = body_h - face_h·cos(t) - r·sin(t)
//   must be  > wall + esp_shelf_z + 3   (top of ESP shelf)
body_h = wall + esp_shelf_z + 3
       + face_h * cos(tilt) + r * sin(tilt)
       + 12;  // margin (+10mm height)

body_rear_h  = body_h + r * sin(tilt);
body_front_h = body_h - r * sin(tilt);

echo(str("Body center: ", body_h, " mm"));
echo(str("Rear wall:   ", body_rear_h, " mm"));
echo(str("Front wall:  ", body_front_h, " mm"));

// ══════════════════════════════════════════════════════════
//  PART SELECTOR
// ══════════════════════════════════════════════════════════

if (part == "assembly") {
    color("dimgray")    body();
    color("white")      translate([0, 0, body_h])
                            rotate([tilt, 0, 0])
                                translate([0, 0, -face_h])
                                    face();
}
if (part == "body")     body();
if (part == "face")     face();

// ══════════════════════════════════════════════════════════
//  BODY
//  Cylinder whose wall stops at the lower tilted plane.
//  The face plate continues the wall from there to the top.
// ══════════════════════════════════════════════════════════
module body() {
    difference() {
        union() {
            // ── Outer shell (hollow) ─────────────────
            difference() {
                cylinder(h = body_rear_h + 1, r = r);
                translate([0, 0, wall])
                    cylinder(h = body_rear_h + 2, r = ir);
            }

            // ── Speaker press-fit collar (bottom) ────
            translate([0, 0, wall])
                difference() {
                    cylinder(h = spk_collar_h, r = ir);
                    translate([0, 0, -eps])
                        cylinder(h = spk_collar_h + 2 * eps, d = spk_dia + 1 * spk_tol);
                }

            // ── M3 mount bosses (uniform radius in world XY) ─
            for (i = [0 : mount_count - 1]) {
                a  = i * 360 / mount_count + 270;
                bR = ir - (insert_d + 2) / 2 + 0.1;
                translate([bR * cos(a), bR * sin(a), wall])
                    cylinder(h = body_rear_h, d = insert_d + 2);
            }
        }

        // ── Cut above lower tilted plane ─────────────
        // Everything above this plane is replaced by the face plate.
        translate([0, 0, body_h])
            rotate([tilt, 0, 0])
                translate([0, 0, -face_h + big])
                    cube([big * 2, big * 2, big * 2], center = true);

        // ── Base grille ──────────────────────────────
        translate([0, 0, -eps])
            honeycomb_grid(grille_dia / 2,
                           wall + 2 * eps, hex_cell, hex_cell * 0.3);

        // ── M3 heat-set insert holes (on lower plane) ─
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

        // ── Cable exit hole (rear, y+) ───────────────
        translate([0, r, cable_z])
            rotate([90, 0, 0])
                hull() {
                    translate([ (cable_w - cable_h) / 2, 0, 0])
                        cylinder(h = wall * 4, d = cable_h, center = true);
                    translate([-(cable_w - cable_h) / 2, 0, 0])
                        cylinder(h = wall * 4, d = cable_h, center = true);
                }

    }
}

// ══════════════════════════════════════════════════════════
//  FACE PLATE
//  Modeled flat (z=0 is back / mating face, z=face_h is
//  the visible front).  Outer profile is the intersection
//  of this slab with the body cylinder, so the wall
//  continues flush from the body.
// ══════════════════════════════════════════════════════════
module face() {
    difference() {
        // ── Flush outer profile ──────────────────────
        intersection() {
            cylinder(h = face_h, r = od);
            body_cyl_in_face_frame(r - face_clearance);
        }

        // ── Central recess: full circle leaving 0.8mm skin ─
        // covers LCD + LED ring area in one shot, no wall between them
        translate([0, 0, -eps])
            cylinder(h = face_h - 0.8 + eps, d = ring_od + 2);

        // ── Display window: cuts through the 0.8mm skin ─
        translate([0, 0, -1])
            cylinder(h = face_h + 2, d = dsp_window);

        // ── Mic port (12 o'clock) ────────────────────
        mic_y = (ring_od / 2 + r) / 2;
        translate([0, mic_y, -1])
            cylinder(h = face_h + 2, d = mic_d);

        // ── M3 countersunk holes ─────────────────────
        for (i = [0 : mount_count - 1]) {
            a   = i * 360 / mount_count + 270;
            bR  = ir - (insert_d + 2) / 2 + 0.1;
            wx  = bR * cos(a);
            wy  = bR * sin(a);
            fpy = (wy - face_h * sin(tilt)) / cos(tilt);
            translate([wx, fpy, -1]) {
                cylinder(h = face_h + 2, d = mount_d);
                translate([0, 0, face_h + 1 - 2])
                    cylinder(h = 2.5, d1 = mount_d, d2 = mount_head);
            }
        }

        // ── LCD connector notch (6 o'clock) ──────────
        // Rectangular slot from PCB edge outward, full depth to diffuser.
        translate([-dsp_conn_w / 2, -(dsp_pcb_dia / 2 + dsp_conn_ext), -eps])
            cube([dsp_conn_w, dsp_conn_ext, face_h - 0.8 + 2 * eps]);
    }
}

// ══════════════════════════════════════════════════════════
//  HELPERS
// ══════════════════════════════════════════════════════════

// Vertical body cylinder expressed in the face plate's
// tilted coordinate frame.
// Face frame: Tz(body_h)·Rx(tilt)·Tz(-face_h)·P
// Inverse  : Tz(face_h)·Rx(-tilt)·Tz(-body_h)·P_world
module body_cyl_in_face_frame(radius) {
    translate([0, 0, face_h])
        rotate([-tilt, 0, 0])
            translate([0, 0, -body_h - 100])
                cylinder(h = 300, r = radius);
}

// Honeycomb grille
module honeycomb_grid(radius, h, cell, wall_t) {
    spacing = cell + wall_t;
    rows = ceil(radius * 2 / (spacing * 0.866));
    cols = ceil(radius * 2 / spacing);
    intersection() {
        cylinder(h = h, r = radius);
        translate([0, 0, -eps])
            for (row = [-rows:rows])
                for (col = [-cols:cols]) {
                    x = col * spacing + (row % 2) * spacing / 2;
                    y = row * spacing * 0.866;
                    if (sqrt(x * x + y * y) < radius - cell / 2)
                        translate([x, y, 0])
                            cylinder(h = h + 2 * eps, d = cell, $fn = 6);
                }
    }
}
