// ══════════════════════════════════════════════════════════════
//  HUB CASE v4 — Voice Assistant
//
//  THREE PARTS:
//    shell      : fully organic rounded wedge (hull of 8 spheres — zero sharp edges)
//                 open bottom, front wall REMOVED (filled by front_plate)
//                 rear  : dense circular honeycomb + 4 speaker bosses (M2.5 inserts)
//                 top   : ST7796S 4.0" LCD rectangular viewport 95 × 61 mm
//                         4 blind M3 insert pockets from inner face (102 × 54 mm pattern)
//                         outer top surface completely clean — no through-holes
//                         INMP441 mic pocket from inner face + 2.5 mm sound port
//                 front : USB-C slot (left of centre — use right-angle adapter)
//                 left  : elongated airflow vents
//                 inside: 4 pillars ribbed to walls (M2.5 heat-set inserts) for plate
//                 PRINT IN BLACK
//
//    plate      : flat bottom slab, M2.5 countersunk screws from below (invisible)
//                 PRINT IN BLACK
//
//    front_plate: 1.5 mm organic front face insert — LED diffuser
//                 slides in from open bottom before plate is installed; glue around
//                 inner perimeter. Shape is the exact front wall of the shell body.
//                 PRINT IN WHITE / TRANSLUCENT
//                 Slicer orientation: rotate 90° about X (flat face down)
//
//  LCD mounting (no holes through outer top):
//    PCB sits against inner top face (glass faces outward through viewport).
//    top_t = 3.5 mm = glass height → LCD glass flush with outer surface.
//    M3 screws from inside shell, through PCB mounting holes, into blind pockets.
//
//  part = "assembly" | "shell" | "plate" | "front_plate"
// ══════════════════════════════════════════════════════════════

$fn  = 60;
eps  = 0.01;

/* [Part] */
part = "assembly";

/* [Outer envelope] */
// case_w = 120 fits the 108 mm LCD PCB with ~6 mm clearance each side.
// case_d, front_h, rear_h unchanged from v3 — speaker / RPi / HAT stack unchanged.
case_w  = 120;   // width (X)
case_d  = 106;   // depth (Y)
front_h =  45;   // body height at front face (Y-)
rear_h  =  77;   // body height at rear face  (Y+)
rs      =   7;   // sphere radius — rounds ALL edges and corners
wall    =   2;   // side / rear wall thickness
front_t =   1.5; // front LED diffuser skin
top_t   =   3.5; // sloped top wall thickness = glass height → LCD flush with outer surface

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
// No FPC ribbon — SPI pins are edge-mounted on the PCB.
// Mounting: PCB pressed against inner top face from inside; LCD glass (3.5 mm)
// protrudes outward through viewport → flush with outer surface (top_t = 3.5 mm).
// Blind insert pockets from inner face (no through-holes on outer top).
// Pocket inner edge at X = 51 − 2.25 = 48.75 mm > viewport half-width 47.5 mm → no overlap.
dsp_open_w    =  95;   // viewport opening width  (X)
dsp_open_h    =  61;   // viewport opening height (local Y, along sloped surface)
dsp_mnt_x     =  51;   // mounting hole ±X from display centre (102 mm bolt span)
dsp_mnt_y     =  27;   // mounting hole ±Y from display centre ( 54 mm bolt span)
dsp_y         = -10;   // world-Y of display centre (negative = toward front)
dsp_pocket_d  =   4.5; // M3 insert pocket diameter (from inner face)
dsp_pocket_dep=   2.5; // pocket depth — leaves 1 mm outer skin (top_t 3.5 − 2.5 = 1 mm)

/* [Mic — INMP441 round 15 mm PCB] */
mic_pocket_d     = 17;   // PCB + 1 mm clearance
mic_pocket_depth =  2;   // leaves 1.5 mm outer skin (top_t=3.5 − 2 = 1.5 mm)
mic_hole_d       =  2.5;
// 13 mm gap behind the rear edge of the viewport (display rear edge ≈ world-Y +19 mm).
// Mic centre at ≈ +33.5 mm; pocket edge at +42 mm; inner rear wall at +51 mm → 9 mm ✓
mic_y = dsp_y + dsp_open_h/2 + 13;   // ≈ +33.5 mm world-Y

/* [Speaker — 54 mm Ø basket, 42 mm hole spacing] */
spk_z       = 30;
spk_ear_off = 21;   // ±21 mm in X and Z (42 mm hole-to-hole)
spk_ear_d   =  2.7;

