#!/usr/bin/env python3
"""Render the scoreboard card in README.md: a row of counters in the same pink
palette, background drift and fade-in as the language cards.

The size matches the streak card next to it (495x195), so both halves of that
README row end up the same height.
"""
from __future__ import annotations

from html import escape

from langcard import FADE_DELAY_S, FADE_S, FADE_STEP_S, FONT, PALETTES, THEMES, breathing_gradient

WIDTH, HEIGHT, PAD = 495, 195, 25
EYEBROW_Y = 36
COLS, ROW_H, FIRST_ROW_Y = 2, 46, 84
MAX_STATS = COLS * 3


def render(stats: list[tuple[str, str, int]], label: str, theme: str = "light") -> str:
    """The card as SVG text.

    `stats` is a list of (icon, caption, value), at most MAX_STATS entries, in
    reading order: first row left to right, then the next.
    """
    if theme not in PALETTES:
        raise ValueError(f"unknown theme {theme!r}, expected one of {THEMES}")
    if not stats:
        raise ValueError("no stats to render")
    if len(stats) > MAX_STATS:
        raise ValueError(f"at most {MAX_STATS} counters fit on the card, got {len(stats)}")
    palette = PALETTES[theme]

    return f"""<svg width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" \
xmlns="http://www.w3.org/2000/svg">
  <defs>{breathing_gradient(palette)}</defs>
  <style>
    .eyebrow {{ font: 700 10px {FONT}; letter-spacing: 1.6px; fill: {palette["text"]}; opacity: .55; }}
    .value {{ font: 700 22px {FONT}; fill: {palette["text"]}; }}
    .caption {{ font: 400 11px {FONT}; fill: {palette["text"]}; opacity: .7; }}
    .entry {{ opacity: 0; animation: fade-in {FADE_S}s ease-out forwards; }}
    @keyframes fade-in {{ to {{ opacity: 1; }} }}
  </style>
  <rect width="{WIDTH}" height="{HEIGHT}" rx="4.5" fill="url(#bg)" />
  <text x="{PAD}" y="{EYEBROW_Y}" class="eyebrow">{escape(label)}</text>
  {''.join(_entry(i, *stat) for i, stat in enumerate(stats))}
</svg>
"""


def _entry(index: int, icon: str, caption: str, value: int) -> str:
    col, row = index % COLS, index // COLS
    x = PAD + col * ((WIDTH - 2 * PAD) / COLS)
    y = FIRST_ROW_Y + row * ROW_H
    delay = FADE_DELAY_S + index * FADE_STEP_S
    return (f'<g class="entry" style="animation-delay:{delay:.2f}s">'
            f'<text x="{x:.1f}" y="{y:.1f}" class="value">{escape(icon)} {value:,}</text>'
            f'<text x="{x:.1f}" y="{y + 16:.1f}" class="caption">{escape(caption)}</text>'
            f'</g>')
