// ══════════════════════════════════════════════════════════════
//  HUB CASE v5 — Voice Assistant
//
//  Changes vs v4:
//   1. LED DIFFUSER FIXED FROM INSIDE — the shell now keeps a real front
//      wall with a rounded 86 × 15 mm window (LEDs 30 mm apart → 13 mm of
//      glow margin past each outer LED). The diffuser is a backing plate +
//      flush tongue, screwed FROM INSIDE (2 × M2.5 into heat-set inserts
//      in wall bosses above the window). No glue, nothing visible outside.
//   2. BOTTOM PLATE FIXATION — 3 extra pillars: left-middle, right-middle
//      and front-centre (7 screws total). Nothing added at the rear —
//      the speaker basket owns that wall. The front-centre pillar is
//      pushed back from the wall (y = −39) so it clears the diffuser
//      plate + LED strip; its skirt passes UNDER the diffuser (z < 7.5).
//   3. LCD PROPERLY FIXED — the v4 blind insert pockets (2.5 mm deep in a
//      3.5 mm wall — could not hold a heat-set insert) are gone. New
//      system: 4 bosses hang 8 mm from the inner top face just beyond the
//      PCB's short edges (local Y ±35.5), M3 heat-set inserts in the boss
//      ends, and a printed CLAMP FRAME (new part "lcd_clamp") with press
//      pads squeezes the PCB flat against the inner top face.
//      Glass still protrudes through the viewport, flush with the outside.
//
//  FOUR PARTS:
//    shell      : organic rounded wedge, open bottom — PRINT IN BLACK
//    plate      : flat bottom slab, 7 × M2.5 countersunk from below — BLACK
//    front_plate: LED diffuser (plate + flush tongue) — WHITE/TRANSLUCENT
//                 print with the flat back face on the bed (tongue up)
//    lcd_clamp  : LCD retention frame — BLACK, print as modeled (pads up)
//
//  HARDWARE:
//    7 × M2.5 heat-set insert (Ø3.8) — bottom-plate pillars
//    2 × M2.5 heat-set insert (Ø3.8) — diffuser wall bosses
//    4 × M3   heat-set insert (Ø4.0) — LCD clamp bosses
//    7 × M2.5 countersunk screw      — bottom plate
//    2 × M2.5 × 6 pan-head           — diffuser (driven from inside,
//                                      stubby driver through open bottom)
//    4 × M3 × 8 pan-head             — LCD clamp (straight shot from bottom)
//    4 × M3                          — speaker (rear, unchanged)
//
//  ASSEMBLY ORDER (shell upside down, bottom open):
//    1. LCD PCB into viewport (glass out) → lcd_clamp on → 4 × M3
//    2. Mic into pocket (glue), LED strip stuck to diffuser plate back
//    3. Diffuser tongue into window → 2 × M2.5 from inside
//    4. Speaker on rear bosses, RPi stack, wiring
//    5. Bottom plate → 7 × M2.5 countersunk
//
//  part = "assembly" | "shell" | "plate" | "front_plate" | "lcd_clamp"
// ══════════════════════════════════════════════════════════════

$fn  = 60;
eps  = 0.01;

/* [Part] */
part = "assembly";

/* [Outer envelope] */
case_w  = 120;   // width (X)
case_d  = 106;   // depth (Y)
front_h =  45;   // body height at front face (Y-)
rear_h  =  77;   // body height at rear face  (Y+)
rs      =   7;   // sphere radius — rounds ALL edges and corners
wall    =   2;   // side / rear wall thickness
front_t =   1.5; // front wall thickness (diffuser tongue sits flush in it)
top_t   =   3.5; // sloped top wall thickness = glass height → LCD flush outside

// Slope of the organic top face — tangent between front/rear-top sphere centres.
tilt = atan2(rear_h - front_h, case_d - 2*rs);   // ≈ 19.2°
function top_z(y) =
    let(dZ = rear_h - front_h, dY = case_d - 2*rs)
    (dZ*y + dY*(front_h - rs) + dZ*(case_d/2 - rs) + rs*sqrt(dZ*dZ + dY*dY)) / dY;

/* [RPi 4] */
rpi_w=85; rpi_d=56; rpi_t=1.6; rpi_z=6;
rpi_usb_edge = +1;
rpi_x = -rpi_w/2;
rpi_y = case_d/2 - wall - 5 - rpi_d;

