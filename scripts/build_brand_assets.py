"""Build every Maestro brand file from one source of the mark's geometry.

The mark is the original two-bolt M joined into one shape. Its outline is the
drawn polygon below grown by a fixed radius, with round outer corners, so the
files hold plain filled paths that every renderer and icon tool reads the same.

Writes:
  docs/assets/brand/            the mark (navy, white, currentColor), the tile
                                avatars, and the two lockups (wordmark kept, mark swapped)
  docs/assets/brand/icons/      icon-192.png, icon-512.png, favicon.ico (16, 32, 48)
  frontend/app/icon.svg         marigold tile, ink mark (the app's favicon)
  frontend/app/apple-icon.png   180, full-bleed and opaque (iOS rounds it itself)
  frontend/components/brand-logo.tsx   the MARK_D constant only
  extension/icons/{16,32,48,128}.png
  mcpb/icon.png                 512, the Claude Desktop bundle icon, only with --with-mcpb

Run from anywhere, safe to re-run:
  backend/.venv/bin/python scripts/build_brand_assets.py [--with-mcpb]

The bundle icon is packed into mcpb/maestro-career-studio.mcpb, whose hash the
registry entry pins, so it changes only at release time: run with --with-mcpb
just before packing the bundle (docs/RELEASING.md). A run without it leaves
mcpb/icon.png alone and says so.
"""
import argparse
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "docs" / "assets" / "brand"

NAVY, WHITE = "#0F172A", "#FFFFFF"
MARIGOLD, ON_MARIGOLD = "#ffb81f", "#1a1300"

WEIGHT = 5.0  # how far the drawn polygon is grown, in 256-box units
TILE = (16, 16, 224, 224, 54)  # x, y, w, h, corner radius in the 256 box
TILE_MARK_SCALE = 0.72


# Geometry ------------------------------------------------------------------

def quad(p0, c, p2, ts=(0.25, 0.5, 0.75)):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p2[1]) for t in ts]


def base_polygon():
    """The joined M on a 256 box, clockwise on screen, curves sampled."""
    pts = [(34, 211), (61, 48)]
    pts += quad((61, 48), (63, 39), (70, 47)) + [(70, 47), (128, 108), (186, 47)]
    pts += quad((186, 47), (193, 39), (195, 48)) + [(195, 48), (222, 211)]
    pts += quad((222, 211), (213, 229), (202, 216)) + [(202, 216), (128, 142), (54, 216)]
    pts += quad((54, 216), (43, 229), (34, 211))
    return pts


def place(pts, scale, cx, cy, ox=128, oy=132):
    """Scale about the mark's own centre (ox, oy) and move that centre to (cx, cy)."""
    return [(cx + scale * (x - ox), cy + scale * (y - oy)) for x, y in pts]


def grow(pts, r):
    """The polygon grown by r, as segments.

    Each item is ("L", point) or ("A", start, end, centre): outer corners get an
    arc of radius r around the original corner, inner corners stay sharp where
    the two grown edges cross.
    """
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (p1[0] - p0[0], p1[1] - p0[1])
        d2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*d1), math.hypot(*d2)
        n1 = (d1[1] / l1, -d1[0] / l1)
        n2 = (d2[1] / l2, -d2[0] / l2)
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        if cross > 1e-9:  # outer corner: round it
            a = (p1[0] + r * n1[0], p1[1] + r * n1[1])
            b = (p1[0] + r * n2[0], p1[1] + r * n2[1])
            out.append(("A", a, b, p1))
        else:  # inner corner: where the two grown edges cross
            k = r / (1 + n1[0] * n2[0] + n1[1] * n2[1])
            out.append(("L", (p1[0] + k * (n1[0] + n2[0]), p1[1] + k * (n1[1] + n2[1]))))
    return out


