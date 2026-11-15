import unittest
from datetime import date, timedelta
from climateM1.services.history import normalize_power_history
from climateM1.services.locations import LOCATIONS


class HistoryNormalizationTests(unittest.TestCase):
    def test_year_season_and_completeness_are_preserved(self):
        start = date(2021, 1, 1)
        rainfall = {}
        temperature = {}
        for offset in range(60):
            day = start + timedelta(days=offset)
            key = day.strftime("%Y%m%d")
            rainfall[key] = 0.0 if offset < 8 else 2.0
            temperature[key] = 25.0 + (offset % 5) / 10
        payload = normalize_power_history(
            {"header": {"fill_value": -999}, "properties": {"parameter": {"PRECTOTCORR": rainfall, "T2M": temperature}}},
            LOCATIONS["pamplemousses-04"],
            "20210101",
            "20210301",
            "2026-11-08T00:00:00+00:00",
        )
        self.assertEqual(payload["timeseries"][0]["period"], "2021")
        self.assertTrue(payload["seasonal"])
        self.assertEqual(payload["timeseries"][0]["drySpellDays"], 8)
        self.assertEqual(payload["metrics"]["dataCompleteness"], 100.0)


if __name__ == "__main__":
    unittest.main()