/* [HAT] */
gpio_h=8; hat_gap=3; hat_pcb_t=1.6; hat_comp_h=14;
hat_z = rpi_z + rpi_t + gpio_h + hat_gap;

/* [Display — ST7796S 4.0" 480×320, PCB 108 × 62 mm] */
// PCB pressed against the inner top face from inside; LCD glass (3.5 mm)
// protrudes through the viewport → flush with the outer surface.
// The PCB's own Ø3 mounting holes are NOT used — retention is the clamp frame.
dsp_open_w =  95;   // viewport opening width  (X)
dsp_open_h =  61;   // viewport opening height (local Y, along sloped surface)
dsp_y      = -10;   // world-Y of display centre (negative = toward front)
dsp_pcb_t  = 1.6;

/* [Display clamp — bosses hang from inner top face, frame presses PCB] */
// Bosses sit just beyond the PCB's ±31 mm (local Y) edges, clear of the
// Ø17 mic pocket (mic is at X=0, bosses at X=±44).
cl_boss_x   = 44;    // boss centre ±X (display-local)
cl_boss_y   = 35.5;  // boss centre ±Y — edge at 31.75 → 0.75 mm off the PCB
cl_boss_od  = 7.5;
cl_boss_h   = 8;     // hang below inner face — room for a full M3 insert
cl_boss_emb = 1;     // embedded into the top wall (2.5 mm skin remains)
cl_insert_d = 4.0;   // M3 heat-set
cl_insert_dep = 6;
cl_bar_w    = 8;     // frame bar width
cl_bar_t    = 3;     // frame bar thickness
cl_screw_d  = 3.4;   // M3 clearance
// Press pads: land on the PCB back ~10 mm inboard of its short edges.
// >>> Verify against your module's rear components (SD socket, pin header)
//     and move cl_pad_x / cl_pad_y if needed. <<<
cl_pad_x    = 44;
cl_pad_y    = 26;
cl_pad_d    = 6;
cl_pad_squeeze = 0.2;   // pad overtravel → preload when screws tighten

/* [Mic — INMP441 round 15 mm PCB] */
mic_pocket_d     = 17;
mic_pocket_depth =  2;
mic_hole_d       =  2.5;
mic_y = dsp_y + dsp_open_h/2 + 13;   // ≈ +33.5 mm world-Y

/* [Speaker — 54 mm Ø basket, 42 mm hole spacing] */
spk_z       = 30;
spk_ear_off = 21;
spk_ear_d   =  2.7;

/* [Speaker boss] */
boss_od  = 8;
boss_len = 4;
spk_m3_d = 3.2;

/* [Front LED diffuser — window + tongue + 2 inside screws] */
// Window raised vs v4 (band centre z = 18.5) so the front-centre pillar's
// skirt passes underneath the diffuser plate. LED strip sticks to the
// BACK of the diffuser plate, centred on the window.
// The 3 LEDs are 30 mm apart (outer LEDs at x = ±30) → 86 mm window gives
// 13 mm of glow margin past each outer LED. The two wall bosses sit ABOVE
// the window (no room to flank it); screws still drive from inside.
fp_led_z    = 18.5;  // window / LED band centre height
fp_win_w    = 86;    // window width  (LEDs at x = −30/0/+30)
fp_win_h    = 15;    // window height
fp_win_r    = 2;     // window corner radius
fp_plate_w  = 92;    // backing plate width (1.5 mm clear of corner pillars)
fp_plate_z0 = 8;     // backing plate bottom (front-centre pillar skirt < 7.5)
fp_plate_z1 = 35;    // backing plate top (covers the bosses above the window)
fp_plate_t  = 2;
fp_boss_x   = 25;    // wall boss ±X, above the window
fp_boss_z   = 30.5;  // wall boss centre height (window top 26 → 1.25 mm ring)
fp_boss_od  = 6.5;
fp_boss_len = 4;     // plate stands off the wall on the boss tips
fp_insert_d = 3.8;   // M2.5 heat-set
fp_insert_dep = 5;   // 4 in boss + 1 into wall (0.5 mm outer skin remains)
fp_screw_d  = 2.8;
fp_clear    = 0.3;   // tongue-to-window clearance per side

/* [Bottom-plate mounting pillars] */
pillar_od    =  7;
pillar_h     = 12;
insert_d     =  3.8;
insert_depth =  5;
mount_d      =  2.7;
mount_head_d =  5.5;
mount_head_h =  2.5;

