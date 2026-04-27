// ══════════════════════════════════════════════════════════════
//  HUB CASE — Voice Assistant
//
//  TWO PARTS:
//    shell : fully organic rounded wedge (hull of 8 spheres — zero sharp edges)
//            open bottom, front wall 1.5 mm (print white PLA → LEDs glow)
//            rear  : dense circular honeycomb + 4 speaker bosses (M2.5 inserts)
//            top   : GC9A01 display pocket from inner face (voice_assistant_case style)
//                    INMP441 mic pocket from inner face + 2.5 mm sound port
//            rear  : USB-C slot (right of centre — use right-angle adapter)
//            left  : elongated airflow vents
//            inside: 4 pillars ribbed to walls (M2.5 heat-set inserts) for plate
//
//    plate : flat bottom slab, M2.5 countersunk screws from below (invisible)
//
//  part = "assembly" | "shell" | "plate"
// ══════════════════════════════════════════════════════════════

$fn  = 60;
eps  = 0.01;

/* [Part] */
part = "assembly";

/* [Outer envelope] */
case_w  = 118;   // width (X)
case_d  = 108;   // depth (Y)
front_h =  34;   // body height at front face (Y-)
rear_h  =  72;   // body height at rear face  (Y+)
rs      =   8;   // sphere radius — rounds ALL edges and corners
wall    =   2;   // side / rear wall thickness
front_t =   1.5; // front LED diffuser skin
top_t   =   3;   // sloped top wall thickness (0.8 mm outer skin + 2.2 mm recess)

// Slope of the organic top face = tangent plane between front/rear-top sphere centres.
// Sphere centres span case_d - 2*rs in Y, not the full case_d.
tilt = atan2(rear_h - front_h, case_d - 2*rs);   // ≈ 22.4°
function top_z(y) =
    let(dZ = rear_h - front_h, dY = case_d - 2*rs)
    (dZ*y + dY*(front_h - rs) + dZ*(case_d/2 - rs) + rs*sqrt(dZ*dZ + dY*dY)) / dY;

/* [RPi 4] */
rpi_w=85; rpi_d=56; rpi_t=1.6; rpi_z=6;
rpi_y = case_d/2 - wall - 26 - 4 - rpi_d;
rpi_x = -rpi_w/2;

/* [HAT] */
gpio_h=8; hat_gap=3; hat_pcb_t=1.6; hat_comp_h=14;
hat_z = rpi_z + rpi_t + gpio_h + hat_gap;

/* [Display — GC9A01] */
dsp_win      = 33;    // viewing bore
dsp_pcb      = 39.5;  // PCB pocket diameter
dsp_conn_w   = 25;    // connector pocket width (X)
dsp_conn_ext = 6;    // connector pocket depth beyond PCB edge (local -Y = toward front)
dsp_y        = -5;    // world-Y of display centre on top surface

/* [Mic — INMP441 round 15 mm PCB] */
mic_pocket_d    = 17;   // PCB + 1 mm clearance
mic_pocket_depth =  2;  // leaves 1 mm outer skin (top_t=3 − 2 = 1 mm)
mic_hole_d      =  2.5;
mic_y = dsp_y + 25;

/* [Speaker — 53 mm Ø, 26 mm basket depth] */
spk_z       = 36;
spk_ear_off = 21;   // ±21 mm in X and Z (42 mm hole-to-hole)
spk_ear_d   =  2.7; // M2.5 clearance through boss from interior

/* [Speaker boss] */
boss_od  = 8;
boss_len = 4;   // protrusion from inner rear wall into case interior
spk_m3_d = 3.2; // M3 drill hole

/* [Bottom-plate mounting pillars] */
pillar_od    = 10;
pillar_h     = 14;
insert_d     =  3.8;
insert_depth =  5;
mount_d      =  2.7;
mount_head_d =  5.5;
mount_head_h =  2.5;

/* [Plate / split-line between shell and plate] */
// The shell's outer bottom is the lower half of the 4 corner spheres (radius rs=8),
// reaching z=0 at the tangent points and curving up to z=rs at the outermost sides.
// We split the case HORIZONTALLY at z = split_z. Below this plane is the plate,
// above it is the shell. Because the split is a flat horizontal cut through the
// SAME rounded outer body, the two halves share an identical perimeter at z=split_z
// and re-assemble into a continuous rounded bottom with zero gap.
split_z = 3;     // plate is the slice of the outer body from z=0 to z=split_z
plate_t = split_z;

// Pillar XY positions — inside case, clear of RPi (y ≈ −34 … +22) and speaker bosses
pillar_pts = [[-44,-38], [44,-38], [-44,34], [44,34]];

// ── Modules ──────────────────────────────────────────────────

