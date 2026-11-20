#!/usr/bin/env python3
"""Tests for tools/argus_build_stamp.py, the QC build identity (#823)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_build_stamp as stamp  # noqa: E402

PROGS = """#pragma progs_dat "../lq1/progs.dat"
#includelist
defs.qc
argus_build.qc          // generated
argus.qc   // the bot
#endlist
"""

DEFS = "float x;\n"
ARGUS = 'void() f =\n{\n    dprint ("a  b // not a comment\\n");\n    x = 1;\n};\n'


def tree(root, progs=PROGS, defs=DEFS, argus=ARGUS):
    root = Path(root)
    (root / "progs.src").write_text(progs, encoding="latin-1")
    (root / "defs.qc").write_text(defs, encoding="latin-1")
    (root / "argus.qc").write_text(argus, encoding="latin-1")
    return root


class Normalise(unittest.TestCase):
    def test_normalise_matches_the_shared_cases(self):
        path = Path(__file__).resolve().parent / 'argus_mcp/testdata/build_normalise_cases.json'
        for case in json.loads(path.read_text(encoding='utf-8')):
            with self.subTest(case=case['name']):
                self.assertEqual(stamp.normalise(case['source']), case['expected'])

    def test_line_and_block_comments_are_whitespace(self):
        self.assertEqual(stamp.normalise("a // c\nb"), "a\nb")
        self.assertEqual(stamp.normalise("a /* c */ b"), "a b")
        self.assertEqual(stamp.normalise("a /* c\n d */ b"), "a\nb")

    def test_comment_markers_inside_strings_are_kept(self):
        text = 'dprint ("http://x /* y */");'
        self.assertEqual(stamp.normalise(text), text)

    def test_string_whitespace_is_kept_byte_for_byte(self):
        self.assertNotEqual(stamp.normalise('s = "a  b";'),
                            stamp.normalise('s = "a b";'))

    def test_escaped_quote_does_not_end_a_string(self):
        text = 's = "say \\"hi\\" // still string";'
        self.assertEqual(stamp.normalise(text), text)

    def test_vector_literal_is_kept(self):
        self.assertIn("'0  0 1'", stamp.normalise("v = '0  0 1';"))

    def test_layout_collapses_but_newlines_survive(self):
        self.assertEqual(stamp.normalise("a   b\n\n\n  c"), "a b\nc")
        self.assertEqual(stamp.normalise("#define X 1\nfoo"),
                         "#define X 1\nfoo")


class Compute(unittest.TestCase):
    def test_comment_only_change_keeps_the_identity(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = stamp.compute(tree(a))
            second = stamp.compute(tree(b, argus="// header\n" + ARGUS.replace(
                "x = 1;", "x = 1;    /* set */")))
            self.assertEqual(first, second)
            self.assertEqual(len(first), stamp.ID_LEN)

    def test_code_change_moves_the_identity(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertNotEqual(stamp.compute(tree(a)),
                                stamp.compute(tree(b, argus=ARGUS.replace("1;", "2;"))))

    def test_string_change_moves_the_identity(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertNotEqual(stamp.compute(tree(a)),
                                stamp.compute(tree(b, argus=ARGUS.replace("a  b", "a b"))))

    def test_a_listed_file_rename_moves_the_identity(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = stamp.compute(tree(a))
            root = tree(b, progs=PROGS.replace("defs.qc", "defs2.qc"))
            (root / "defs2.qc").write_text(DEFS, encoding="latin-1")
            self.assertNotEqual(first, stamp.compute(root))

    def test_the_stamp_file_and_its_progs_line_are_excluded(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            listed = tree(a)
            unlisted = tree(b, progs=PROGS.replace(
                "argus_build.qc          // generated\n", ""))
            (Path(a) / stamp.STAMP_FILE).write_text(stamp.render("deadbeef0000"))
            self.assertEqual(stamp.compute(listed), stamp.compute(unlisted))

    def test_crlf_and_lf_agree(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual(stamp.compute(tree(a)),
                             stamp.compute(tree(b, argus=ARGUS.replace("\n", "\r\n"),
                                                progs=PROGS.replace("\n", "\r\n"))))

    def test_an_empty_list_is_an_error(self):
        with tempfile.TemporaryDirectory() as a:
            root = tree(a, progs="#includelist\n#endlist\n")
            with self.assertRaises(ValueError):
                stamp.compute(root)


class WriteAndCheck(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = stamp.main(list(argv))
        return code, out.getvalue()

    def test_write_then_check_is_current_and_idempotent(self):
        with tempfile.TemporaryDirectory() as a:
            root = tree(a)
            code, _ = self.run_main("--src", str(root), "--check")
            self.assertEqual(code, 1)
            build_id, changed = stamp.write(root)
            self.assertTrue(changed)
            self.assertEqual(stamp.read_stamp(root), build_id)
            self.assertEqual(stamp.write(root), (build_id, False))
            code, text = self.run_main("--src", str(root), "--check")
            self.assertEqual(code, 0)
            self.assertIn(build_id, text)

    def test_check_names_the_fix_when_stale(self):
        with tempfile.TemporaryDirectory() as a:
            root = tree(a)
            stamp.write(root)
            (root / "argus.qc").write_text(ARGUS.replace("1;", "3;"), encoding="latin-1")
            code, text = self.run_main("--src", str(root), "--check")
            self.assertEqual(code, 1)
            self.assertIn("--write", text)

    def test_rendered_file_is_valid_for_the_reader(self):
        self.assertEqual(stamp.STAMP_RE.search(stamp.render("0123456789ab"))[1],
                         "0123456789ab")


if __name__ == "__main__":
    unittest.main()
