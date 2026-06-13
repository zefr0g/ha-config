"""
Axolotl night-light shell.

Scope (simplified):
  - hollow body, ~2mm uniform walls
  - bottom opening + 4 M3 screw bosses
  - matching base plate with through-holes
  - 100mm total height
  - no IR / USB-C cutouts (user will cut those manually)

Run:
  python3 build.py
"""

import argparse
from pathlib import Path
import numpy as np
import trimesh

HERE = Path(__file__).parent
OUT = HERE / 'output'
OUT.mkdir(exist_ok=True)
SRC_STL = Path('/home/dd/Téléchargements/cute_axolotl.stl')

# ------- parameters (mm) -------
TARGET_HEIGHT  = 100.0
WALL           = 2.5
VOXEL_PITCH    = 0.8        # 3 cells of erosion ≈ 2.4mm wall (close enough)
DECIMATE_INNER = 8000   # inner cavity can be very coarse — invisible
# (no final decimation — outer surface stays at source resolution)

# Bottom opening (rectangle in XY) — centered at (0, OPEN_Y_OFFSET) so it
# stays in the main torso, clear of the front legs
OPEN_W         = 42.0
OPEN_D         = 38.0
OPEN_Y_OFFSET  = 8.0    # shift opening toward back (+Y) to avoid legs

# Screw bosses (4 corners of the opening)
BOSS_OD        = 7.0
BOSS_ID        = 2.6        # M3 self-tap pilot
BOSS_H         = 10.0       # rises this far above z=0 into the cavity
BOSS_INSET     = 5.0        # how far inside the opening edge each boss sits
SCREW_HEAD_D   = 6.0        # countersink diameter on base plate
SCREW_HEAD_H   = 2.0
BASE_THICKNESS = 3.0
BASE_LIP_TOL   = 0.4        # clearance for base plate to drop into opening

# IR receiver window — clean rectangular hole on chest (-Y face)
# Sized for a typical TSOP/VS1838 module (~10mm wide × 5mm tall with PCB)
IR_W           = 5.0
IR_H           = 5.0
IR_Z           = 25.0       # height above floor
IR_FRONT_Y     = -30.0      # approx y of body front at z=25 (negative = front)

# USB-C cable slot — through +Y tail at low Z, opens out the back-bottom
USB_W          = 12.0       # cable width clearance
USB_H          = 6.0        # cable height clearance (allows passing connector)
USB_Z          = 6.0        # center height (low so cable lays flat)
USB_BACK_Y     = 50.0       # approx y of tail back
# -------------------------------


def render(mesh_list, path, title=''):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(14, 10))
    views = [('Front (-Y)', 0, -90), ('Side (+X)', 0, 0), ('Top', 90, -90), ('Iso', 25, -60)]
    allv = np.concatenate([m.vertices for m, *_ in mesh_list])
    lo, hi = allv.min(0), allv.max(0); ext = hi - lo
    for i, (name, elev, azim) in enumerate(views):
        ax = fig.add_subplot(2, 2, i+1, projection='3d')
        for m, color, alpha in mesh_list:
            mm = m
            if len(m.faces) > 12000:
                mm = m.simplify_quadric_decimation(percent=1.0 - 12000/len(m.faces))
            coll = Poly3DCollection(mm.vertices[mm.faces], alpha=alpha, facecolor=color, edgecolor='none')
            ax.add_collection3d(coll)
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
        ax.set_box_aspect((ext[0], ext[1], ext[2]))
        ax.view_init(elev=elev, azim=azim); ax.set_title(name)
    plt.suptitle(title); plt.tight_layout()
    plt.savefig(path, dpi=85, bbox_inches='tight'); plt.close()
    print(f"  → {path.name}", flush=True)


def ensure_volume(m, name=''):
    if not m.is_volume:
        trimesh.repair.fill_holes(m); trimesh.repair.fix_normals(m); m.process(validate=True)
    if not m.is_volume:
        # keep only largest connected component, then repair again
        parts = m.split(only_watertight=False)
        main = max(parts, key=lambda p: len(p.faces))
        trimesh.repair.fill_holes(main); trimesh.repair.fix_normals(main)
        m = main
    if not m.is_volume:
        print(f"  ⚠ {name} not a volume", flush=True)
    return m


