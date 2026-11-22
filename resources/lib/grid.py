# -*- coding: utf-8 -*-
"""Layout and remote-control movement for the full-screen camera grid.

No Kodi imports here, so this file can be tested on any computer.
"""

MAX_TILES = 9


def grid_shape(n):
    """(columns, rows) for n cameras: 1 -> 1x1, 2 -> 2x1, 3-4 -> 2x2, 5-9 -> 3x3."""
    if n <= 1:
        return 1, 1
    if n == 2:
        return 2, 1
    if n <= 4:
        return 2, 2
    return 3, 3


def tile_rects(n, width, height, gap=0):
    """(x, y, w, h) for each of the first n tiles, left to right, top to bottom."""
    n = max(0, min(n, MAX_TILES))
    cols, rows = grid_shape(n)
    tile_w = (width - gap * (cols - 1)) // cols
    tile_h = (height - gap * (rows - 1)) // rows
    rects = []
    for i in range(n):
        col, row = i % cols, i // cols
        rects.append((col * (tile_w + gap), row * (tile_h + gap), tile_w, tile_h))
    return rects


def move(index, direction, n):
    """The tile index after pressing an arrow key ("left", "right", "up", "down").

    Stays put at the edges. Moving down into an empty spot of a part-filled
    last row (e.g. 3 cameras in a 2x2 grid) lands on the last tile instead.
    """
    if n <= 1:
        return 0
    cols, _ = grid_shape(n)
    col, row = index % cols, index // cols
    last_row = (n - 1) // cols
    if direction == "left" and col > 0:
        return index - 1
    if direction == "right" and col < cols - 1 and index + 1 < n:
        return index + 1
    if direction == "up" and row > 0:
        return index - cols
    if direction == "down" and row < last_row:
        return min(index + cols, n - 1)
    return index
