#!/usr/bin/env python3
"""Render the language cards in README.md: a segmented bar, a two column legend
and a small eyebrow label instead of a title, in the pink palette of the other
cards.

The animations are plain SVG (SMIL and CSS keyframes), which GitHub renders
inside <img>: the bar grows and the legend fades in once per page load, the
background drifts between pink and lilac in a slow loop.
"""
from __future__ import annotations

from html import escape
from itertools import accumulate

WIDTH, PAD = 300, 25
BAR_Y, BAR_H, BAR_RADIUS, BAR_GAP = 55, 8, 4, 2
ROW_H, COLS = 25, 2
LEGEND_TOP = BAR_Y + BAR_H + 28
EYEBROW_Y = 36
MAX_LANGS = 12
# Fixed height: the two cards share one README row, so they must match even
# when one of them lists fewer languages.
HEIGHT = BAR_Y + BAR_H + 22 + (MAX_LANGS // COLS) * ROW_H

GROW_S = 1.1          # the bar grows in once
FADE_S = 0.5          # each legend entry fades in once...
FADE_DELAY_S = 0.35   # ...starting while the bar is still growing...
FADE_STEP_S = 0.06    # ...one after the other
BREATHE_S = 9         # background pink -> lilac -> pink, looping

PINK = ("#ffc2e0", "#ff9ecd")
LILAC = ("#e6c3ff", "#c9a0ff")
TEXT_COLOR = "#5c1046"
FONT = "'Segoe UI', Ubuntu, Sans-Serif"

# One palette per README theme. GitHub serves the matching file through
# <picture>, so each card is rendered twice rather than carrying a media query.
PALETTES = {
    "light": {"base": PINK, "drift": LILAC, "text": TEXT_COLOR},
    "dark": {"base": ("#2b1622", "#4a1f38"), "drift": ("#33203f", "#5a2a6b"), "text": "#ffd6ea"},
}
THEMES = tuple(PALETTES)

# Languages that are noise on a profile card: markup and data, not code.
HIDE = {"HTML", "CSS", "CMake", "Less", "Jupyter Notebook", "Markdown", "Text",
        "JSON", "YAML"}

# github-linguist colors, only for the languages this account actually uses;
# anything else falls back to a neutral grey.
COLORS = {
    "C": "#555555", "C++": "#f34b7d", "C#": "#178600", "Swift": "#F05138",
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Go": "#00ADD8", "Rust": "#dea584", "Ruby": "#701516", "Java": "#b07219",
    "Kotlin": "#A97BFF", "Objective-C": "#438eff", "Shell": "#89e051",
    "GDScript": "#355570", "Solidity": "#AA6746", "Lua": "#000080", "SQL": "#e38c00",
    "PHP": "#4F5D95", "Dart": "#00B4AB", "Vue": "#41b883", "SCSS": "#c6538c",
    "YAML": "#cb171e", "JSON": "#292929", "Elixir": "#6e4a7e", "Haskell": "#5e5086",
}
FALLBACK_COLOR = "#8b949e"


def rank(sizes: dict[str, float], counts: dict[str, int] | None = None,
         size_weight: float = 1.0, count_weight: float = 0.0) -> list[tuple[str, float]]:
    """Languages ordered by size^size_weight * count^count_weight, largest first.

    Same formula as the public language cards: a count weight above zero favours
    languages spread over many repositories over one huge repository.
    """
    scores = {
        lang: size ** size_weight * (counts or {}).get(lang, 1) ** count_weight
        for lang, size in sizes.items() if size > 0
    }
    return sorted(scores.items(), key=lambda kv: -kv[1])


def render(langs: list[tuple[str, float]], label: str, theme: str = "light") -> str:
    """The card as SVG text. `langs` is ranked, at most MAX_LANGS entries."""
    if theme not in PALETTES:
        raise ValueError(f"unknown theme {theme!r}, expected one of {THEMES}")
    palette = PALETTES[theme]
    if not langs:
        raise ValueError("no languages to render")
    if len(langs) > MAX_LANGS:
        raise ValueError(f"at most {MAX_LANGS} languages fit on the card, got {len(langs)}")
    total = sum(value for _, value in langs)
    if total <= 0:
        raise ValueError("language sizes must add up to a positive total")

    inner = WIDTH - 2 * PAD
    return f"""<svg width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" \
xmlns="http://www.w3.org/2000/svg">
  <defs>
    {breathing_gradient(palette)}
    <clipPath id="bar">
      <rect x="{PAD}" y="{BAR_Y}" width="0" height="{BAR_H}" rx="{BAR_RADIUS}">
        <animate attributeName="width" from="0" to="{inner}" dur="{GROW_S}s" fill="freeze"
                 calcMode="spline" keyTimes="0;1" keySplines=".2 .8 .2 1" />
      </rect>
    </clipPath>
  </defs>
  <style>
    .eyebrow {{ font: 700 10px {FONT}; letter-spacing: 1.6px; fill: {palette["text"]}; opacity: .55; }}
    .lang {{ font: 400 12px {FONT}; fill: {palette["text"]}; }}
    .entry {{ opacity: 0; animation: fade-in {FADE_S}s ease-out forwards; }}
    @keyframes fade-in {{ to {{ opacity: 1; }} }}
  </style>
  <rect width="{WIDTH}" height="{HEIGHT}" rx="4.5" fill="url(#bg)" />
  <text x="{PAD}" y="{EYEBROW_Y}" class="eyebrow">{escape(label)}</text>
  <g clip-path="url(#bar)">{''.join(_segments(langs, total, inner))}</g>
  {''.join(_entries(langs, total, inner))}
</svg>
"""


def breathing_gradient(palette: dict, gradient_id: str = "bg") -> str:
    """The looping background gradient, shared by every card in README.md."""
    return (f'<linearGradient id="{gradient_id}">'
            f'{_breathing_stop("0%", palette["base"][0], palette["drift"][0])}'
            f'{_breathing_stop("100%", palette["base"][1], palette["drift"][1])}'
            f'</linearGradient>')


def _breathing_stop(offset: str, base: str, drift: str) -> str:
    return (f'<stop offset="{offset}" stop-color="{base}">'
            f'<animate attributeName="stop-color" values="{base};{drift};{base}" '
            f'dur="{BREATHE_S}s" repeatCount="indefinite" /></stop>')


def _segments(langs: list[tuple[str, float]], total: float, inner: float) -> list[str]:
    usable = inner - BAR_GAP * (len(langs) - 1)
    widths = [max(usable * value / total, 1.0) for _, value in langs]
    starts = list(accumulate([PAD, *(w + BAR_GAP for w in widths[:-1])]))
    return [
        f'<rect x="{x:.2f}" y="{BAR_Y}" width="{w:.2f}" height="{BAR_H}" fill="{_color(name)}" />'
        for (name, _), x, w in zip(langs, starts, widths)
    ]


def _entries(langs: list[tuple[str, float]], total: float, inner: float) -> list[str]:
    return [_entry(i, name, 100 * value / total, inner) for i, (name, value) in enumerate(langs)]


def _entry(index: int, name: str, pct: float, inner: float) -> str:
    col, row = index % COLS, index // COLS
    cx = PAD + col * (inner / COLS)
    cy = LEGEND_TOP + row * ROW_H
    delay = FADE_DELAY_S + index * FADE_STEP_S
    return (f'<g class="entry" style="animation-delay:{delay:.2f}s">'
            f'<circle cx="{cx + 5:.1f}" cy="{cy - 4:.1f}" r="5" fill="{_color(name)}" />'
            f'<text x="{cx + 16:.1f}" y="{cy:.1f}" class="lang">{escape(name)} {pct:.2f}%</text>'
            f'</g>')


def _color(name: str) -> str:
    return COLORS.get(name, FALLBACK_COLOR)
