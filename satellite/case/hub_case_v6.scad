// ══════════════════════════════════════════════════════════════
//  HUB CASE v6 — Voice Assistant
//  (note: hub_v6/v7 PNGs in this dir are stale renders from the old
//   round-display era — unrelated to this file)
//
//  ARCHITECTURE CHANGE vs v5 — same outer silhouette, better split:
//  the case separates along a plane parallel to the sloped top face
//  (10 mm below it) instead of at the bottom.
//
//    ┌──────────── lid ────────────┐   sloped face + rounded top edges
//    │  viewport · clamp bosses ·  │   ← prints FACE-DOWN: perfect outer
//    │  mic pocket · hooks · bosses│     surface, all precision features
//    ╞══════════ seam ════════════╡     vertical, ZERO supports
//    │                             │
//    │   body (tub, closed floor)  │   ← prints bottom-down, ZERO supports
//    └─────────────────────────────┘
//
//  Why this is better than v5:
//   · v5's shell printed the sloped top as an interior ceiling (71°
//     overhang) — viewport, clamp bosses and mic pocket sat on dense
//     supports: weak bosses, rough faces. In v6 they print clean.
//   · Integrated floor: no bottom plate, no 7 screws, no seam at desk
//     level, stiffer body. Feet are stick-on rubber in shallow recesses.
//   · The display is assembled onto the OPEN lid on the bench (PCB in
//     viewport, clamp frame, 4 screws) — no more blind work in a cavity.
//   · Service: 2 rear screws → lift lid → everything reachable from above
//     (RPi, speaker, diffuser screws, wiring).
//   · Lid fixation invisible from front/sides: 2 hook fingers engage
//     catch bars behind the front wall (tilt-in), 2 countersunk M2.5 on
//     the rear wall (where the speaker screws already live).
//
//  Carried over from v5 (unchanged solutions):
//   · LED diffuser: 86×15 window, flush tongue, 2 M2.5 from inside
//   · LCD clamp frame pressing the PCB against the lid's inner face
//   · Speaker bosses + honeycomb, USB-C slot, side vents, mic pocket
//
//  PARTS:
//    body       : tub with integrated floor — PRINT BLACK, bottom down
//    lid        : sloped top slab — PRINT BLACK, sloped face down
//    front_plate: LED diffuser — PRINT WHITE/TRANSLUCENT, back face down
//    lcd_clamp  : LCD retention frame — PRINT BLACK, as modeled
//
//  HARDWARE:
//    2 × M2.5 heat-set insert (Ø3.8) — diffuser wall bosses
//    2 × M2.5 heat-set insert (Ø3.8) — lid rear bosses
//    4 × M3   heat-set insert (Ø4.0) — LCD clamp bosses
//    2 × M2.5 × 10 countersunk       — lid (rear wall)
//    2 × M2.5 × 6 pan-head           — diffuser (from inside, open top)
//    4 × M3 × 8 pan-head             — LCD clamp
//    4 × M3                          — speaker (rear, unchanged)
//    4 × stick-on rubber feet Ø10    — floor recesses
//
//  ASSEMBLY:
//    1. Lid on bench (face down): LCD PCB into viewport → clamp → 4×M3;
//       mic into pocket (glue)
//    2. Body: LED strip on diffuser back → tongue into window → 2×M2.5
//       from the open top; speaker on rear bosses; RPi stack on the floor
//    3. Connect display/touch/mic wiring (leave a service loop)
//    4. Tilt lid in — hook fingers under front catch bars — lower flat,
//       2 × M2.5 countersunk through rear wall
//
//  part = "assembly" | "exploded" | "body" | "lid" | "front_plate" | "lcd_clamp"
// ══════════════════════════════════════════════════════════════

$fn  = 60;
eps  = 0.01;

/* [Part] */
part = "assembly";

/* [Outer envelope — identical silhouette to v5] */
case_w  = 120;
case_d  = 106;
front_h =  45;
rear_h  =  77;
rs      =   7;
wall    =   2;
front_t =   1.5;
top_t   =   3.5;   // sloped top wall thickness = glass height → LCD flush