def num(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def segments_to_d(segs, r):
    d = []
    for seg in segs:
        if seg[0] == "L":
            x, y = seg[1]
            d.append(f"{'M' if not d else 'L'}{num(x)} {num(y)}")
        else:
            (ax, ay), (bx, by) = seg[1], seg[2]
            d.append(f"{'M' if not d else 'L'}{num(ax)} {num(ay)}")
            d.append(f"A{num(r)} {num(r)} 0 0 1 {num(bx)} {num(by)}")
    return " ".join(d) + "Z"


def arc_points(start, end, centre, step=math.radians(3)):
    """Points along a clockwise-on-screen arc, excluding the start point."""
    t0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
    t1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
    sweep = (t1 - t0) % (2 * math.pi)
    r = math.hypot(start[0] - centre[0], start[1] - centre[1])
    k = max(1, math.ceil(sweep / step))
    return [(centre[0] + r * math.cos(t0 + sweep * i / k), centre[1] + r * math.sin(t0 + sweep * i / k))
            for i in range(1, k + 1)]


def segments_to_points(segs):
    pts = []
    for seg in segs:
        if seg[0] == "L":
            pts.append(seg[1])
        else:
            pts.append(seg[1])
            pts += arc_points(seg[1], seg[2], seg[3])
    return pts


def mark_segments(scale=1.0, cx=128, cy=128):
    return grow(place(base_polygon(), scale, cx, cy), WEIGHT * scale)


def mark_d(scale=1.0, cx=128, cy=128):
    return segments_to_d(mark_segments(scale, cx, cy), WEIGHT * scale)


def rounded_rect_d(x, y, w, h, r):
    return (f"M{x + r} {y}H{x + w - r}A{r} {r} 0 0 1 {x + w} {y + r}V{y + h - r}A{r} {r} 0 0 1 {x + w - r} {y + h}"
            f"H{x + r}A{r} {r} 0 0 1 {x} {y + h - r}V{y + r}A{r} {r} 0 0 1 {x + r} {y}Z")


def rounded_rect_points(x, y, w, h, r):
    pts = []
    for (cx, cy), start in (((x + w - r, y + r), (x + w - r, y)), ((x + w - r, y + h - r), (x + w, y + h - r)),
                            ((x + r, y + h - r), (x + r, y + h)), ((x + r, y + r), (x, y + r))):
        pts.append(start)
        end_angle = math.atan2(start[1] - cy, start[0] - cx) + math.pi / 2
        pts += arc_points(start, (cx + r * math.cos(end_angle), cy + r * math.sin(end_angle)), (cx, cy))
    return pts


# SVG -----------------------------------------------------------------------

def svg(body, title, desc, w=256, h=256):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none">\n'
            f"  <title>{title}</title>\n  <desc>{desc}</desc>\n{body}\n</svg>\n")


MARK_GROUP = re.compile(r'(<g id="mark" transform="translate\(([\d.]+) ([\d.]+)\)"[^>]*>)(.*?)(</g>)', re.S)
FIT = re.compile(r'data-fit="([\d.]+) ([\d.]+) ([\d.]+)"')