def step1_load():
    print("[1] Load + scale + repair", flush=True)
    m = trimesh.load(str(SRC_STL))
    print(f"  loaded {len(m.faces)} faces", flush=True)
    scale = TARGET_HEIGHT / m.extents[2]
    m.apply_scale(scale)
    m.apply_translation([-(m.bounds[0,0]+m.bounds[1,0])/2,
                         -(m.bounds[0,1]+m.bounds[1,1])/2,
                         -m.bounds[0,2]])
    m = ensure_volume(m, 'outer')
    print(f"  extents={m.extents}", flush=True)
    return m


def step2_inner(outer):
    print(f"[2] Voxel-shell inner (pitch={VOXEL_PITCH}, wall~{WALL}mm)", flush=True)
    from scipy.ndimage import binary_erosion
    vox = outer.voxelized(pitch=VOXEL_PITCH).fill()
    print(f"  voxel grid: {vox.matrix.shape}", flush=True)
    iters = max(1, int(round(WALL / VOXEL_PITCH)))
    inner_mat = binary_erosion(vox.matrix, iterations=iters)
    inner = trimesh.voxel.VoxelGrid(inner_mat, transform=vox.transform)
    inner_mesh = inner.marching_cubes
    print(f"  inner (index-space): {len(inner_mesh.faces)} faces, bounds={inner_mesh.bounds}", flush=True)
    # marching_cubes returns index-space coords; manually apply the voxel transform
    inner_mesh.apply_transform(vox.transform)
    print(f"  inner (world-space): bounds={inner_mesh.bounds}", flush=True)
    # Sanity: inner should be inside outer
    if (inner_mesh.bounds[0] < outer.bounds[0] - 0.5).any() or \
       (inner_mesh.bounds[1] > outer.bounds[1] + 0.5).any():
        print(f"  ⚠ inner exceeds outer bounds — alignment failed", flush=True)
    # decimate inner heavily — it's hidden inside the shell
    if len(inner_mesh.faces) > DECIMATE_INNER:
        inner_mesh = inner_mesh.simplify_quadric_decimation(percent=1.0 - DECIMATE_INNER/len(inner_mesh.faces))
        print(f"  inner decimated to {len(inner_mesh.faces)} faces", flush=True)
    inner_mesh = ensure_volume(inner_mesh, 'inner')
    return inner_mesh


def step3_bosses():
    """4 cylindrical screw bosses at the corners of the bottom opening,
    each with a pilot hole for an M3 self-tap screw.
    Returns (boss_solids, boss_pilots) — both to be unioned/subtracted later.
    """
    print("[3] Build screw bosses", flush=True)
    bosses, pilots = [], []
    bx = OPEN_W/2 - BOSS_INSET
    by = OPEN_D/2 - BOSS_INSET
    for sx in [-1, 1]:
        for sy in [-1, 1]:
            x, y = sx*bx, sy*by + OPEN_Y_OFFSET
            boss = trimesh.creation.cylinder(radius=BOSS_OD/2, height=BOSS_H, sections=24)
            boss.apply_translation([x, y, BOSS_H/2])
            bosses.append(boss)
            pilot = trimesh.creation.cylinder(radius=BOSS_ID/2, height=BOSS_H + 1, sections=16)
            pilot.apply_translation([x, y, (BOSS_H + 1)/2])
            pilots.append(pilot)
    bosses_solid = trimesh.boolean.union(bosses)
    pilots_solid = trimesh.boolean.union(pilots)
    return bosses_solid, pilots_solid


