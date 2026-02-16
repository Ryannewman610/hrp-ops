import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "04_parse_and_fill.py"
RAW_ROOT = REPO_ROOT / "inputs" / "export" / "raw"

def choose_fixture_dir() -> Path:
    caros = RAW_ROOT / "Caros_Compass"
    strike = RAW_ROOT / "Strike_King"
    if caros.exists():
        return caros
    if strike.exists():
        return strike
    return caros

FIXTURE_DIR = choose_fixture_dir()


def load_module():
    spec = importlib.util.spec_from_file_location("parse_and_fill", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module at {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParseAndFill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT_PATH.exists():
            raise unittest.SkipTest(f"Missing parser script: {SCRIPT_PATH}")
        if not FIXTURE_DIR.exists():
            raise unittest.SkipTest(f"Missing fixture folder: {FIXTURE_DIR}")
        cls.mod = load_module()
        cls.fixture_horse_id = FIXTURE_DIR.name
        cls.fixture_horse_name = FIXTURE_DIR.name.replace("_", " ")

    def test_meters_history_parses_rows(self):
        warnings = []
        meters_soup, _ = self.mod.file_soup(FIXTURE_DIR, "meters.html")
        rows = self.mod.parse_meters(
            horse_id=self.fixture_horse_id,
            horse_name=self.fixture_horse_name,
            s=meters_soup,
            source="meters.html",
            warnings=warnings,
        )
        self.assertGreater(len(rows), 0, "Expected meters parser to produce rows.")

    def test_works_log_parses_rows(self):
        warnings = []
        works_soup, _ = self.mod.file_soup(FIXTURE_DIR, "works_all.html")
        rows = self.mod.parse_works(
            horse_id=self.fixture_horse_id,
            horse_name=self.fixture_horse_name,
            s=works_soup,
            source="works_all.html",
            warnings=warnings,
        )
        self.assertGreater(len(rows), 0, "Expected works parser to produce rows.")

    def test_join_sets_status_on_works_rows(self):
        warnings = []
        meters_soup, _ = self.mod.file_soup(FIXTURE_DIR, "meters.html")
        works_soup, _ = self.mod.file_soup(FIXTURE_DIR, "works_all.html")
        meters_rows = self.mod.parse_meters(
            horse_id=self.fixture_horse_id,
            horse_name=self.fixture_horse_name,
            s=meters_soup,
            source="meters.html",
            warnings=warnings,
        )
        works_rows = self.mod.parse_works(
            horse_id=self.fixture_horse_id,
            horse_name=self.fixture_horse_name,
            s=works_soup,
            source="works_all.html",
            warnings=warnings,
        )
        self.assertGreater(len(works_rows), 0, "Works rows required for join test.")

        self.mod.join_works_meters(works_rows, meters_rows, warnings, self.fixture_horse_id)
        missing_status = [r for r in works_rows if not r.get("meters_join_status")]
        self.assertEqual(
            len(missing_status),
            0,
            "Expected meters_join_status to be populated for every works row.",
        )

    def test_race_results_use_combined_pp_rows(self):
        warnings = []
        def parse_fixture_rows(fixture_dir: Path):
            printable_soup, printable_txt = self.mod.file_soup(fixture_dir, "profile_printable.html")
            allraces_soup, allraces_txt = self.mod.file_soup(fixture_dir, "profile_allraces.html")
            race_soup = printable_soup or allraces_soup
            race_txt = printable_txt or allraces_txt
            source = "profile_printable.html" if printable_txt else "profile_allraces.html"
            return self.mod.parse_races(
                horse_id=fixture_dir.name,
                horse_name=fixture_dir.name.replace("_", " "),
                s=race_soup,
                txt=race_txt,
                source=source,
                warnings=warnings,
            )

        rows = parse_fixture_rows(FIXTURE_DIR)
        if not any(r.get("race_token", "") for r in rows):
            strike_dir = RAW_ROOT / "Strike_King"
            if strike_dir.exists():
                rows = parse_fixture_rows(strike_dir)

        self.assertGreater(len(rows), 0, "Expected race parser to produce rows.")
        parsed_rows = [r for r in rows if r.get("race_token", "")]
        self.assertGreater(len(parsed_rows), 0, "Expected at least one parsed race row with race_token.")

        token_re = r"^\d{1,2}[A-Za-z]{3}\d{2}-\d+[A-Z]{2,3}$"
        for row in parsed_rows:
            self.assertRegex(row.get("race_token", ""), token_re, "race_token should match expected pattern.")
            self.assertIn(" ", row.get("raw_row", ""), "raw_row should be a combined line with spaces.")


if __name__ == "__main__":
    unittest.main()
