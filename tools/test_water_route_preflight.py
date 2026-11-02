"""Legacy geometry mismatches must stop before any lab resources are owned."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import verify_water_route as runner


class WaterRoutePreflight(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'src';self.source.mkdir()
        self.graph=self.source/'argus_nav_e1m5.qc'

    def test_all_legacy_cases_use_qc_seats_and_exact_fixture_tolerance(self):
        good="n0 = Argus_NavNode ('41 713 7.2');\nn1 = Argus_NavNode ('-87 809 111');\n"
        for case in (3,4,5,6):
            self.graph.write_text(good,encoding='utf-8')
            runner.preflight_source(self.source,case)
            self.graph.write_text(good.replace('-87 809 111','-87 809 111.9'),encoding='utf-8')
            runner.preflight_source(self.source,case)
            self.graph.write_text(good.replace('-87 809 111','-87 809 112'),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'archived source graph'):
                runner.preflight_source(self.source,case)
            # Python double subtraction puts 8.2 - 7.2 just below one;
            # the compiled QC vectors differ by exactly one and must refuse.
            self.graph.write_text(good.replace('41 713 7.2','41 713 8.2'),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'archived source graph'):
                runner.preflight_source(self.source,case)

    def test_comments_and_sidecar_cannot_supply_missing_compiled_seat(self):
        self.graph.write_text("// Argus_NavNode ('41 713 7.2');\n/* Argus_NavNode ('41 713 7.2'); */\nn1=Argus_NavNode ('-87 809 111');",encoding='utf-8')
        (self.source/'argus_nav_e1m5.qc.json').write_text('{"nodes":[[41,713,7.2],[-87,809,111]]}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'41 713 7.2'):
            runner.preflight_source(self.source,6)

    def test_invalid_source_is_explicit(self):
        self.graph.write_text("n0=Argus_NavNode ('nan 713 7.2');",encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'invalid navigation seat'):
            runner.preflight_source(self.source,3)

    def test_other_cases_need_no_historical_graph(self):
        for case in (1,2,7,8,9,10,11,12):
            runner.preflight_source(self.source/'absent',case)

    def test_cli_rejects_before_output_staging_compile_or_engine(self):
        self.graph.write_text("n0=Argus_NavNode ('-87 809 111');",encoding='utf-8')
        output=Path(self.temp.name)/'must_remain_absent'
        argv=['verify_water_route.py','--output',str(output),'--prefix','preflight_test',
              '--source',str(self.source),'--maps','e1m5','--case','6']
        err=io.StringIO()
        with patch('sys.argv',argv),patch.object(runner,'new_output',side_effect=AssertionError('output staging was reached')) as new,\
                patch.object(runner,'stage') as stage,patch.object(runner,'Lab') as lab,\
                contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as exit:
                runner.main()
        self.assertEqual(exit.exception.code,2)
        self.assertIn('41 713 7.2',err.getvalue())
        self.assertIn('--source',err.getvalue())
        self.assertFalse(output.exists())
        new.assert_not_called();stage.assert_not_called();lab.assert_not_called()


if __name__=='__main__':unittest.main()