tilt = atan2(rear_h - front_h, case_d - 2*rs);   // ≈ 19.2°
function top_z(y) =
    let(dZ = rear_h - front_h, dY = case_d - 2*rs)
    (dZ*y + dY*(front_h - rs) + dZ*(case_d/2 - rs) + rs*sqrt(dZ*dZ + dY*dY)) / dY;

/* [Split] */
cut_d   = 10;     // seam plane: 10 mm below the outer slope, ⊥ to it
floor_t = 2.5;    // integrated floor

/* [RPi 4 — no case fixation, sits on the floor] */
rpi_w=85; rpi_d=56; rpi_t=1.6;
rpi_x = -rpi_w/2;
rpi_y = case_d/2 - wall - 5 - rpi_d;
rpi_z = floor_t + 2;

/* [HAT] */
gpio_h=8; hat_gap=3; hat_pcb_t=1.6; hat_comp_h=14;
hat_z = rpi_z + rpi_t + gpio_h + hat_gap;

/* [Display — ST7796S 4.0" 480×320, PCB 108 × 62 mm] */
dsp_open_w =  95;
dsp_open_h =  61;
dsp_y      = -10;
dsp_pcb_t  = 1.6;

/* [Display clamp — same system as v5, now printing cleanly on the lid] */
cl_boss_x   = 44;
cl_boss_y   = 35.5;
cl_boss_od  = 7.5;
cl_boss_h   = 8;
cl_boss_emb = 1;
cl_insert_d = 4.0;
cl_insert_dep = 6;
cl_bar_w    = 8;
cl_bar_t    = 3;
cl_screw_d  = 3.4;
// >>> Verify pad positions against your module's rear components <<<
cl_pad_x    = 44;
cl_pad_y    = 26;
cl_pad_d    = 6;
cl_pad_squeeze = 0.2;

/* [Mic — INMP441 round 15 mm PCB] */
mic_pocket_d     = 17;
mic_pocket_depth =  2;
mic_hole_d       =  2.5;
mic_y = dsp_y + dsp_open_h/2 + 13;

/* [Speaker — 54 mm Ø basket, 42 mm hole spacing] */
spk_z       = 30;
spk_ear_off = 21;
boss_od  = 8;
boss_len = 4;
spk_m3_d = 3.2;

/* [Front LED diffuser — same system as v5, band lowered so the bosses
    sit entirely BELOW the seam plane (no v5-style bottom pillar to avoid
    anymore, so the plate may reach down to z = 5)] */
fp_led_z    = 16;
fp_win_w    = 86;
fp_win_h    = 15;
fp_win_r    = 2;
fp_plate_w  = 92;
fp_plate_z0 = 5;
fp_plate_z1 = 32;    // whole plate + bosses ≥ 1.3 mm under the seam
fp_plate_t  = 2;
fp_boss_x   = 25;
fp_boss_z   = 28;    // boss top 31.25 < seam ≈ 32.6 at the front wall
fp_boss_od  = 6.5;
fp_boss_len = 4;
fp_insert_d = 3.8;
fp_insert_dep = 5;
fp_screw_d  = 2.8;
fp_clear    = 0.3;

/* [Lid fixation] */
// Front: two hook fingers on the lid drop behind catch bars on the front
// wall (engaged by tilting the lid in nose-first).
hk_x     = 49.5;   // hook/catch centre ±X — outside the diffuser plate (±46)
hk_bar_w = 5;      // catch bar length (X)
hk_bar_t = 1.5;    // catch bar thickness (Y, from inner wall face)
hk_bar_z0 = 29.5;  // catch bar bottom
hk_bar_h = 2;
hk_fin_w = 4;      // hook finger width (0.5 mm clearance in the catch)
hk_fin_t = 1.5;    // finger thickness (Y)
hk_nose  = 0.9;    // nose height (slides under the bar, 0.3 mm clearance)
// Rear: two M2.5 countersunk through the rear wall into lid bosses.
lid_scr_x = 15;    // ±X
lid_scr_z = 62.5;  // above speaker rim (57), below rear-top rounding