// Fully organic wedge: hull of 8 spheres.
// All edges and corners rounded with radius rs.
// Bottom at z=0, sloped top from front_h to rear_h.
module outer_body() {
    hull() {
        // 4 bottom spheres (all at z=rs so outer bottom lands at z=0)
        for (sx=[-1,1], sy=[-1,1])
            translate([sx*(case_w/2-rs), sy*(case_d/2-rs), rs])
                sphere(r=rs);
        // 2 front-top spheres
        for (sx=[-1,1])
            translate([sx*(case_w/2-rs), -(case_d/2-rs), front_h-rs])
                sphere(r=rs);
        // 2 rear-top spheres
        for (sx=[-1,1])
            translate([sx*(case_w/2-rs), +(case_d/2-rs), rear_h-rs])
                sphere(r=rs);
    }
}

// Inner hollow: hull of 8 spheres mirroring outer_body exactly.
// Each sphere is inset by wall/front_t/top_t from the corresponding outer sphere.
// Sphere tangents define the wall faces; organic corner rounding matches outer body.
module inner_hollow() {
    iw  = case_w - 2*wall;
    icr = max(2, rs - wall);            // inner sphere radius = 6
    ify = -(case_d/2 - front_t - icr); // inner front Y = -46.5
    iry =   case_d/2 - wall   - icr;   // inner rear  Y = +46
    // Z centres: bottom tangent at z=−1, top tangent at z=front/rear_h − top_t
    iz_b  = icr - 1;                   // bottom sphere centre z = 5
    iz_ft = front_h - top_t - icr;     // front-top centre z   = 25
    iz_rt = rear_h  - top_t - icr;     // rear-top  centre z   = 63

    hull()
        for (sx=[-1,1]) {
            translate([sx*(iw/2-icr), ify, iz_b])  sphere(r=icr);
            translate([sx*(iw/2-icr), iry, iz_b])  sphere(r=icr);
            translate([sx*(iw/2-icr), ify, iz_ft]) sphere(r=icr);
            translate([sx*(iw/2-icr), iry, iz_rt]) sphere(r=icr);
        }
}

// Cut display pocket ⊥ to sloped top.
// Local z=0 = outer surface, negative = into body.
// Pocket goes from inner face (z=−top_t) to 0.8 mm skin (z=−0.8) — like voice_assistant_case face plate.
module display_cut(dy) {
    translate([0, dy, top_z(dy)])
    rotate([tilt, 0, 0]) {
        // PCB pocket from inner face, leaving 0.8 mm outer skin
        translate([0, 0, -top_t])
            cylinder(h = top_t - 0.8 + eps, d = dsp_pcb);
        // Connector pocket: 25 mm wide × 10 mm deep, exits PCB edge toward front (local -Y)
        translate([-dsp_conn_w/2, -(dsp_pcb/2 + dsp_conn_ext), -top_t])
            cube([dsp_conn_w, dsp_conn_ext + eps+5, top_t - 0.8 + eps]);
        // Viewing bore through outer skin
        cylinder(h = 60, d = dsp_win, center = true);
    }
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

// Dense circular hex honeycomb (voice_assistant_case style).
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
            // Outer organic shell minus inner hollow, with the bottom slice
            // (z < split_z) removed \u2014 that slice is the plate.
            difference() {
                outer_body();
                inner_hollow();
                // Remove everything below z=split_z \u2014 belongs to the plate.
                translate([-case_w, -case_d, -50])
                    cube([case_w*2, case_d*2, 50 + split_z]);
            }

            // ── 4 mounting pillars + ribs
            // Pillars sit ON TOP of the plate's flat top face (z=split_z) and rise
            // into the shell cavity. Their flat bottom faces mate directly with the
            // matching flat pads on top of the plate.
            intersection() {
                outer_body();
                union() {
                    for (pt = pillar_pts)
                        translate([pt[0], pt[1], split_z])
                            cylinder(h = pillar_h, d = pillar_od);

                    for (pt = pillar_pts) {
                        sx = sign(pt[0]);
                        sy = sign(pt[1]);
                        iwall_x = sx * (case_w/2 - wall);
                        iwall_y = sy > 0
                                  ? case_d/2 - wall
                                  : -(case_d/2 - front_t);
                        hull() {
                            translate([pt[0], pt[1], split_z])
                                cylinder(h = pillar_h, d = pillar_od);
                            translate([iwall_x - sx*0.5, pt[1]-1.5, split_z])
                                cube([1, 3, pillar_h]);
                        }
                        hull() {
                            translate([pt[0], pt[1], split_z])
                                cylinder(h = pillar_h, d = pillar_od);
                            translate([pt[0]-1.5, iwall_y - sy*0.5, split_z])
                                cube([3, 1, pillar_h]);
                        }
                    }
                }
            }

