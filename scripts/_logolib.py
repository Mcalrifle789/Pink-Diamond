"""Shared helpers for cutting the Pink Diamond artwork into transparent assets."""
import numpy as np
from PIL import Image, ImageFilter


def dilate(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def reconstruct(marker: np.ndarray, mask: np.ndarray, iters: int = 4000) -> np.ndarray:
    """Morphological reconstruction: grow marker while staying inside mask."""
    cur = marker & mask
    for _ in range(iters):
        nxt = dilate(cur) & mask
        if np.array_equal(nxt, cur):
            break
        cur = nxt
    return cur


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Flood the background in from the border, everything unreached is a hole."""
    free = ~mask
    seed = np.zeros_like(free)
    seed[0, :] = free[0, :]
    seed[-1, :] = free[-1, :]
    seed[:, 0] = free[:, 0]
    seed[:, -1] = free[:, -1]
    outside = reconstruct(seed, free)
    return ~outside


def feather(mask: np.ndarray, radius: float) -> np.ndarray:
    a = Image.fromarray((mask * 255).astype(np.uint8), "L")
    a = a.filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(a).astype(np.float32) / 255.0


def trim(rgba: np.ndarray, pad: int = 0, thresh: int = 4) -> np.ndarray:
    ys, xs = np.nonzero(rgba[:, :, 3] > thresh)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + 1 + pad, rgba.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + 1 + pad, rgba.shape[1])
    return rgba[y0:y1, x0:x1]


def erode(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:, :] &= mask[:-1, :]
    out[:-1, :] &= mask[1:, :]
    out[:, 1:] &= mask[:, :-1]
    out[:, :-1] &= mask[:, 1:]
    return out


def close(mask: np.ndarray, n: int) -> np.ndarray:
    out = mask
    for _ in range(n):
        out = dilate(out)
    for _ in range(n):
        out = erode(out)
    return out


def open_(mask: np.ndarray, n: int) -> np.ndarray:
    out = mask
    for _ in range(n):
        out = erode(out)
    for _ in range(n):
        out = dilate(out)
    return out


def largest_blob(mask: np.ndarray, seed_box) -> np.ndarray:
    """Keep only the component reachable from inside seed_box."""
    y0, y1, x0, x1 = seed_box
    seed = np.zeros_like(mask)
    seed[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    return reconstruct(seed, mask)