/* [Feet + floor vents] */
foot_d = 11; foot_dep = 1.2;
foot_pts = [[-45,-38],[45,-38],[-45,38],[45,38]];

// ── Helpers ──────────────────────────────────────────────────

module rr2d(w, h, r) {
    hull() for (a=[-1,1], b=[-1,1])
        translate([a*(w/2-r), b*(h/2-r)]) circle(r);
}

module rrect_y(w, h, r, len) {
    rotate([-90, 0, 0]) linear_extrude(len) rr2d(w, h, r);
}

// Frame on the sloped top face: origin at display centre on the OUTER
// surface, local z ⊥ to the slope (z=0 outer, −top_t inner face).
module slope_frame() {
    translate([0, dsp_y, top_z(dsp_y)]) rotate([tilt, 0, 0]) children();
}

// Half-space above the seam plane (cut_d below the outer slope).
module upper_half() {
    slope_frame()
        translate([-200, -200, -cut_d]) cube([400, 400, 250]);
}

// ── Base solids ──────────────────────────────────────────────

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

// v6: hollow floats floor_t above the bottom → integrated floor.
module inner_hollow() {
    iw  = case_w - 2*wall;
    icr = max(2, rs - wall);
    ify = -(case_d/2 - front_t - icr);
    iry =   case_d/2 - wall   - icr;
    iz_b  = floor_t + icr;
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

module case_shell() {   // walls + floor + top skin, before the split
    difference() { outer_body(); inner_hollow(); }
}

// ── Feature modules (shared with v5) ─────────────────────────

module display_cut() {
    slope_frame()
        translate([-dsp_open_w/2, -dsp_open_h/2, -top_t - eps])
            cube([dsp_open_w, dsp_open_h, top_t * 4 + 2*eps]);
}

module display_clamp_bosses() {
    slope_frame()
    for (mx=[-1,1], my=[-1,1])
        translate([mx*cl_boss_x, my*cl_boss_y, -top_t - cl_boss_h])
            cylinder(h = cl_boss_h + cl_boss_emb, d = cl_boss_od);
}

module display_clamp_insert_holes() {
    slope_frame()
    for (mx=[-1,1], my=[-1,1])
        translate([mx*cl_boss_x, my*cl_boss_y, -top_t - cl_boss_h - eps])
            cylinder(h = cl_insert_dep, d = cl_insert_d);
}

module mic_cut() {
    translate([0, mic_y, top_z(mic_y)])
    rotate([tilt, 0, 0]) {
        translate([0, 0, -top_t])
            cylinder(h = mic_pocket_depth + eps, d = mic_pocket_d);
        cylinder(h = 60, d = mic_hole_d, center = true);
    }
}

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
//  BODY — tub with integrated floor
// ══════════════════════════════════════════════════════════════
module body() {
    difference() {
        union() {
            difference() { case_shell(); upper_half(); }

            // ── Diffuser bosses on inner front wall, above the window
            for (s=[-1,1])
                translate([s*fp_boss_x, -(case_d/2 - front_t) - 1, fp_boss_z])
                    rotate([-90, 0, 0])
                        cylinder(h = fp_boss_len + 1, d = fp_boss_od);

            // ── Speaker bosses on inner rear wall
            for (sx=[-1,1], sz=[-1,1])
                translate([sx*spk_ear_off, case_d/2 - wall, spk_z + sz*spk_ear_off])
                    rotate([90, 0, 0])
                        cylinder(h = boss_len, d = boss_od);

            // ── Front catch bars + cheeks (lid hooks engage here)
            for (s=[-1,1]) {
                wf = -(case_d/2 - front_t);            // inner wall face
                // bar, bridging between the two cheeks
                translate([s*hk_x - hk_bar_w/2, wf - eps, hk_bar_z0])
                    cube([hk_bar_w, hk_bar_t + eps, hk_bar_h]);
                // cheeks: register the finger in X, stiffen the bar ends
                for (c=[-1,1])
                    translate([s*hk_x + c*(hk_bar_w/2 + 0.25) - 0.5, wf - eps, hk_bar_z0 - 1])
                        cube([1, 3.2, 3.8]);   // top 32.3 — below the seam
            }
        }

        // ── Body owns nothing above the seam — clips the diffuser-boss
        //    embeds and catch cheeks where they'd graze the lid skirt
        upper_half();

        // ── Diffuser window + insert pockets (as v5)
        translate([0, -case_d/2 - 1, fp_led_z])
            rrect_y(fp_win_w, fp_win_h, fp_win_r, front_t + 2);
        for (s=[-1,1])
            translate([s*fp_boss_x, -(case_d/2 - front_t) + fp_boss_len + eps, fp_boss_z])
                rotate([90, 0, 0])
                    cylinder(h = fp_insert_dep, d = fp_insert_d);

        // ── Rear honeycomb + speaker screw holes (as v5)
        translate([0, case_d/2 - wall/2, spk_z])
            rotate([90, 0, 0])
                hex_circle(20, wall + 4, 2.5, 0.65);
        for (sx=[-1,1], sz=[-1,1])
            translate([sx*spk_ear_off, case_d/2 + eps, spk_z + sz*spk_ear_off])
                rotate([90, 0, 0])
                    cylinder(h = wall + boss_len + 2*eps, d = spk_m3_d);

        // ── USB-C slot (as v5)
        translate([36, case_d/2 - wall/2, 15])
            rotate([90, 0, 0])
                hull()
                    for (dx=[-1,1])
                        translate([dx*2.5, 0, 0])
                            cylinder(h = wall*2+4, d = 9, center = true);

        // ── Left side airflow vents (as v5)
        for (zv = [hat_z+3, hat_z+11, hat_z+19])
            translate([-case_w/2, 15, zv])
                rotate([0, 90, 0])
                    hull() {
                        translate([0,  7, 0]) cylinder(h=wall+2, d=2.5, center=true);
                        translate([0, -7, 0]) cylinder(h=wall+2, d=2.5, center=true);
                    }

        // ── v6: floor intake slots under the RPi (convection with side vents)
        for (yy = [6, 16, 26])
            hull()
                for (dx=[-1,1])
                    translate([dx*30, yy, -eps])
                        cylinder(h = floor_t + 2*eps, d = 3);

        // ── v6: feet recesses (stick-on rubber)
        for (pt = foot_pts)
            translate([pt[0], pt[1], -eps])
                cylinder(h = foot_dep + eps, d = foot_d);

        // ── v6: lid screw holes through rear wall (countersunk M2.5)
        for (s=[-1,1])
            translate([s*lid_scr_x, case_d/2 + eps, lid_scr_z])
                rotate([90, 0, 0]) {
                    cylinder(h = wall + 4, d = fp_screw_d);
                    cylinder(h = 1.6, d1 = 5.2, d2 = fp_screw_d);
                }
    }
}

// ══════════════════════════════════════════════════════════════
//  LID — sloped face, prints face-down
// ══════════════════════════════════════════════════════════════
module lid() {
    difference() {
        union() {
            intersection() { case_shell(); upper_half(); }

            // ── LCD clamp bosses (print as clean vertical columns)
            display_clamp_bosses();

            // ── Front hook fingers (tilt-in engagement with catch bars)
            for (s=[-1,1]) {
                // finger: descends just behind the catch bar, fuses into
                // the lid's top skin above
                translate([s*hk_x - hk_fin_w/2, -(case_d/2 - front_t) + hk_bar_t + 0.3,
                           hk_bar_z0 - 1 - hk_nose])
                    cube([hk_fin_w, hk_fin_t, 44 - (hk_bar_z0 - 1 - hk_nose)]);
                // nose: reaches forward under the bar (0.3 mm clearance)
                translate([s*hk_x - hk_fin_w/2, -(case_d/2 - front_t) + 0.3,
                           hk_bar_z0 - 1 - hk_nose])
                    cube([hk_fin_w, hk_bar_t + hk_fin_t, hk_nose]);
            }

            // ── Rear screw blocks: hang at the inner rear wall, fuse into
            //    the thick rear-top edge above
            for (s=[-1,1])
                translate([s*lid_scr_x - 6, case_d/2 - wall - 5.3, lid_scr_z - 4])
                    cube([12, 5, 12.5]);
        }

        display_cut();
        display_clamp_insert_holes();
        mic_cut();

        // ── Insert pockets in the rear screw blocks (M2.5, horizontal)
        for (s=[-1,1])
            translate([s*lid_scr_x, case_d/2 - wall - 0.3 + eps, lid_scr_z])
                rotate([90, 0, 0])
                    cylinder(h = fp_insert_dep + 0.5, d = fp_insert_d);
    }
}

// ══════════════════════════════════════════════════════════════
//  FRONT LED DIFFUSER — identical system to v5
// ══════════════════════════════════════════════════════════════
module front_plate() {
    wall_in = -(case_d/2 - front_t);
    py      = wall_in + fp_boss_len;
    difference() {
        union() {
            translate([0, py, (fp_plate_z0 + fp_plate_z1)/2])
                rrect_y(fp_plate_w, fp_plate_z1 - fp_plate_z0, 2, fp_plate_t);
            translate([0, -case_d/2, fp_led_z])
                rrect_y(fp_win_w - 2*fp_clear, fp_win_h - 2*fp_clear,
                        fp_win_r - fp_clear, front_t + fp_boss_len + eps);
        }
        for (s=[-1,1])
            translate([s*fp_boss_x, py - eps, fp_boss_z])
                rotate([-90, 0, 0])
                    cylinder(h = fp_plate_t + 2*eps, d = fp_screw_d);
    }
}

// ══════════════════════════════════════════════════════════════
//  LCD CLAMP — identical to v5
// ══════════════════════════════════════════════════════════════
module lcd_clamp() {
    pad_h = cl_boss_h - dsp_pcb_t + cl_pad_squeeze;
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
module lid_stack(expl=0) {
    // lid + display + clamp, optionally exploded along the slope normal
    translate([0, -expl*sin(tilt), expl*cos(tilt)]) {
        color("#1a1a1a") lid();
        color("darkgreen", 0.7)
            slope_frame()
                translate([-108/2, -62/2, -top_t - dsp_pcb_t])
                    cube([108, 62, dsp_pcb_t]);
        color("#555")
            slope_frame()
                translate([0, 0, -top_t - cl_boss_h - cl_bar_t])
                    lcd_clamp();
    }
}

module internals() {
    color("darkgreen")  translate([rpi_x,rpi_y,rpi_z]) cube([rpi_w,rpi_d,rpi_t]);
    color("#666")       for (dy=[8,24]) translate([rpi_x+rpi_w-18,rpi_y+dy,rpi_z+rpi_t]) cube([18,14,15]);
    color("black")      translate([rpi_x,rpi_y+rpi_d-10,rpi_z+rpi_t]) cube([51,5,gpio_h]);
    color("#3a7a3a")    translate([rpi_x,rpi_y,hat_z]) cube([rpi_w,rpi_d,hat_pcb_t]);
    color("#222")       translate([rpi_x+10,rpi_y+8,hat_z+hat_pcb_t]) cube([30,20,hat_comp_h]);
    color("#111")       translate([0,case_d/2-wall-2,spk_z]) rotate([90,0,0]) cylinder(h=3,d=48);
    color("royalblue",0.9)
        for(i=[-1,0,1])
            translate([i*30, -(case_d/2-front_t) + fp_boss_len + fp_plate_t + 1, fp_led_z])
                sphere(d=4.5);
}

if (part == "assembly") {
    color("#1a1a1a")      body();
    color("white",  0.85) front_plate();
    lid_stack(0);
    internals();
}

if (part == "exploded") {
    color("#1a1a1a")      body();
    color("white",  0.85) translate([0, -25, 0]) front_plate();
    lid_stack(35);
    internals();
}

if (part == "body")        body();
if (part == "lid")         lid();
if (part == "front_plate") front_plate();
if (part == "lcd_clamp")   lcd_clamp();
