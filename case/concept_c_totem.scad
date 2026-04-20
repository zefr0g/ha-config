// ══════════════════════════════════════════════════════════════
//  CONCEPT C — "Totem"
//  Tall waisted column (hourglass-ish).
//  Bottom bulb  = speaker chamber, radial slot grille.
//  Narrow waist = RPi + HAT stacked vertically.
//  Top bulb     = display at front, LED ring halo around it.
// ══════════════════════════════════════════════════════════════

$fn = 120;

// Profile samples (z, radius)
// Bottom bulb peaks at z≈35, waist at z≈90, head peaks at z≈155.
profile = [
    [  0, 44],
    [ 10, 47],
    [ 25, 48],
    [ 40, 45],
    [ 60, 36],
    [ 85, 28],
    [110, 28],
    [130, 36],
    [150, 42],
    [165, 42],
    [175, 38],
    [180, 30],
];

module revolve_profile(pts) {
    // Build stack of frustums between consecutive sample pairs.
    for (i = [0 : len(pts) - 2]) {
        z0 = pts[i][0];   r0 = pts[i][1];
        z1 = pts[i+1][0]; r1 = pts[i+1][1];
        translate([0, 0, z0])
            cylinder(h = z1 - z0, r1 = r0, r2 = r1);
    }
}

ring_od = 51;
dsp_od  = 33;

// ── Body ──────────────────────────────────────────────────────
color("dimgray")
difference() {
    revolve_profile(profile);

    // Speaker radial slots around the bottom bulb
    for (a = [0:24:359])
        rotate([0, 0, a])
            translate([0, 42, 25])
                cube([4, 10, 20], center = true);

    // Display cutout on the head, facing Y−
    translate([0, -50, 155])
        rotate([90, 0, 0])
            cylinder(h = 20, d = dsp_od, center = true);

    // USB-C rear exit near waist bottom
    translate([0, 35, 70])
        rotate([90, 0, 0])
            cylinder(h = 10, d = 10, center = true);
}

// ── LED ring halo on head front ──────────────────────────────
color("royalblue", 0.95)
translate([0, -42.2, 155])
    rotate([90, 0, 0])
        difference() {
            cylinder(h = 1.0, d = ring_od, center = true);
            cylinder(h = 1.4, d = ring_od - 7, center = true);
        }

// ── Display indicative ───────────────────────────────────────
color("black")
translate([0, -42.8, 155])
    rotate([90, 0, 0])
        cylinder(h = 1.6, d = dsp_od, center = true);