def step4_shell(outer, inner, bosses, pilots):
    print("[4] Boolean: shell = outer − inner − bottom_box, then + bosses − pilots", flush=True)
    shell = trimesh.boolean.difference([outer, inner])
    print(f"  outer−inner: {len(shell.faces)} faces, vol={shell.is_volume}", flush=True)

    # Cut bottom opening (a box that extends just above z=0)
    bottom = trimesh.creation.box(extents=[OPEN_W, OPEN_D, 4.0])
    bottom.apply_translation([0, OPEN_Y_OFFSET, 2.0])
    shell = trimesh.boolean.difference([shell, bottom])
    print(f"  after bottom cut: {len(shell.faces)} faces, vol={shell.is_volume}", flush=True)

    # Union the screw bosses
    shell = trimesh.boolean.union([shell, bosses])
    print(f"  + bosses: {len(shell.faces)} faces, vol={shell.is_volume}", flush=True)

    # Subtract the pilot holes
    shell = trimesh.boolean.difference([shell, pilots])
    print(f"  − pilots: {len(shell.faces)} faces, vol={shell.is_volume}", flush=True)

    # IR window — a clean rectangular hole through the chest (-Y face)
    # box centered, length 30mm in Y so it pierces through the wall
    ir = trimesh.creation.box(extents=[IR_W, 30.0, IR_H])
    ir.apply_translation([0, IR_FRONT_Y, IR_Z])
    shell = trimesh.boolean.difference([shell, ir])
    print(f"  − IR window: {len(shell.faces)} faces, vol={shell.is_volume}", flush=True)

    # USB-C slot — pierces +Y tail, also opens downward through floor for cable exit
    usb = trimesh.creation.box(extents=[USB_W, 40.0, USB_H])
    usb.apply_translation([0, USB_BACK_Y, USB_Z])
    shell = trimesh.boolean.difference([shell, usb])
    print(f"  − USB tail slot: {len(shell.faces)} faces, vol={shell.is_volume}", flush=True)
    # bottom channel under the slot so the cable can exit downward
    channel = trimesh.creation.box(extents=[USB_W, 40.0, USB_Z + 1])
    channel.apply_translation([0, USB_BACK_Y, (USB_Z + 1)/2])
    shell = trimesh.boolean.difference([shell, channel])
    print(f"  − cable channel: {len(shell.faces)} faces, vol={shell.is_volume}", flush=True)

    return shell


def step5_baseplate():
    """Flat plate that drops into the bottom opening, with 4 countersunk through-holes."""
    print("[5] Build base plate", flush=True)
    w = OPEN_W - BASE_LIP_TOL
    d = OPEN_D - BASE_LIP_TOL
    plate = trimesh.creation.box(extents=[w, d, BASE_THICKNESS])
    plate.apply_translation([0, OPEN_Y_OFFSET, BASE_THICKNESS/2])

    bx = OPEN_W/2 - BOSS_INSET
    by = OPEN_D/2 - BOSS_INSET
    cutters = []
    for sx in [-1, 1]:
        for sy in [-1, 1]:
            x, y = sx*bx, sy*by + OPEN_Y_OFFSET
            # through-hole for M3 shank
            thru = trimesh.creation.cylinder(radius=1.7, height=BASE_THICKNESS + 1, sections=24)
            thru.apply_translation([x, y, (BASE_THICKNESS + 1)/2])
            cutters.append(thru)
            # countersink for M3 head (top of plate = +Z)
            csk = trimesh.creation.cylinder(radius=SCREW_HEAD_D/2, height=SCREW_HEAD_H + 0.5, sections=24)
            csk.apply_translation([x, y, BASE_THICKNESS - SCREW_HEAD_H/2 + 0.25])
            cutters.append(csk)
    all_cuts = trimesh.boolean.union(cutters)
    base = trimesh.boolean.difference([plate, all_cuts])
    print(f"  base plate: {len(base.faces)} faces", flush=True)
    return base


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--no-render', action='store_true')
    args = p.parse_args()

    outer = step1_load()
    inner = step2_inner(outer)
    if not args.no_render:
        render([(outer, '#f5a3c7', 0.25), (inner, '#88aaff', 0.85)],
               OUT / '02_inner.png', 'Inner shell (blue) inside outer (pink)')

    bosses, pilots = step3_bosses()

    shell = step4_shell(outer, inner, bosses, pilots)
    # remove any tiny artifacts
    parts = shell.split(only_watertight=False)
    shell = max(parts, key=lambda p: len(p.faces))
    trimesh.repair.fill_holes(shell); trimesh.repair.fix_normals(shell)
    print(f"  final shell: {len(shell.faces)} faces (no decimation — outer detail preserved)", flush=True)
    shell.export(OUT / '04_shell.stl')
    if not args.no_render:
        render([(shell, '#f5a3c7', 0.95)], OUT / '04_shell.png', 'Final shell')

    base = step5_baseplate()
    base.export(OUT / '05_base.stl')
    if not args.no_render:
        render([(shell, '#f5a3c7', 0.55), (base, '#aaccff', 0.95)],
               OUT / '05_assembly.png', 'Shell + base plate')

    print("\n✓ Done. STLs in", OUT, flush=True)


if __name__ == '__main__':
    main()