/* [Plate / split-line] */
split_z = 3;
plate_t = split_z;

pillar_inset = 5;
corner_pts = [
    [-(case_w/2 - wall - pillar_inset), -(case_d/2 - front_t - pillar_inset)],
    [ (case_w/2 - wall - pillar_inset), -(case_d/2 - front_t - pillar_inset)],
    [-(case_w/2 - wall - pillar_inset),  (case_d/2 - wall    - pillar_inset)],
    [ (case_w/2 - wall - pillar_inset),  (case_d/2 - wall    - pillar_inset)],
];
// v5: middle pillars — sides + front centre. NONE at the rear (speaker).
mid_side_pts = [
    [-(case_w/2 - wall - pillar_inset), 0],
    [ (case_w/2 - wall - pillar_inset), 0],
];
// Front-centre pillar pushed back so pillar (Ø7 → edge −42.5) clears the
// diffuser plate back (−45.5) and the LED strip on it (≈ −44).
mid_front_pt = [0, -39];
screw_pts    = concat(corner_pts, mid_side_pts, [mid_front_pt]);
// Front-centre skirt must stay below the diffuser plate bottom (z = 8).
fm_skirt_h = fp_plate_z0 - split_z - 0.5;   // = 4.5

// ── Helpers ──────────────────────────────────────────────────

module rr2d(w, h, r) {
    hull() for (a=[-1,1], b=[-1,1])
        translate([a*(w/2-r), b*(h/2-r)]) circle(r);
}

// Rounded-rect prism, centred in X/Z, extruded along +Y from y=0.
module rrect_y(w, h, r, len) {
    rotate([-90, 0, 0]) linear_extrude(len) rr2d(w, h, r);
}

// ── Modules ──────────────────────────────────────────────────

module outer_body() {
    hull() {
        for (sx=[-1,1], sy=[-1,1])
            translate([sx*(case_w/2-rs), sy*(case_d/2-rs), rs])
                sphere(r=rs);
        for (sx=[-1,1])
            translate([sx*(case_w/2-rs), -(case_d/2-rs), front_h-rs])
                sphere(r=rs);
        for (sx=[-1,1])
            translate([sx*(case_w/2-rs), +(case_d/2-rs), rear_h-rs])
                sphere(r=rs);
    }
}

module inner_hollow() {
    iw  = case_w - 2*wall;
    icr = max(2, rs - wall);
    ify = -(case_d/2 - front_t - icr);
    iry =   case_d/2 - wall   - icr;
    iz_b  = icr - 1;
    iz_ft = front_h - top_t - icr;
    iz_rt = rear_h  - top_t - icr;

    hull()
        for (sx=[-1,1]) {
            translate([sx*(iw/2-icr), ify, iz_b])  sphere(r=icr);
            translate([sx*(iw/2-icr), iry, iz_b])  sphere(r=icr);
            translate([sx*(iw/2-icr), ify, iz_ft]) sphere(r=icr);
            translate([sx*(iw/2-icr), iry, iz_rt]) sphere(r=icr);
        }
}

// Rectangular LCD viewport ⊥ to sloped top.
// Local z=0 = outer surface, z=−top_t = inner face.
module display_cut(dy) {
    translate([0, dy, top_z(dy)])
    rotate([tilt, 0, 0])
        translate([-dsp_open_w/2, -dsp_open_h/2, -top_t - eps])
            cube([dsp_open_w, dsp_open_h, top_t * 4 + 2*eps]);
}

// LCD clamp bosses — hang from the inner top face, embedded 1 mm into the
// wall (outside the viewport, so the outer surface stays untouched).
module display_clamp_bosses(dy) {
    translate([0, dy, top_z(dy)])
    rotate([tilt, 0, 0])
    for (mx=[-1,1], my=[-1,1])
        translate([mx*cl_boss_x, my*cl_boss_y, -top_t - cl_boss_h])
            cylinder(h = cl_boss_h + cl_boss_emb, d = cl_boss_od);
}

// M3 insert pockets drilled up into the boss ends (never touch the wall).
module display_clamp_insert_holes(dy) {
    translate([0, dy, top_z(dy)])
    rotate([tilt, 0, 0])
    for (mx=[-1,1], my=[-1,1])
        translate([mx*cl_boss_x, my*cl_boss_y, -top_t - cl_boss_h - eps])
            cylinder(h = cl_insert_dep, d = cl_insert_d);
}

