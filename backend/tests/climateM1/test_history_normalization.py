import asyncio
import unittest
from datetime import date, timedelta
from climateM1.services import history
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

    def test_in_process_history_calls_use_coordinate_and_period_cache(self):
        records = {}
        requests = []
        raw = {
            "header": {"fill_value": -999},
            "properties": {"parameter": {"PRECTOTCORR": {}, "T2M": {}}},
        }
        for offset in range(31):
            day = date(2021, 1, 1) + timedelta(days=offset)
            key = day.strftime("%Y%m%d")
            raw["properties"]["parameter"]["PRECTOTCORR"][key] = 1.0
            raw["properties"]["parameter"]["T2M"][key] = 25.0

        class FakeResponse:
            url = "https://power.larc.nasa.gov/fake"

            def raise_for_status(self):
                return None

            def json(self):
                return raw

        async def fake_get(self, url, params):
            requests.append((url, dict(params)))
            return FakeResponse()

        def get_cached(key, allow_stale=False):
            return records.get(key)

        def save_cached(key, payload):
            records[key] = payload

        from unittest.mock import patch

        with patch.object(history.httpx.AsyncClient, "get", fake_get), \
             patch.object(history, "get_cached", get_cached), \
             patch.object(history, "save_cached", save_cached):
            first = asyncio.run(history.fetch_history(
                LOCATIONS["pamplemousses-04"], "20210101", "20210131"))
            second = asyncio.run(history.fetch_history(
                LOCATIONS["pamplemousses-04"], "20210101", "20210131"))
            asyncio.run(history.fetch_history(
                LOCATIONS["flacq-02"], "20210101", "20210131"))
            asyncio.run(history.fetch_history(
                LOCATIONS["pamplemousses-04"], "20210101", "20210201"))

        self.assertEqual(len(requests), 3)
        self.assertEqual(first["timeseries"], second["timeseries"])
        self.assertEqual(
            len(records),
            3,
        )
        self.assertTrue(all(":PRECTOTCORR,T2M" in key for key in records))


if __name__ == "__main__":
    unittest.main()
