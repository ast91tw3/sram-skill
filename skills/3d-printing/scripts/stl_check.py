"""Printability pre-check for an STL (binary or ASCII). Pure Python, offline, read-only.

Usage: python stl_check.py model.stl [--bed 256 256 256] [--min-wall 0.8]

Checks: bounding box vs build volume, likely unit mistakes, watertightness (every edge shared by
exactly 2 triangles), inverted normals (negative volume), degenerate triangles, thin overall size.
It does NOT detect overhangs, thin internal walls or bad slicing. Always preview in the slicer.
"""
import argparse, struct, sys
from pathlib import Path

MAX_TRIS = 3_000_000


def read_stl(path):
    data = Path(path).read_bytes()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):                     # binary STL has an exact size
            if n > MAX_TRIS:
                sys.exit(f"ERROR: {n} triangles exceeds safety limit {MAX_TRIS}")
            tris = []
            for i in range(n):
                v = struct.unpack_from("<12f", data, 84 + 50 * i)
                tris.append(((v[3], v[4], v[5]), (v[6], v[7], v[8]), (v[9], v[10], v[11])))
            return tris
    tris, cur = [], []                                    # ASCII fallback
    for line in data.decode("utf-8", "replace").splitlines():
        p = line.split()
        if len(p) == 4 and p[0] == "vertex":
            cur.append((float(p[1]), float(p[2]), float(p[3])))
            if len(cur) == 3:
                tris.append(tuple(cur)); cur = []
                if len(tris) > MAX_TRIS:
                    sys.exit("ERROR: too many triangles")
    if not tris:
        sys.exit("ERROR: no triangles found (not a valid STL?)")
    return tris


def analyse(tris, bed, min_wall):
    key = lambda v: (round(v[0], 4), round(v[1], 4), round(v[2], 4))
    xs = [v[0] for t in tris for v in t]; ys = [v[1] for t in tris for v in t]; zs = [v[2] for t in tris for v in t]
    dims = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    edges, degenerate, vol = {}, 0, 0.0
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        ka, kb, kc = key(a), key(b), key(c)
        if len({ka, kb, kc}) < 3:
            degenerate += 1; continue
        for e in ((ka, kb), (kb, kc), (kc, ka)):
            k = tuple(sorted(e)); edges[k] = edges.get(k, 0) + 1
    open_edges = sum(1 for n in edges.values() if n == 1)
    nonman = sum(1 for n in edges.values() if n > 2)
    notes, fails = [], []
    for d, name, lim in zip(dims, "XYZ", bed):
        if d > lim:
            fails.append(f"{name} size {d:.1f} mm exceeds build volume {lim} mm (split the part or rotate it)")
    if max(dims) < 2:
        notes.append("Whole part is under 2 mm: units may be metres or inches. Scale before slicing.")
    if max(dims) > 1000:
        notes.append("Part is over 1 m: units may be micrometres. Check scale.")
    if 20 < max(dims) / max(min(dims), 1e-9) and min(dims) < min_wall:
        notes.append(f"Smallest overall dimension {min(dims):.2f} mm is below the {min_wall} mm wall guideline.")
    if open_edges:
        fails.append(f"{open_edges} open edge(s): mesh is not watertight; repair it before slicing")
    if nonman:
        fails.append(f"{nonman} non-manifold edge(s) shared by more than 2 faces")
    if vol < 0:
        fails.append("Negative volume: normals are inverted (flip normals)")
    if degenerate:
        notes.append(f"{degenerate} degenerate (zero-area) triangle(s)")
    return {"triangles": len(tris), "size_mm": tuple(round(d, 2) for d in dims), "volume_cm3": round(abs(vol) / 1000, 3),
            "open_edges": open_edges, "non_manifold_edges": nonman, "fails": fails, "notes": notes}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file"); ap.add_argument("--bed", nargs=3, type=float, default=[256, 256, 256])
    ap.add_argument("--min-wall", type=float, default=0.8)
    a = ap.parse_args()
    r = analyse(read_stl(a.file), a.bed, a.min_wall)
    print(f"triangles: {r['triangles']}   size (mm): {r['size_mm']}   volume: {r['volume_cm3']} cm3")
    print(f"open edges: {r['open_edges']}   non-manifold edges: {r['non_manifold_edges']}")
    for f in r["fails"]: print("FAIL:", f)
    for n in r["notes"]: print("NOTE:", n)
    print("RESULT:", "NOT READY" if r["fails"] else "no blocking problems found (still preview in the slicer)")
    sys.exit(1 if r["fails"] else 0)


if __name__ == "__main__":
    main()
