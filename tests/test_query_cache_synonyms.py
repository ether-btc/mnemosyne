#!/usr/bin/env python3
"""Tests for Query Cache and Synonyms modules."""

import sys
import os
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MNEMOSYNE_DATA_DIR", tempfile.mkdtemp())


class TestSynonyms(unittest.TestCase):
    def test_expand_query(self):
        from mnemosyne.core.synonyms import expand_query
        result = expand_query("what is the db password")
        self.assertIn("database", result.lower())
        self.assertIn("password", result.lower())

    def test_normalize_query(self):
        from mnemosyne.core.synonyms import normalize_query
        result = normalize_query("what is the database password")
        self.assertIn("database", result)
        self.assertIn("password", result)
        self.assertNotIn("what", result)
        self.assertNotIn("is", result)
        self.assertNotIn("the", result)

    def test_get_synonyms(self):
        from mnemosyne.core.synonyms import get_synonyms
        syns = get_synonyms("db")
        self.assertIn("database", syns)
        self.assertGreater(len(syns), 1)

    def test_no_synonyms_for_unknown(self):
        from mnemosyne.core.synonyms import get_synonyms
        syns = get_synonyms("xyzzy_unknown_word")
        self.assertEqual(syns, ["xyzzy_unknown_word"])

    def test_canonical_mapping(self):
        from mnemosyne.core.synonyms import normalize_query
        r1 = normalize_query("db password")
        r2 = normalize_query("database password")
        self.assertEqual(r1, r2, "db and database should normalize to same form")


class TestQueryCache(unittest.TestCase):
    def setUp(self):
        from mnemosyne.core.query_cache import QueryCache
        self.cache = QueryCache(max_size=100)

    def teardown(self):
        self.cache.close()

    def test_cache_hit_exact(self):
        results = [{"content": "cached result", "score": 0.9}]
        self.cache.put("test query", results)
        cached = self.cache.get("test query")
        self.assertIsNotNone(cached)
        self.assertEqual(cached[0]["content"], "cached result")
        self.assertEqual(self.cache.hits, 1)

    def test_cache_miss(self):
        cached = self.cache.get("nonexistent query")
        self.assertIsNone(cached)
        self.assertEqual(self.cache.misses, 1)

    def test_cache_normalized_hit(self):
        results = [{"content": "test", "score": 0.5}]
        self.cache.put("What is the database password", results)
        cached = self.cache.get("what is the database password")
        self.assertIsNotNone(cached)

    def test_cache_invalidation(self):
        results = [{"content": "test", "score": 0.5}]
        self.cache.put("query one", results)
        self.cache.invalidate()
        cached = self.cache.get("query one")
        self.assertIsNone(cached)

    def test_cache_stats(self):
        self.cache.put("query", [{"content": "x", "score": 0.5}])
        self.cache.get("query")  # hit
        self.cache.get("other")  # miss
        stats = self.cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)


if __name__ == "__main__":
    unittest.main()
