"""Draw the big pointer (media/cursor.png): a yellow arrow with a thick black outline.

128x128 is the largest custom cursor Chrome-based browsers accept. Pure Python so it runs anywhere.
Usage: python3 tools/make_cursor.py
"""
import math
import os
import struct
import zlib

SIZE = 128
FILL = (255, 212, 0)
EDGE = (0, 0, 0)
OUTLINE = 7.0  # pixels
SAMPLES = 4    # supersampling per axis, for smooth edges

# Classic arrow shape in 0..1 units; tip at the top-left (the click point).
SHAPE = [(0.06, 0.04), (0.06, 0.80), (0.26, 0.63), (0.40, 0.95), (0.55, 0.89), (0.41, 0.58), (0.68, 0.58)]
POLY = [(x * SIZE, y * SIZE) for x, y in SHAPE]


def inside(px, py):
    hit = False
    j = len(POLY) - 1
    for i in range(len(POLY)):
        xi, yi = POLY[i]
        xj, yj = POLY[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def edge_distance(px, py):
    best = 1e9
    for i in range(len(POLY)):
        ax, ay = POLY[i]
        bx, by = POLY[(i + 1) % len(POLY)]
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return best


def pixel(x, y):
    r = g = b = a = 0.0
    n = SAMPLES * SAMPLES
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            px, py = x + (sx + 0.5) / SAMPLES, y + (sy + 0.5) / SAMPLES
            d = edge_distance(px, py)
            if inside(px, py) and d > OUTLINE / 2:
                col = FILL
            elif d <= OUTLINE / 2 or inside(px, py):
                col = EDGE
            else:
                continue
            r, g, b, a = r + col[0], g + col[1], b + col[2], a + 1
    if a == 0:
        return (0, 0, 0, 0)
    return (int(r / a), int(g / a), int(b / a), int(255 * a / n))


def png(width, height, rows):
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    rows = [[pixel(x, y) for x in range(SIZE)] for y in range(SIZE)]
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "cursor.png")
    with open(out, "wb") as f:
        f.write(png(SIZE, SIZE, rows))
    print(out)
