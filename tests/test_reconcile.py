import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/star-rsm-invoice-reconciliation/scripts/reconcile.py"


class ReconcileTests(unittest.TestCase):
    def test_reports_duplicate_star_slot_and_count_mismatch(self):
        star_csv = """Student Id Number,Session Date,Therapist,Session ID,Start Time,End Time,Service,Hours,Amount
2001,09/01/2026,Avery,STAR-101,9:00 AM,9:30 AM,OT Online,0.5,50.00
2001,09/01/2026,Avery,STAR-102,09:00AM,09:30AM,OT Online - No Show,0.5,50.00
"""
        rsm_xls = """<html><body><table>
<tr><th>SID</th><th>Srvc Date</th><th>Therapist</th><th>Service</th><th>Hours</th><th>Grand Total</th><th>No Show?</th></tr>
<tr><td>2001</td><td>09/01/2026</td><td>Avery</td><td>OT Online</td><td>0.5</td><td>$50.00</td><td>No</td></tr>
</table></body></html>"""
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            star_path = fixture_dir / "star.csv"
            rsm_path = fixture_dir / "rsm.xls"
            star_path.write_text(star_csv)
            rsm_path.write_text(rsm_xls)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--star", str(star_path), "--rsm", str(rsm_path)],
                capture_output=True,
                check=True,
                text=True,
            )

        result = json.loads(completed.stdout)
        duplicates = result["duplicate_star_sessions"]
        self.assertEqual(duplicates["count"], 1)
        self.assertEqual(duplicates["unchecked_session_count"], 0)
        self.assertEqual(duplicates["rows"][0]["start_time"], "09:00")
        self.assertEqual(duplicates["rows"][0]["end_time"], "09:30")
        self.assertEqual(
            [row["session_id"] for row in duplicates["rows"][0]["star_sessions"]],
            ["STAR-101", "STAR-102"],
        )
        self.assertEqual(result["count_mismatches"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
