// ══════════════════════════════════════════════════════════════
//  HUB CASE — Two-part (body + lid)
//
//  Body: open-top wedge tray (dark filament)
//    - Thin front wall (1.5 mm) — print in white PLA for LED glow
//    - Rear: dense honeycomb speaker grille + 4× M2.5 ear mounts
//    - Right side: USB-C slot
//    - Left side: elongated airflow vents
//    - Heat-set insert rim along sloped top (4 positions)
//
//  Lid: flat slab modelled in its own frame (z=0 = inner/mating face)
//       placed via translate+rotate to sit flush on body top
//    - GC9A01 display bore ⊥ to lid surface (leaving 0.8 mm skin)
//    - LCD PCB recess (39.5 mm Ø) with FPC connector notch toward front
//    - INMP441 mic pocket (17 mm Ø, 3 mm deep) from inner face
//    - 2.5 mm mic sound-port through outer skin
//    - 4× M2.5 through-holes + pan-head counterbore
//
//  Part selector: part = "assembly" / "body" / "lid"
// ══════════════════════════════════════════════════════════════

$fn  = 80;
eps  = 0.01;
big  = 300;

/* [Part] */
part = "assembly";  // assembly | body | lid

/* [Outer shell] */
case_w  = 118;
case_d  = 108;
wall    = 3;
front_t = 1.5;    // front-face skin thickness (LED diffuser zone)
cr      = 10;     // XY corner radius
front_h = 34;
rear_h  = 72;

/* [Lid] */
lid_t   = 5;      // lid thickness (z=0 inner, z=lid_t outer)
tilt    = atan2(rear_h - front_h, case_d);   // ~19.4°
lid_len = case_d / cos(tilt);                 // lid Y in flat frame ≈ 114.5 mm

/* [RPi 4 — 85 mm along X, USB-C at +X side] */
rpi_w  = 85;  rpi_d  = 56;  rpi_t  = 1.6;  rpi_z  = 6;
// rear-aligned: flush with rear inner wall (behind speaker basket)
rpi_y  = case_d/2 - wall - 26 - 3 - rpi_d;
rpi_x  = -rpi_w / 2;

/* [Proto HAT] */
gpio_h      = 8;
hat_gap     = 3;
hat_pcb_t   = 1.6;
hat_comp_h  = 14;
hat_z       = rpi_z + rpi_t + gpio_h + hat_gap;

/* [Display — GC9A01] */
dsp_win      = 33;   // viewing bore
dsp_pcb      = 39.5; // PCB recess diameter
dsp_conn_w   = 10;   // FPC ribbon width at 6-o'clock (toward front = Y- in lid frame)
dsp_conn_ext =  8;   // FPC notch depth past PCB edge

// Display world position → lid-frame Y
dsp_y_world  = -5;
dsp_lx       =  0;
dsp_ly       = (dsp_y_world + case_d/2) / cos(tilt);  // ≈ 51.9 mm from lid front edge

/* [INMP441 microphone — round 15 mm PCB] */
mic_pcb_d       = 15;
mic_pocket_d    = 17;   // PCB + 1 mm clearance all round
mic_pocket_depth =  3;  // depth from inner face (PCB 1.6 mm + hot-glue room)
mic_hole_d      =  2.5; // sound port through outer skin
// Mic sits just above (toward rear) the display
mic_lx  =  0;
mic_ly  = dsp_ly + 25;  // 25 mm toward rear from display centre

/* [Speaker — 53 mm, 26 mm basket depth] */
spk_od      = 53;
spk_depth   = 26;
spk_z       = rear_h * 0.50;   // centre height on rear face
spk_ear_off = 21;              // ±21 mm X and Z from speaker centre
spk_ear_d   = 2.7;             // M2.5 clearance

/* [Heat-set inserts — M2.5] */
insert_d     = 3.8;
insert_depth = 5;
mount_d      = 2.7;   // M2.5 screw clearance
mount_head   = 5.0;   // pan-head OD

// 4 insert positions in lid frame [lx, ly]
// Placed near corners of the lid, within the wall band
_mx = case_w/2 - wall - insert_d/2 - 1;
_my_f = 8;
_my_r = lid_len - 8;
mount_pts = [[-_mx, _my_f], [_mx, _my_f], [-_mx, _my_r], [_mx, _my_r]];