// Mic pocket from inner face, sound port through skin.
module mic_cut(my) {
    translate([0, my, top_z(my)])
    rotate([tilt, 0, 0]) {
        translate([0, 0, -top_t])
            cylinder(h = mic_pocket_depth + eps, d = mic_pocket_d);
        cylinder(h = 60, d = mic_hole_d, center = true);
    }
}

// Dense circular hex honeycomb.
module hex_circle(radius, depth, cell, wall_t) {
    sp = cell + wall_t;
    n  = ceil(radius / sp) + 1;
    intersection() {
        cylinder(h = depth + 2*eps, r = radius, center = true);
        for (row = [-n:n], col = [-n:n]) {
            x = col*sp + (row%2)*sp/2;
            y = row * sp * 0.866;
            translate([x, y, 0])
                cylinder(h = depth + 2*eps, d = cell, $fn=6, center = true);
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  SHELL
// ══════════════════════════════════════════════════════════════
module shell() {
    difference() {
        union() {
            difference() {
                outer_body();
                inner_hollow();
                // Remove plate slice (z < split_z belongs to the plate).
                translate([-case_w, -case_d, -50])
                    cube([case_w*2, case_d*2, 50 + split_z]);
            }

            // ── Mounting pillars with ribs and base skirts
            skirt_h    = 5;
            rib_thick  = 2;
            rib_width  = 7;
            intersection() {
                outer_body();
                union() {
                    // Corner pillars — two ribs + corner skirt (as v4)
                    for (pt = corner_pts) {
                        sx = sign(pt[0]);
                        sy = sign(pt[1]);
                        owall_x = sx * (case_w/2 + 5);
                        owall_y = sy * (case_d/2 + 5);
                        translate([pt[0], pt[1], split_z])
                            cylinder(h = pillar_h, d = pillar_od);
                        hull() {
                            translate([pt[0], pt[1], split_z])
                                cylinder(h = pillar_h, d = pillar_od);
                            translate([owall_x - sx*rib_thick/2, pt[1]-rib_width/2, split_z])
                                cube([rib_thick, rib_width, pillar_h]);
                        }
                        hull() {
                            translate([pt[0], pt[1], split_z])
                                cylinder(h = pillar_h, d = pillar_od);
                            translate([pt[0]-rib_width/2, owall_y - sy*rib_thick/2, split_z])
                                cube([rib_width, rib_thick, pillar_h]);
                        }
                        hull() {
                            translate([pt[0], pt[1], split_z])
                                cylinder(h = skirt_h, d = pillar_od);
                            translate([owall_x - sx*0.5, pt[1]-rib_width/2, split_z])
                                cube([1, rib_width, skirt_h]);
                            translate([pt[0]-rib_width/2, owall_y - sy*0.5, split_z])
                                cube([rib_width, 1, skirt_h]);
                            translate([owall_x - sx*0.5, owall_y - sy*0.5, split_z])
                                cube([1, 1, skirt_h]);
                        }
                    }

                    // v5: side-middle pillars — rib + skirt to side wall only
                    for (pt = mid_side_pts) {
                        sx = sign(pt[0]);
                        owall_x = sx * (case_w/2 + 5);
                        translate([pt[0], pt[1], split_z])
                            cylinder(h = pillar_h, d = pillar_od);
                        hull() {
                            translate([pt[0], pt[1], split_z])
                                cylinder(h = pillar_h, d = pillar_od);
                            translate([owall_x - sx*rib_thick/2, pt[1]-rib_width/2, split_z])
                                cube([rib_thick, rib_width, pillar_h]);
                        }
                        hull() {
                            translate([pt[0], pt[1], split_z])
                                cylinder(h = skirt_h, d = pillar_od);
                            translate([owall_x - sx*0.5, pt[1]-rib_width/2, split_z])
                                cube([1, rib_width, skirt_h]);
                        }
                    }

                    // v5: front-centre pillar — LOW skirt to the front wall,
                    // passing under the diffuser plate (skirt top 7.5 < plate 8).
                    translate([mid_front_pt[0], mid_front_pt[1], split_z])
                        cylinder(h = pillar_h, d = pillar_od);
                    hull() {
                        translate([mid_front_pt[0], mid_front_pt[1], split_z])
                            cylinder(h = fm_skirt_h, d = pillar_od);
                        translate([-rib_width/2, -(case_d/2 + 5), split_z])
                            cube([rib_width, 1, fm_skirt_h]);
                    }
                }
            }

            // ── Speaker bosses on inner rear wall
            for (sx=[-1,1], sz=[-1,1])
                translate([sx*spk_ear_off, case_d/2 - wall, spk_z + sz*spk_ear_off])
                    rotate([90, 0, 0])
                        cylinder(h = boss_len, d = boss_od);

            // ── v5: LCD clamp bosses hanging from inner top face
            display_clamp_bosses(dsp_y);

            // ── v5: diffuser bosses on inner front wall, above the window
            for (s=[-1,1])
                translate([s*fp_boss_x, -(case_d/2 - front_t) - 1, fp_boss_z])
                    rotate([-90, 0, 0])
                        cylinder(h = fp_boss_len + 1, d = fp_boss_od);
        }

        // ── LCD viewport (clean rectangular cut, no external holes)
        display_cut(dsp_y);
        // ── v5: M3 insert pockets in the clamp boss ends
        display_clamp_insert_holes(dsp_y);
        // ── Mic pocket + sound port
        mic_cut(mic_y);

        // ── Rear honeycomb (r=20 mm, cell 2.5 mm, wall 0.65 mm)
        translate([0, case_d/2 - wall/2, spk_z])
            rotate([90, 0, 0])
                hex_circle(20, wall + 4, 2.5, 0.65);

        // ── Speaker boss M3 holes
        for (sx=[-1,1], sz=[-1,1])
            translate([sx*spk_ear_off, case_d/2 + eps, spk_z + sz*spk_ear_off])
                rotate([90, 0, 0])
                    cylinder(h = wall + boss_len + 2*eps, d = spk_m3_d);

        // ── USB-C slot on rear wall (unchanged)
        usb_x = +36;
        usb_z = 15;
        translate([usb_x, case_d/2 - wall/2, usb_z])
            rotate([90, 0, 0])
                hull()
                    for (dx=[-1,1])
                        translate([dx*2.5, 0, 0])
                            cylinder(h = wall*2+4, d = 9, center = true);

        // ── Left side airflow vents
        for (zv = [hat_z+3, hat_z+11, hat_z+19])
            translate([-case_w/2, 15, zv])
                rotate([0, 90, 0])
                    hull() {
                        translate([0,  7, 0]) cylinder(h=wall+2, d=2.5, center=true);
                        translate([0, -7, 0]) cylinder(h=wall+2, d=2.5, center=true);
                    }

        // ── Insert holes in all 7 bottom-plate pillars
        for (pt = screw_pts)
            translate([pt[0], pt[1], split_z - eps])
                cylinder(h = insert_depth, d = insert_d);

        // ── v5: diffuser window through the front wall (rounded rect)
        translate([0, -case_d/2 - 1, fp_led_z])
            rrect_y(fp_win_w, fp_win_h, fp_win_r, front_t + 2);

        // ── v5: M2.5 insert pockets in the diffuser boss tips
        for (s=[-1,1])
            translate([s*fp_boss_x, -(case_d/2 - front_t) + fp_boss_len + eps, fp_boss_z])
                rotate([90, 0, 0])
                    cylinder(h = fp_insert_dep, d = fp_insert_d);
    }
}

// ══════════════════════════════════════════════════════════════
//  BOTTOM PLATE — 7 countersunk M2.5 from below
// ══════════════════════════════════════════════════════════════
module plate() {
    difference() {
        intersection() {
            outer_body();
            translate([-case_w, -case_d, 0])
                cube([case_w*2, case_d*2, split_z]);
        }
        for (pt = screw_pts) {
            translate([pt[0], pt[1], -eps])
                cylinder(h = split_z + 2*eps, d = mount_d);
            translate([pt[0], pt[1], -eps])
                cylinder(h = mount_head_h, d2=mount_d, d1=mount_head_d);
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  FRONT LED DIFFUSER — plate + flush tongue, fixed from inside
// ══════════════════════════════════════════════════════════════
//  The backing plate stands off the inner wall face on the two boss tips;
//  the tongue passes through the window and sits flush with the outer
//  surface. 2 × M2.5 pan-head from inside pull it tight.
//  LED strip sticks to the BACK of the plate, centred on the window.
//  PRINT IN WHITE/TRANSLUCENT — flat back face on the bed, tongue up.
module front_plate() {
    wall_in = -(case_d/2 - front_t);        // inner face of front wall
    py      = wall_in + fp_boss_len;        // plate front face (on boss tips)
    difference() {
        union() {
            // Backing plate
            translate([0, py, (fp_plate_z0 + fp_plate_z1)/2])
                rrect_y(fp_plate_w, fp_plate_z1 - fp_plate_z0, 2, fp_plate_t);
            // Flush tongue — fills the window, front face at the outer surface
            translate([0, -case_d/2, fp_led_z])
                rrect_y(fp_win_w - 2*fp_clear, fp_win_h - 2*fp_clear,
                        fp_win_r - fp_clear, front_t + fp_boss_len + eps);
        }
        // M2.5 through-holes
        for (s=[-1,1])
            translate([s*fp_boss_x, py - eps, fp_boss_z])
                rotate([-90, 0, 0])
                    cylinder(h = fp_plate_t + 2*eps, d = fp_screw_d);
    }
}

// ══════════════════════════════════════════════════════════════
//  LCD CLAMP — ring frame with press pads, screws into the 4 bosses
// ══════════════════════════════════════════════════════════════
//  Modeled flat for printing (pads up). In the case it sits under the
//  bosses; tightening the 4 × M3 presses the pads onto the PCB back and
//  squeezes it flat against the inner top face.
module lcd_clamp() {
    pad_h = cl_boss_h - dsp_pcb_t + cl_pad_squeeze;   // 6.6 — 0.2 preload
    difference() {
        union() {
            linear_extrude(cl_bar_t) difference() {
                rr2d(2*cl_boss_x + cl_bar_w, 2*cl_boss_y + cl_bar_w, 4);
                rr2d(2*cl_boss_x - cl_bar_w, 2*cl_boss_y - cl_bar_w, 2);
            }
            for (mx=[-1,1], my=[-1,1])
                translate([mx*cl_pad_x, my*cl_pad_y, cl_bar_t - eps])
                    cylinder(h = pad_h + eps, d = cl_pad_d);
        }
        for (mx=[-1,1], my=[-1,1])
            translate([mx*cl_boss_x, my*cl_boss_y, -eps])
                cylinder(h = cl_bar_t + 2*eps, d = cl_screw_d);
    }
}

// ══════════════════════════════════════════════════════════════
//  OUTPUT
// ══════════════════════════════════════════════════════════════
if (part == "assembly") {
    color("#1a1a1a")      shell();
    color("#1a1a1a", 0.7) plate();
    color("white",  0.85) front_plate();
    color("#555")
        translate([0, dsp_y, top_z(dsp_y)])
        rotate([tilt, 0, 0])
        translate([0, 0, -top_t - cl_boss_h - cl_bar_t])
            lcd_clamp();

    // RPi 4
    color("darkgreen")  translate([rpi_x,rpi_y,rpi_z]) cube([rpi_w,rpi_d,rpi_t]);
    color("#666")       for (dy=[8,24]) translate([rpi_x+rpi_w-18,rpi_y+dy,rpi_z+rpi_t]) cube([18,14,15]);
    color("black")      translate([rpi_x,rpi_y+rpi_d-10,rpi_z+rpi_t]) cube([51,5,gpio_h]);
    color("#3a7a3a")    translate([rpi_x,rpi_y,hat_z]) cube([rpi_w,rpi_d,hat_pcb_t]);
    color("#222")       translate([rpi_x+10,rpi_y+8,hat_z+hat_pcb_t]) cube([30,20,hat_comp_h]);
    // Speaker
    color("#111")       translate([0,case_d/2-wall-2,spk_z]) rotate([90,0,0]) cylinder(h=3,d=48);
    // Front LEDs — 30 mm apart, on the diffuser plate back (y ≈ −44.5)
    color("royalblue",0.9)
        for(i=[-1,0,1])
            translate([i*30, -(case_d/2-front_t) + fp_boss_len + fp_plate_t + 1, fp_led_z])
                sphere(d=4.5);
    // LCD PCB against the inner top face
    color("darkgreen", 0.7)
        translate([0, dsp_y, top_z(dsp_y)])
        rotate([tilt, 0, 0])
        translate([-108/2, -62/2, -top_t - dsp_pcb_t])
            cube([108, 62, dsp_pcb_t]);
}

if (part == "shell")       shell();
if (part == "plate")       plate();
if (part == "front_plate") front_plate();
if (part == "lcd_clamp")   lcd_clamp();