def lockup_fit(group_open, group_body, fname):
    """Centre and scale for the new mark: read back from data-fit, or measured once from the old two-bolt mark."""
    m = FIT.search(group_open)
    if m:
        return tuple(float(v) for v in m.groups())
    ds = re.findall(r'\bd="([^"]+)"', group_body)
    if not ds or any(re.search(r"[Aa]", d) for d in ds):
        raise SystemExit(f"{fname}: mark group has no data-fit and is not the original two-bolt mark")
    nums = [float(v) for d in ds for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    xs, ys = nums[0::2], nums[1::2]
    cx, cy, height = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(ys) - min(ys)
    scale = height / (229 + 5 - (39 - 5))  # the grown mark is about 200 units tall
    return round(cx, 4), round(cy, 4), round(scale, 4)


def build_lockup(fname, fill):
    path = BRAND / fname
    src = path.read_text()
    m = MARK_GROUP.search(src)
    if not m:
        raise SystemExit(f"{fname}: mark group not found")
    cx, cy, scale = lockup_fit(m.group(1), m.group(4), fname)
    opener = f'<g id="mark" transform="translate({m.group(2)} {m.group(3)})" data-fit="{num(cx)} {num(cy)} {num(scale)}">'
    group = f'{opener}\n    <path d="{mark_d(scale=scale, cx=cx, cy=cy)}" fill="{fill}"/>\n  </g>'
    text = src[:m.start()] + group + src[m.end():]
    text = re.sub(r"<title>.*?</title>", f"<title>Maestro Career Studio lockup, {'light' if fill == NAVY else 'dark'}</title>", text, count=1, flags=re.S)
    text = re.sub(r"<desc>.*?</desc>", "<desc>One-colour joined M mark with the Inter-based wordmark and tagline.</desc>",
                  text, count=1, flags=re.S)
    text = re.sub(r"\n\s*<!-- Palette tokens.*?-->\n", "\n", text, count=1, flags=re.S)
    path.write_text(text)
    return path, (cx, cy, scale)


def write(path, text, wrote):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    wrote.append(path)


def build_svgs(wrote):
    name = "Maestro Career Studio"
    one = "One-colour M: the two bolts of the original mark joined into a single shape."
    full = mark_d()
    for fname, fill in (("maestro_mark_navy.svg", NAVY), ("maestro_mark_white.svg", WHITE)):
        write(BRAND / fname, svg(f'  <path d="{full}" fill="{fill}"/>', f"{name} mark", one), wrote)
    write(BRAND / "maestro_mark.svg",
          svg(f'  <path d="{full}" fill="currentColor"/>', f"{name} mark", one + " Takes the text colour."), wrote)

    tile = rounded_rect_d(*TILE)
    inner = mark_d(scale=TILE_MARK_SCALE)
    small = "The joined M cut out of a rounded tile, for 32 px and below."
    write(BRAND / "maestro_avatar_primary.svg", svg(
        f'  <path fill-rule="evenodd" clip-rule="evenodd" d="{tile} {inner}" fill="{NAVY}"/>', f"{name} avatar", small), wrote)
    write(BRAND / "maestro_avatar_light.svg", svg(
        f'  <path d="{tile}" fill="{WHITE}"/>\n  <path d="{inner}" fill="{NAVY}"/>',
        f"{name} avatar, light", "The joined M in navy on a white rounded tile."), wrote)
    write(BRAND / "maestro_mark_small.svg", svg(
        f'  <path d="{tile}" fill="{NAVY}"/>\n  <path d="{inner}" fill="{WHITE}"/>',
        f"{name} small-size mark", small + " Solid white M, for use on any background."), wrote)
    write(ROOT / "frontend" / "app" / "icon.svg", svg(
        f'  <path d="{tile}" fill="{MARIGOLD}"/>\n  <path d="{inner}" fill="{ON_MARIGOLD}"/>',
        f"{name} icon", "The joined M in ink on a marigold rounded tile."), wrote)

    fits = {}
    for fname, fill in (("maestro_lockup_light.svg", NAVY), ("maestro_lockup_dark.svg", WHITE)):
        path, fits[fname] = build_lockup(fname, fill)
        wrote.append(path)
    return fits["maestro_lockup_light.svg"]


def update_brand_logo(fit, wrote):
    """Keep the app's inline mark equal to the lockup's mark (same centre and scale, same group translate)."""
    path = ROOT / "frontend" / "components" / "brand-logo.tsx"
    src = path.read_text()
    cx, cy, scale = fit
    new, count = re.subn(r'const MARK_D =\n  "[^"]*";', f'const MARK_D =\n  "{mark_d(scale=scale, cx=cx, cy=cy)}";', src)
    if count != 1:
        raise SystemExit(f"{path}: MARK_D constant not found")
    if new != src:
        path.write_text(new)
    wrote.append(path)


# Raster --------------------------------------------------------------------

def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def render_icon(size, full_bleed=False):
    """The marigold tile with the ink mark at `size` px.

    Shapes are drawn as coverage masks at 8x or more and box-averaged down,
    which is exact area coverage, so edges are clean at every size. Outside the
    tile's rounded corners is transparent; full_bleed fills the whole square
    and returns an opaque RGB image.
    """
    ss = max(8, math.ceil(2048 / size))
    big = size * ss
    k = big / 256

    def mask(points):
        m = Image.new("L", (big, big), 0)
        ImageDraw.Draw(m).polygon([(x * k, y * k) for x, y in points], fill=255)
        return m.reduce(ss)

    mark = mask(segments_to_points(mark_segments(scale=TILE_MARK_SCALE)))
    img = Image.composite(Image.new("RGB", (size, size), hex_rgb(ON_MARIGOLD)),
                          Image.new("RGB", (size, size), hex_rgb(MARIGOLD)), mark)
    if full_bleed:
        return img
    img.putalpha(mask(rounded_rect_points(*TILE)))
    return img


def build_rasters(wrote, with_mcpb=False):
    pngs = [
        (ROOT / "frontend" / "app" / "apple-icon.png", 180, True),
        (ROOT / "extension" / "icons" / "16.png", 16, False),
        (ROOT / "extension" / "icons" / "32.png", 32, False),
        (ROOT / "extension" / "icons" / "48.png", 48, False),
        (ROOT / "extension" / "icons" / "128.png", 128, False),
        (BRAND / "icons" / "icon-192.png", 192, False),
        (BRAND / "icons" / "icon-512.png", 512, False),
    ]
    if with_mcpb:
        pngs.append((ROOT / "mcpb" / "icon.png", 512, False))
    for path, size, full_bleed in pngs:
        path.parent.mkdir(parents=True, exist_ok=True)
        render_icon(size, full_bleed).save(path, optimize=True)
        wrote.append(path)
    ico = BRAND / "icons" / "favicon.ico"
    frames = [render_icon(s) for s in (16, 32, 48)]
    frames[-1].save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[:-1])
    wrote.append(ico)


def main():
    parser = argparse.ArgumentParser(description="Build every Maestro brand file from the mark's geometry.")
    parser.add_argument("--with-mcpb", action="store_true",
                        help="also write mcpb/icon.png (a release step: re-pack the bundle after)")
    args = parser.parse_args()
    wrote = []
    fit = build_svgs(wrote)
    update_brand_logo(fit, wrote)
    build_rasters(wrote, with_mcpb=args.with_mcpb)
    for p in wrote:
        print("wrote", p.relative_to(ROOT), f"({p.stat().st_size} bytes)")
    if not args.with_mcpb:
        print("left mcpb/icon.png alone: run with --with-mcpb before packing the bundle for a release")


if __name__ == "__main__":
    main()
