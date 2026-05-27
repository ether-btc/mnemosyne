#!/usr/bin/env python3
"""Tests for Temporal Parser module."""

import sys
import os
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MNEMOSYNE_DATA_DIR", tempfile.mkdtemp())


class TestTemporalParser(unittest.TestCase):
    def test_extract_absolute_date(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("Meeting was on 2026-05-15")
        self.assertIsNotNone(result)
        self.assertEqual(result["event_date"], "2026-05-15")
        self.assertEqual(result["event_date_precision"], "day")

    def test_extract_relative_date(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("I had a meeting yesterday")
        self.assertIsNotNone(result)
        self.assertEqual(result["event_date_precision"], "day")

    def test_extract_day_reference(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("Discussed this last Monday")
        self.assertIsNotNone(result)
        self.assertEqual(result["event_date_precision"], "day")

    def test_extract_interval(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("We deployed 2 days ago")
        self.assertIsNotNone(result)
        self.assertEqual(result["event_date_precision"], "day")

    def test_extract_named_time(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("Had coffee this morning")
        self.assertIsNotNone(result)

    def test_vague_reference(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("recently updated the server")
        self.assertIsNotNone(result)

    def test_no_temporal_reference(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("The database password is hunter2")
        self.assertIsNotNone(result)
        self.assertIsNone(result.get("event_date"))

    def test_parse_nl_date_absolute(self):
        from mnemosyne.core.temporal_parser import parse_nl_date
        result = parse_nl_date("2026-05-15")
        self.assertIsNotNone(result)
        self.assertEqual(result[0].year, 2026)

    def test_parse_nl_date_relative(self):
        from mnemosyne.core.temporal_parser import parse_nl_date
        result = parse_nl_date("yesterday")
        self.assertIsNotNone(result)

    def test_parse_nl_date_invalid(self):
        from mnemosyne.core.temporal_parser import parse_nl_date
        result = parse_nl_date("not a date at all")
        self.assertIsNone(result)

    def test_extract_temporal_tags(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("Last Monday we discussed the API design")
        self.assertIsNotNone(result)
        self.assertIn("temporal_tags", result)
        self.assertGreater(len(result["temporal_tags"]), 0)

    def test_multi_date_extraction(self):
        from mnemosyne.core.temporal_parser import extract_temporal
        result = extract_temporal("Deployed v2 on 2026-01-15 and v3 yesterday")
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