/* [Speaker boss] */
boss_od  = 8;
boss_len = 4;
spk_m3_d = 3.2;

/* [Bottom-plate mounting pillars] */
pillar_od    =  7;
pillar_h     = 12;
insert_d     =  3.8;
insert_depth =  5;
mount_d      =  2.7;
mount_head_d =  5.5;
mount_head_h =  2.5;

/* [Front LED diffuser plate] */
fp_z0  = 7;       // bottom Z — centred on LEDs at Z=14 (plate spans Z 7→22)
fp_h   = 15;      // height of the diffuser strip (covers LEDs at Z=14)
fp_lip = 1;       // lip width all around (mm)
// fp_w (plate width) = case_w − 2×wall = 116 mm — computed inside modules

/* [Plate / split-line] */
split_z = 3;
plate_t = split_z;

pillar_inset = 5;
pillar_pts = [
    [-(case_w/2 - wall - pillar_inset), -(case_d/2 - front_t - pillar_inset)],
    [ (case_w/2 - wall - pillar_inset), -(case_d/2 - front_t - pillar_inset)],
    [-(case_w/2 - wall - pillar_inset),  (case_d/2 - wall    - pillar_inset)],
    [ (case_w/2 - wall - pillar_inset),  (case_d/2 - wall    - pillar_inset)],
];

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
// No PCB pocket, no FPC pocket, no external screw holes — outer top surface is clean.
module display_cut(dy) {
    translate([0, dy, top_z(dy)])
    rotate([tilt, 0, 0])
        translate([-dsp_open_w/2, -dsp_open_h/2, -top_t - eps])
            cube([dsp_open_w, dsp_open_h, top_t * 4 + 2*eps]);
}

// Blind M3 insert pockets drilled from the inner top face toward the outer surface.
// No protrusion into shell cavity → no debording of the viewport.
// Pocket inner edge: 51 − 2.25 = 48.75 mm > viewport half-width 47.5 mm → clear ✓
// Screw entry from inside shell: through PCB Ø3.2 mm hole, tip into pocket insert.
module display_mounting_pockets(dy) {
    translate([0, dy, top_z(dy)])
    rotate([tilt, 0, 0])
    for (mx=[-1,1], my=[-1,1])
        // Pocket starts at inner face (z=−top_t), extends toward outer surface.
        translate([mx*dsp_mnt_x, my*dsp_mnt_y, -top_t])
            cylinder(h = dsp_pocket_dep, d = dsp_pocket_d);
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

            // ── 4 mounting pillars with ribs and base skirts
            skirt_h    = 5;
            rib_thick  = 2;
            rib_width  = 7;
            intersection() {
                outer_body();
                union() {
                    for (pt = pillar_pts)
                        translate([pt[0], pt[1], split_z])
                            cylinder(h = pillar_h, d = pillar_od);

                    for (pt = pillar_pts) {
                        sx = sign(pt[0]);
                        sy = sign(pt[1]);
                        owall_x = sx * (case_w/2 + 5);
                        owall_y = sy * (case_d/2 + 5);
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
                }
            }

            // ── Speaker bosses on inner rear wall
            for (sx=[-1,1], sz=[-1,1])
                translate([sx*spk_ear_off, case_d/2 - wall, spk_z + sz*spk_ear_off])
                    rotate([90, 0, 0])
                        cylinder(h = boss_len, d = boss_od);
        }

        // ── LCD viewport (clean rectangular cut, no external holes)
        display_cut(dsp_y);
        // ── Blind M3 insert pockets from inner top face
        display_mounting_pockets(dsp_y);
        // ── Mic pocket + sound port
        mic_cut(mic_y);

        // ── Rear honeycomb (r=20 mm, cell 2.5 mm, wall 0.65 mm)
        translate([0, case_d/2 - wall/2, spk_z])
            rotate([90, 0, 0])
                hex_circle(20, wall + 4, 2.5, 0.65);

        // ── Speaker boss M3 holes (outer rear face → through wall → through boss)
        for (sx=[-1,1], sz=[-1,1])
            translate([sx*spk_ear_off, case_d/2 + eps, spk_z + sz*spk_ear_off])
                rotate([90, 0, 0])
                    cylinder(h = wall + boss_len + 2*eps, d = spk_m3_d);

        // ── USB-C slot on rear wall, viewer's left of speaker (+X side).
        // Free zone with case_w=120: pillar at +53, boss at +21 → centre ≈ +37.
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

