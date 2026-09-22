"""Cut the Pink Diamond artwork into the transparent brand assets the site uses.

Source: the master "Pink Diamond" key art (pear gem over a magenta wordmark on a
dark brick backdrop). Everything in brand/ is generated from it, so re-run this
after replacing SOURCE:

    python scripts/build-brand.py "path/to/artwork.png"

Two colour builds come out of each cut:
  *.png      the artwork as-is, for the dark facets
  *-ink.png  a luminance re-map into deep magenta, so the mark still reads on
             the porcelain / candlelight / coral-dusk facets
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _logolib import close, feather, fill_holes, largest_blob, open_, reconstruct, trim

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "brand"
DEFAULT_SOURCE = (
    Path.home() / "OneDrive" / "Desktop" / "\U0001d53b\U0001d55a\U0001d552\U0001d55e\U0001d560\U0001d55f\U0001d555"
    / "Pink" / "ChatGPT Image Aug 9, 2026, 11_44_06 AM.png"
)

# Luminance -> colour ramp used for the light-facet build.
INK_RAMP = [(0.0, (34, 10, 28)), (0.40, (110, 24, 90)), (0.75, (196, 48, 152)), (1.0, (255, 140, 205))]


def cut_gem(rgb: np.ndarray, lum: np.ndarray) -> np.ndarray:
    band = np.zeros(lum.shape, bool)
    band[130:650, 580:965] = True
    m = fill_holes(reconstruct((lum > 246) & band, (lum > 190) & band))
    m = largest_blob(m, (300, 500, 720, 830))
    m = open_(fill_holes(close(m, 14)), 4)
    alpha = np.clip((feather(m, 1.6) - 0.30) / 0.55, 0, 1)
    return trim(np.dstack([rgb, alpha * 255]).astype(np.uint8), pad=2)


def cut_wordmark(rgb: np.ndarray, lum: np.ndarray) -> np.ndarray:
    band = np.zeros(lum.shape, bool)
    # stop above y=772: below that sits the rule + ornament, which only muddies
    # the mark at header sizes
    band[636:772, 250:1300] = True
    m = open_(fill_holes(close(reconstruct((lum > 242) & band, (lum > 150) & band), 3)), 4)
    m = fill_holes(close(m, 2))
    # the gem's lower glow bleeds over the D and the i — knock the soft haze off
    haze = np.zeros_like(m)
    haze[636:664, 250:1300] = True
    m &= ~(haze & (lum < 205))
    m = fill_holes(close(open_(m, 2), 2))
    alpha = np.clip((feather(m, 1.2) - 0.32) / 0.5, 0, 1)
    return trim(np.dstack([rgb, alpha * 255]).astype(np.uint8), pad=2)


def to_ink(rgba: np.ndarray) -> np.ndarray:
    c = rgba[:, :, :3].astype(np.float32) / 255.0
    lum = (c * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1)
    pos = np.array([s[0] for s in INK_RAMP], np.float32)
    cols = np.array([s[1] for s in INK_RAMP], np.float32)
    out = np.dstack([np.interp(lum, pos, cols[:, i]) for i in range(3)] + [rgba[:, :, 3]])
    return out.astype(np.uint8)


def save(im: Image.Image, path: Path) -> None:
    """Quantize to a 255-colour palette + alpha; the facets keep their detail at
    a third of the truecolour weight."""
    q = im.convert("RGBA").quantize(colors=255, method=Image.FASTOCTREE, dither=Image.Dither.NONE)
    q.save(path, optimize=True)


def img(rgba: np.ndarray) -> Image.Image:
    return Image.fromarray(rgba, "RGBA")


def scaled(im: Image.Image, height: int) -> Image.Image:
    return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)


def lockup(gem: Image.Image, word: Image.Image, height: int) -> Image.Image:
    """Horizontal gem + wordmark, optically centred on the wordmark's midline."""
    g = scaled(gem, height)
    w = scaled(word, round(height * 0.52))
    gap = round(height * 0.16)
    canvas = Image.new("RGBA", (g.width + gap + w.width, height), (0, 0, 0, 0))
    canvas.alpha_composite(g, (0, 0))
    canvas.alpha_composite(w, (g.width + gap, (height - w.height) // 2))
    return canvas


def icon(gem: Image.Image, size: int, background=None) -> Image.Image:
    pad = round(size * 0.08)
    g = scaled(gem, size - 2 * pad)
    base = Image.new("RGBA", (size, size), background or (0, 0, 0, 0))
    base.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2))
    return base


def social_card(source: Image.Image, width=1200, height=630) -> Image.Image:
    """Centre-weighted crop of the original key art for og:image."""
    scale = max(width / source.width, height / source.height)
    s = source.resize((round(source.width * scale), round(source.height * scale)), Image.LANCZOS)
    left = (s.width - width) // 2
    top = round((s.height - height) * 0.42)
    return s.crop((left, top, left + width, top + height)).convert("RGB")


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    art = Image.open(source).convert("RGB")
    rgb = np.asarray(art).astype(np.float32)
    lum = rgb.max(axis=2)

    gem_rgba, word_rgba = cut_gem(rgb, lum), cut_wordmark(rgb, lum)
    OUT.mkdir(exist_ok=True)

    for suffix, conv in (("", lambda x: x), ("-ink", to_ink)):
        gem, word = img(conv(gem_rgba)), img(conv(word_rgba))
        save(scaled(gem, 512), OUT / f"pd-gem{suffix}.png")
        save(scaled(word, 224), OUT / f"pd-wordmark{suffix}.png")
        save(lockup(gem, word, 224), OUT / f"pd-lockup{suffix}.png")

    gem = img(gem_rgba)
    save(icon(gem, 32), OUT / "icon-32.png")
    save(icon(gem, 192), OUT / "icon-192.png")
    save(icon(gem, 180, background=(15, 5, 20, 255)), OUT / "apple-touch-icon.png")
    social_card(art).save(OUT / "pd-og.jpg", quality=88, optimize=True)

    for f in sorted(OUT.iterdir()):
        with Image.open(f) as i:
            print(f"{f.name:24s} {i.size[0]:5d}x{i.size[1]:<5d} {f.stat().st_size/1024:7.1f} KB")


if __name__ == "__main__":
    main()