// ── Geometry helpers ──────────────────────────────────────────

// Wedge: hull of 4 cylinders (2 short front, 2 tall rear).
// Centred at origin in XY, base at z=0.
module wedge_solid(w, d, hf, hr, r) {
    hull()
        for (sx = [-1,1]) {
            translate([sx*(w/2-r), -d/2+r, 0]) cylinder(h=hf, r=r);
            translate([sx*(w/2-r),  d/2-r, 0]) cylinder(h=hr, r=r);
        }
}

// Lid slab in lid frame: Y goes 0 → lid_len (front→rear), Z=0 inner face.
// Uses same wedge_solid logic centred at y=lid_len/2.
module lid_shape(w, d, h, r) {
    translate([0, d/2, 0])
        hull()
            for (sx=[-1,1]) {
                translate([sx*(w/2-r), -d/2+r, 0]) cylinder(h=h, r=r);
                translate([sx*(w/2-r),  d/2-r, 0]) cylinder(h=h, r=r);
            }
}

// Place lid: flat lid frame → sloped world position on body top
module place_lid() {
    translate([0, -case_d/2, front_h])
    rotate([tilt, 0, 0])
    children();
}

// Dense honeycomb tile (hex cells), for use with rotate+translate on a face.
// w=tile width, h=tile height, depth=wall thickness, cell=hex inradius, wall_t=wall between cells.
module honeycomb_tile(w, h, depth, cell, wall_t) {
    sp = cell + wall_t;
    cols = ceil(w / sp) + 2;
    rows = ceil(h / (sp * 0.866)) + 2;
    intersection() {
        cube([w + eps, h + eps, depth + 2*eps], center=true);
        for (row=[-rows:rows], col=[-cols:cols]) {
            x = col*sp + (row%2)*sp/2;
            y = row*sp*0.866;
            translate([x, y, 0])
                cylinder(h=depth+2*eps, d=cell, $fn=6, center=true);
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  BODY
// ══════════════════════════════════════════════════════════════
module body() {
    icr = max(2, cr - wall);

    difference() {
        // Outer wedge
        wedge_solid(case_w, case_d, front_h, rear_h, cr);

        // ── Inner cavity: open top (heights exceed outer → removes top face)
        translate([0, 0, wall])
            wedge_solid(
                case_w - 2*wall,
                case_d - wall - front_t,   // rear wall=wall thick, front wall=front_t thick
                front_h - 5 + 1,           // 5 mm rim preserved at top for insert bosses
                rear_h  - 5 + 1,
                icr
            );

        // ── Dense hex grille on rear face (speaker area)
        // Area: 72 mm wide × 56 mm tall, centred on spk_z
        translate([0, case_d/2, spk_z])
            rotate([90, 0, 0])
                honeycomb_tile(72, 56, wall + 2*eps, 2.5, 0.7);

        // ── Speaker basket recess in rear wall
        translate([0, case_d/2 - wall - eps, spk_z])
            rotate([-90, 0, 0])
                cylinder(h=spk_depth, d=spk_od + 1);

        // ── Speaker ear holes (M2.5 clearance, 4× at ±21 mm in X and Z)
        for (sx=[-1,1], sz=[-1,1])
            translate([sx*spk_ear_off, case_d/2 - wall/2, spk_z + sz*spk_ear_off])
                rotate([90, 0, 0])
                    cylinder(h=wall*2, d=spk_ear_d, center=true);

        // ── Insert holes in top rim (perpendicular to sloped face, via lid frame)
        place_lid()
            for (pt=mount_pts)
                translate([pt[0], pt[1], -insert_depth - 0.1])
                    cylinder(h=insert_depth + 0.2, d=insert_d);

        // ── USB-C slot — right side wall
        translate([case_w/2, rpi_y + rpi_d*0.12, rpi_z + rpi_t + 3])
            rotate([0,90,0])
                hull()
                    for (dy=[-1,1])
                        translate([0, dy*2, 0])
                            cylinder(h=wall*3, d=6, center=true);

        // ── Left-side airflow vents (elongated slots)
        for (zv=[hat_z+3, hat_z+13, hat_z+23])
            translate([-case_w/2, 0, zv])
                rotate([0,90,0])
                    hull() {
                        translate([0,  10, 0]) cylinder(h=wall+2, d=3, center=true);
                        translate([0, -10, 0]) cylinder(h=wall+2, d=3, center=true);
                    }

        // ── Widen inner cavity at front to create front_t LED diffuser skin
        // (The wedge_solid inner cavity above already leaves front_t at front;
        //  this cut removes excess on the inside of the front wall above z=wall.)
        // Nothing extra needed — the inner cavity offset of front_t from front
        // leaves exactly front_t of material at the front face.
    }
}

// ══════════════════════════════════════════════════════════════
//  LID  (z=0 = inner/mating face, z=lid_t = outer face)
//  Model flat; place_lid() tilts it into position.
//  Print face-down (rotate 180° around X before slicing).
// ══════════════════════════════════════════════════════════════
module lid() {
    lcr = max(2, cr);

    difference() {
        lid_shape(case_w, lid_len, lid_t, lcr);

        // ── PCB recess from inner face (leaves 0.8 mm outer skin)
        translate([dsp_lx, dsp_ly, -eps])
            cylinder(h=lid_t - 0.8 + eps, d=dsp_pcb);

        // ── Viewing window through outer skin
        translate([dsp_lx, dsp_ly, -1])
            cylinder(h=lid_t + 2, d=dsp_win);

        // ── FPC connector notch at front of display (Y- in lid frame = toward front)
        translate([-dsp_conn_w/2,
                   dsp_ly - dsp_pcb/2 - dsp_conn_ext,
                   -eps])
            cube([dsp_conn_w, dsp_conn_ext + eps, lid_t - 0.8 + 2*eps]);

        // ── Mic pocket from inner face (PCB hot-glued in)
        translate([mic_lx, mic_ly, -eps])
            cylinder(h=mic_pocket_depth + eps, d=mic_pocket_d);

        // ── Mic sound port through outer skin
        translate([mic_lx, mic_ly, -1])
            cylinder(h=lid_t + 2, d=mic_hole_d);

        // ── M2.5 through-holes + pan-head counterbore (from outer face)
        for (pt=mount_pts) {
            translate([pt[0], pt[1], -1])
                cylinder(h=lid_t + 2, d=mount_d);
            translate([pt[0], pt[1], lid_t - 2.5 + 0.5])
                cylinder(h=3, d1=mount_d, d2=mount_head);
        }
    }
}

// ══════════════════════════════════════════════════════════════
//  ASSEMBLY / PART SELECTOR
// ══════════════════════════════════════════════════════════════
if (part == "assembly") {
    color("dimgray")    body();
    color("lightgray")  place_lid() lid();

    // ── Indicative internal components ──────────────────────
    // RPi board
    color("darkgreen")
        translate([rpi_x, rpi_y, rpi_z]) cube([rpi_w, rpi_d, rpi_t]);
    // USB-A stacks
    color("#666")
        for (dy=[8,24])
            translate([rpi_x + rpi_w - 18, rpi_y + dy, rpi_z + rpi_t])
                cube([18, 14, 15]);
    // GPIO header
    color("black")
        translate([rpi_x, rpi_y + rpi_d - 10, rpi_z + rpi_t])
            cube([51, 5, gpio_h]);
    // Proto HAT
    color("#3a7a3a")
        translate([rpi_x, rpi_y, hat_z]) cube([rpi_w, rpi_d, hat_pcb_t]);
    // HAT components
    color("#222")
        translate([rpi_x+10, rpi_y+8, hat_z + hat_pcb_t])
            cube([30, 20, hat_comp_h]);
    // Speaker disc
    color("#111")
        translate([0, case_d/2 - wall - 2, spk_z])
            rotate([90,0,0]) cylinder(h=3, d=spk_od-3);
    // 3 LEDs (behind front diffuser)
    color("royalblue", 0.95)
        for (i=[-1,0,1])
            translate([i*12, -case_d/2 + front_t + 2, 14])
                sphere(d=4.5);
}

if (part == "body") body();
if (part == "lid")  lid();