        // ── Insert holes in bottom-plate pillars
        for (pt = pillar_pts)
            translate([pt[0], pt[1], split_z - eps])
                cylinder(h = insert_depth, d = insert_d);

        // ── Front plate stepped opening: outer rebate (half depth) + inner through-hole
        {
            fp_w = case_w - 2*wall;
            // Outer rebate — receives the lip (front_t/2 deep, full plate size)
            translate([-fp_w/2, -case_d/2 - eps, fp_z0])
                cube([fp_w, front_t/2 + eps, fp_h]);
            // Center through-hole — receives the inner panel (full depth, inset by fp_lip)
            translate([-(fp_w/2 - fp_lip), -case_d/2 - eps, fp_z0 + fp_lip])
                cube([fp_w - 2*fp_lip, front_t + 2*eps, fp_h - 2*fp_lip]);
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  BOTTOM PLATE
// ══════════════════════════════════════════════════════════════
module plate() {
    difference() {
        intersection() {
            outer_body();
            translate([-case_w, -case_d, 0])
                cube([case_w*2, case_d*2, split_z]);
        }
        for (pt = pillar_pts) {
            translate([pt[0], pt[1], -eps])
                cylinder(h = split_z + 2*eps, d = mount_d);
            translate([pt[0], pt[1], -eps])
                cylinder(h = mount_head_h, d2=mount_d, d1=mount_head_d);
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  FRONT LED DIFFUSER PLATE
// ══════════════════════════════════════════════════════════════
module front_plate() {
    // Stepped rectangular LED diffuser — print in white/translucent.
    // Slicer: rotate 90° about X so the flat outer face is down.
    //
    // Cross-section (Y = depth into wall, X/Z = width/height):
    //   Outer layer  (lip):   fp_w × fp_h × front_t/2  — seats in shell outer rebate
    //   Inner panel (center): inset fp_lip all around    — passes through inner opening
    //
    // Assembly: slide in from open shell bottom, outer face flush, glue inner rim.
    fp_w = case_w - 2*wall;   // 116 mm — fits between inner side walls
    // Outer layer (full width, half thickness) — the 1 mm lip seats in shell rebate
    translate([-fp_w/2, -case_d/2, fp_z0])
        cube([fp_w, front_t/2, fp_h]);
    // Inner panel (inset by fp_lip all around, remaining half thickness) — through wall
    translate([-(fp_w/2 - fp_lip), -case_d/2 + front_t/2, fp_z0 + fp_lip])
        cube([fp_w - 2*fp_lip, front_t/2, fp_h - 2*fp_lip]);
}

// ══════════════════════════════════════════════════════════════
//  OUTPUT
// ══════════════════════════════════════════════════════════════
if (part == "assembly") {
    color("#1a1a1a")      shell();
    color("#1a1a1a", 0.7) plate();
    color("white",  0.85) front_plate();

    // RPi 4
    color("darkgreen")  translate([rpi_x,rpi_y,rpi_z]) cube([rpi_w,rpi_d,rpi_t]);
    color("#666")       for (dy=[8,24]) translate([rpi_x+rpi_w-18,rpi_y+dy,rpi_z+rpi_t]) cube([18,14,15]);
    color("black")      translate([rpi_x,rpi_y+rpi_d-10,rpi_z+rpi_t]) cube([51,5,gpio_h]);
    color("#3a7a3a")    translate([rpi_x,rpi_y,hat_z]) cube([rpi_w,rpi_d,hat_pcb_t]);
    color("#222")       translate([rpi_x+10,rpi_y+8,hat_z+hat_pcb_t]) cube([30,20,hat_comp_h]);
    // Speaker
    color("#111")       translate([0,case_d/2-wall-2,spk_z]) rotate([90,0,0]) cylinder(h=3,d=48);
    // Front LEDs
    color("royalblue",0.9) for(i=[-1,0,1]) translate([i*12,-case_d/2+front_t+2,14]) sphere(d=4.5);
    // LCD PCB (108 × 62 mm, 1.6 mm thick), sitting on the sloped top surface
    color("darkgreen", 0.7)
        translate([0, dsp_y, top_z(dsp_y)])
        rotate([tilt, 0, 0])
        translate([-108/2, -62/2, 0])
            cube([108, 62, 1.6]);
}

if (part == "shell")       shell();
if (part == "plate")       plate();
if (part == "front_plate") front_plate();
