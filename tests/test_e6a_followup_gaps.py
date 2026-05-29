"""
Regression tests for E6.a follow-up fixes:

- E6.a.1: `mnemosyne_triple_add` MCP tool routes annotation-flavored
  predicates to `AnnotationStore` instead of writing them into the
  legacy `triples` table.

- E6.a.2: `BeamMemory.forget_working` (called from `Mnemosyne.forget`)
  cascade-deletes annotation rows tagged with the same memory_id --
  pre-fix, mentions / fact / occurred_on / has_source rows leaked
  through export, recall, and entity-aware queries even after forget.

- E6.a /review F1: cross-session forget safety.
- E6.a /review F3: cascade atomicity.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mnemosyne.core.annotations import AnnotationStore
from mnemosyne.core.beam import BeamMemory
from mnemosyne.core.memory import Mnemosyne
from mnemosyne.core.triples import TripleStore


class TestForgetCascadeToAnnotations(unittest.TestCase):
    """E6.a.2: `forget()` removes annotations tagged with the memory_id."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)

    def tearDown(self):
        import os
        for suffix in ("", ".pre_e6_backup"):
            try:
                os.unlink(str(self.tmp.name) + suffix)
            except OSError:
                pass

    def test_forget_deletes_annotations_for_memory_id(self):
        mem = Mnemosyne(session_id="s1", db_path=self.db_path)
        memory_id = mem.remember(
            "Alice met Bob in San Francisco.",
            source="test", importance=0.5, extract_entities=True,
        )
        ann_store = AnnotationStore(db_path=self.db_path)
        pre_count = len(ann_store.query_by_memory(memory_id=memory_id))
        self.assertGreater(pre_count, 0, "test setup failure: no annotations to forget")

        result = mem.forget(memory_id)
        self.assertTrue(result, "forget() returned False -- memory wasn't found")

        post_rows = ann_store.query_by_memory(memory_id=memory_id)
        self.assertEqual(
            post_rows, [],
            f"annotations for forgotten memory_id={memory_id} still present: {post_rows}",
        )

    def test_forget_doesnt_touch_other_memories_annotations(self):
        mem = Mnemosyne(session_id="s1", db_path=self.db_path)
        ann_store = AnnotationStore(db_path=self.db_path)

        id_to_forget = mem.remember("Alice met Bob.", source="test", extract_entities=True)
        id_to_keep = mem.remember("Charlie met Dana.", source="test", extract_entities=True)

        keep_count_before = len(ann_store.query_by_memory(memory_id=id_to_keep))
        self.assertGreater(keep_count_before, 0)

        mem.forget(id_to_forget)

        self.assertEqual(ann_store.query_by_memory(memory_id=id_to_forget), [])
        keep_count_after = len(ann_store.query_by_memory(memory_id=id_to_keep))
        self.assertEqual(keep_count_after, keep_count_before)

    def test_beam_forget_working_directly_cascades(self):
        beam = BeamMemory(session_id="s1", db_path=self.db_path)
        memory_id = beam.remember(
            "Alice met Bob in Paris.", source="test", importance=0.5,
            extract_entities=True,
        )
        ann_store = AnnotationStore(db_path=self.db_path)
        self.assertGreater(len(ann_store.query_by_memory(memory_id=memory_id)), 0)

        beam.forget_working(memory_id)
        self.assertEqual(ann_store.query_by_memory(memory_id=memory_id), [])

    def test_forget_after_export_leaves_no_leaked_annotations(self):
        mem = Mnemosyne(session_id="s1", db_path=self.db_path)
        memory_id = mem.remember(
            "Confidential: user's home address is 123 Main St.",
            source="test", extract_entities=True,
        )
        mem.forget(memory_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "export.json"
            mem.export_to_file(str(export_path))
            with open(export_path) as f:
                payload = json.load(f)

        forgotten_annotations = [
            r for r in payload.get("annotations", [])
            if r.get("memory_id") == memory_id
        ]
        self.assertEqual(forgotten_annotations, [])


class TestForgetCrossSessionDoesNotLeakAnnotations(unittest.TestCase):
    """E6.a /review finding F1: cross-session forget must not destroy annotations."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)

    def tearDown(self):
        import os
        for suffix in ("", ".pre_e6_backup"):
            try:
                os.unlink(str(self.tmp.name) + suffix)
            except OSError:
                pass

    def test_wrong_session_forget_does_not_touch_annotations(self):
        mem_a = Mnemosyne(session_id="session-a", db_path=self.db_path)
        memory_id = mem_a.remember(
            "Alice met Bob in Paris.", source="test", extract_entities=True,
        )
        ann_store = AnnotationStore(db_path=self.db_path)
        pre_count = len(ann_store.query_by_memory(memory_id=memory_id))
        self.assertGreater(pre_count, 0)

        mem_b = Mnemosyne(session_id="session-b", db_path=self.db_path)
        result = mem_b.forget(memory_id)
        self.assertFalse(result, "forget() should return False -- cross-session attempt")

        post_rows = ann_store.query_by_memory(memory_id=memory_id)
        self.assertEqual(len(post_rows), pre_count,
                         "cross-session forget destroyed annotations")

    def test_correct_session_forget_still_works(self):
        mem = Mnemosyne(session_id="session-a", db_path=self.db_path)
        memory_id = mem.remember(
            "Test memory with entities Alice and Bob.", source="test",
            extract_entities=True,
        )
        ann_store = AnnotationStore(db_path=self.db_path)
        self.assertGreater(len(ann_store.query_by_memory(memory_id=memory_id)), 0)

        result = mem.forget(memory_id)
        self.assertTrue(result)
        self.assertEqual(ann_store.query_by_memory(memory_id=memory_id), [])


class TestForgetCascadeIsAtomic(unittest.TestCase):
    """E6.a /review finding F3: cascade must be atomic."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)

    def tearDown(self):
        import os
        for suffix in ("", ".pre_e6_backup"):
            try:
                os.unlink(str(self.tmp.name) + suffix)
            except OSError:
                pass

    def test_failed_cascade_rolls_back_working_memory_delete(self):
        import sqlite3
        beam = BeamMemory(session_id="s1", db_path=self.db_path)
        memory_id = beam.remember(
            "Atomic cascade test.", source="test", importance=0.5,
            extract_entities=True,
        )
        row = beam.conn.execute(
            "SELECT id FROM working_memory WHERE id = ?", (memory_id,)
        ).fetchone()
        self.assertIsNotNone(row)

        raw = sqlite3.connect(str(self.db_path))
        raw.execute("DROP TABLE annotations")
        raw.commit()
        raw.close()

        with self.assertRaises(sqlite3.OperationalError):
            beam.forget_working(memory_id)

        row = beam.conn.execute(
            "SELECT id FROM working_memory WHERE id = ?", (memory_id,)
        ).fetchone()
        self.assertIsNotNone(row, "working_memory row not rolled back after cascade failure")


if __name__ == "__main__":
    unittest.main()
