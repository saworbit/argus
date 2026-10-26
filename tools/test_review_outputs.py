"""Keep generated review artifacts local and the answer key separate."""
import subprocess
import unittest
from pathlib import Path

from prepare_blind_perception import PRIVATE, PUBLIC

ROOT=Path(__file__).resolve().parents[1]

class ReviewOutputs(unittest.TestCase):
    def test_generated_media_and_pages_are_ignored(self):
        for path in ('reviews/blind-perception-v1/pair1-A-1.webm',
                     'reviews/blind-perception-v2/index.html'):
            result=subprocess.run(['git','check-ignore','--no-index','-q',path],cwd=ROOT)
            self.assertEqual(result.returncode,0,path)

    def test_template_is_not_ignored(self):
        result=subprocess.run(['git','check-ignore','--no-index','-q','tools/blind_perception_review.html'],cwd=ROOT)
        self.assertEqual(result.returncode,1)

    def test_key_directory_is_outside_public_directory(self):
        self.assertFalse(PRIVATE.resolve().is_relative_to(PUBLIC.resolve()))

if __name__=='__main__':unittest.main()