            // ── Speaker bosses: cylinders from inner rear wall into case
            for (sx=[-1,1], sz=[-1,1])
                translate([sx*spk_ear_off, case_d/2 - wall, spk_z + sz*spk_ear_off])
                    rotate([90, 0, 0])
                        cylinder(h = boss_len, d = boss_od);
        }

        // ── Display pocket + mic (from inner face — see display_cut/mic_cut)
        display_cut(dsp_y);
        mic_cut(mic_y);

        // ── Rear: dense honeycomb (r=20 mm, cell 2.5 mm, wall 0.65 mm)
        // Centred at wall midpoint so hex_circle (center=true) cuts fully through.
        translate([0, case_d/2 - wall/2, spk_z])
            rotate([90, 0, 0])
                hex_circle(20, wall + 4, 2.5, 0.65);

        // ── Speaker boss M3 holes (outer rear face → through wall → through boss)
        for (sx=[-1,1], sz=[-1,1])
            translate([sx*spk_ear_off, case_d/2 + eps, spk_z + sz*spk_ear_off])
                rotate([90, 0, 0])
                    cylinder(h = wall + boss_len + 2*eps, d = spk_m3_d);

        // ── Rear: USB-C slot (right of centre, right-angle adapter)
        translate([38, case_d/2 - wall/2, rpi_z + rpi_t + 4])
            rotate([90, 0, 0])
                hull()
                    for (dx=[-1,1])
                        translate([dx*4, 0, 0])
                            cylinder(h = wall*2+2, d = 9, center = true);

        // ── Left side: airflow vents (shifted toward rear)
        for (zv = [hat_z+3, hat_z+13, hat_z+23])
            translate([-case_w/2, 25, zv])
                rotate([0, 90, 0])
                    hull() {
                        translate([0,  10, 0]) cylinder(h=wall+2, d=3, center=true);
                        translate([0, -10, 0]) cylinder(h=wall+2, d=3, center=true);
                    }

        // ── Insert holes in pillars (from pillar bottom face = z=split_z up)
        for (pt = pillar_pts)
            translate([pt[0], pt[1], split_z - eps])
                cylinder(h = insert_depth, d = insert_d);
    }
}

// ══════════════════════════════════════════════════════════════
//  BOTTOM PLATE
// ══════════════════════════════════════════════════════════════
module plate() {
    // The plate is EXACTLY the bottom slice of the outer body from z=0 to z=split_z.
    // By construction its perimeter at z=split_z is identical to the shell's perimeter
    // at z=split_z — they were cut from the same solid — so when stacked they form
    // a continuous, gap-free rounded bottom.
    //
    //   • bottom surface (z ≤ split_z): shell's rounded bottom (lower-half corner spheres)
    //   • top surface     (z  = split_z): flat, matches the shell's cut face exactly
    //   • perimeter at the split: identical outline on both parts → flush fit
    difference() {
        intersection() {
            outer_body();
            // Slab from z=0 to z=split_z.
            translate([-case_w, -case_d, 0])
                cube([case_w*2, case_d*2, split_z]);
        }
        // M2.5 clearance hole + countersink from plate bottom.
        for (pt = pillar_pts) {
            translate([pt[0], pt[1], -eps])
                cylinder(h = split_z + 2*eps, d = mount_d);
            translate([pt[0], pt[1], -eps])
                cylinder(h = mount_head_h, d2=mount_d, d1=mount_head_d);
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  OUTPUT
// ══════════════════════════════════════════════════════════════
if (part == "assembly") {
    color("dimgray")      shell();
    color("dimgray", 0.7) plate();

    color("darkgreen")  translate([rpi_x,rpi_y,rpi_z]) cube([rpi_w,rpi_d,rpi_t]);
    color("#666")       for (dy=[8,24]) translate([rpi_x+rpi_w-18,rpi_y+dy,rpi_z+rpi_t]) cube([18,14,15]);
    color("black")      translate([rpi_x,rpi_y+rpi_d-10,rpi_z+rpi_t]) cube([51,5,gpio_h]);
    color("#3a7a3a")    translate([rpi_x,rpi_y,hat_z]) cube([rpi_w,rpi_d,hat_pcb_t]);
    color("#222")       translate([rpi_x+10,rpi_y+8,hat_z+hat_pcb_t]) cube([30,20,hat_comp_h]);
    color("#111")       translate([0,case_d/2-wall-2,spk_z]) rotate([90,0,0]) cylinder(h=3,d=48);
    color("royalblue",0.9) for(i=[-1,0,1]) translate([i*12,-case_d/2+front_t+2,14]) sphere(d=4.5);
}

if (part == "shell") shell();
if (part == "plate") plate();
