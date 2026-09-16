"""Unit tests for the shared language card renderer: python3 -m unittest discover -s .github/scripts"""
from __future__ import annotations

import re
import unittest
from xml.etree import ElementTree

import langcard
from langcard import HEIGHT, MAX_LANGS, WIDTH, rank, render

SAMPLE = [("Python", 4881), ("TypeScript", 3599), ("Go", 770), ("C#", 67)]


def parse(svg: str) -> ElementTree.Element:
    return ElementTree.fromstring(svg)


class RenderTest(unittest.TestCase):
    def test_is_well_formed_svg_with_fixed_size(self):
        root = parse(render(SAMPLE, "TEST"))
        self.assertEqual(root.get("width"), str(WIDTH))
        self.assertEqual(root.get("height"), str(HEIGHT))
        self.assertEqual(root.get("viewBox"), f"0 0 {WIDTH} {HEIGHT}")

    def test_height_does_not_depend_on_language_count(self):
        one = parse(render(SAMPLE[:1], "TEST"))
        full = parse(render([(f"L{i}", 10) for i in range(MAX_LANGS)], "TEST"))
        self.assertEqual(one.get("height"), full.get("height"))

    def test_label_and_legend_text(self):
        svg = render(SAMPLE, "📦 IN MY REPOS")
        self.assertIn(">📦 IN MY REPOS<", svg)
        self.assertIn(">Python 52.39%<", svg)
        self.assertIn(">C# 0.72%<", svg)
        self.assertNotIn("Lines I wrote", svg)

    def test_one_segment_and_one_legend_entry_per_language(self):
        svg = render(SAMPLE, "TEST")
        self.assertEqual(len(re.findall(r'<rect x="[\d.]+" y="55" width="[\d.]+" height="8" fill=', svg)), len(SAMPLE))
        self.assertEqual(svg.count('class="entry"'), len(SAMPLE))

    def test_bar_fits_inside_the_padding(self):
        svg = render(SAMPLE, "TEST")
        rects = re.findall(r'<rect x="([\d.]+)" y="55" width="([\d.]+)" height="8" fill=', svg)
        right_edge = max(float(x) + float(w) for x, w in rects)
        self.assertAlmostEqual(right_edge, WIDTH - langcard.PAD, places=1)

    def test_animations_are_present(self):
        svg = render(SAMPLE, "TEST")
        self.assertIn('attributeName="width" from="0"', svg)
        self.assertIn('attributeName="stop-color"', svg)
        self.assertIn("@keyframes fade-in", svg)
        delays = [float(d) for d in re.findall(r'animation-delay:([\d.]+)s', svg)]
        self.assertEqual(delays, sorted(delays))
        self.assertEqual(len(set(delays)), len(SAMPLE))

    def test_names_are_escaped(self):
        svg = render([("<b>&", 1)], "a<b")
        self.assertIn("&lt;b&gt;&amp; 100.00%", svg)
        self.assertIn(">a&lt;b<", svg)
        parse(svg)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            render([], "TEST")
        with self.assertRaises(ValueError):
            render([("A", 0)], "TEST")
        with self.assertRaises(ValueError):
            render([(f"L{i}", 1) for i in range(MAX_LANGS + 1)], "TEST")


class RankTest(unittest.TestCase):
    def test_size_only_by_default(self):
        self.assertEqual(rank({"A": 1, "B": 3, "C": 2}), [("B", 3), ("C", 2), ("A", 1)])

    def test_count_weight_lifts_widespread_languages(self):
        sizes, counts = {"Big": 1000, "Wide": 900}, {"Big": 1, "Wide": 10}
        self.assertEqual(rank(sizes, counts)[0][0], "Big")
        self.assertEqual(rank(sizes, counts, 1.0, 0.2)[0][0], "Wide")

    def test_zero_sizes_are_dropped(self):
        self.assertEqual(rank({"A": 0, "B": 1}), [("B", 1)])


if __name__ == "__main__":
    unittest.main()
