# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Publication preserves source time without exposing future guest input."""
import datetime as dt
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers/carla-viss-kuksa/src"))
from carla_viss_kuksa_provider import runtime
from carla_viss_kuksa_provider.bridge import SIGNALS, SignalValue


class Clock:
    def __init__(self, advance=True):
        self.wall, self.mono, self.advance, self.waits = 1800000000.0, 10.0, advance, []

    def sleep(self, delay):
        self.waits.append(delay)
        self.mono += delay
        if self.advance:
            self.wall += delay


class PublicationClockTests(unittest.TestCase):
    def trial(self, ahead, *, advance=True, unavailable=False, connect_delay=0, failure=None):
        clock = Clock(advance)
        stamp = dt.datetime.fromtimestamp(clock.wall + ahead, dt.timezone.utc)
        values = {s.path: None if unavailable else SignalValue(1, stamp) for s in SIGNALS}
        publications, disconnected = [], []
        sdk = ModuleType("kuksa_client.grpc")
        sdk.Datapoint = lambda value, timestamp=None: SimpleNamespace(value=value, timestamp=timestamp)
        sdk.DataEntry = lambda path, value: SimpleNamespace(path=path, value=value)
        sdk.EntryUpdate = lambda entry, fields: SimpleNamespace(entry=entry, fields=fields)
        sdk.Field = SimpleNamespace(VALUE="VALUE")

        def receive(updates, *, try_v2, timeout):
            self.assertFalse(try_v2)
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 2)
            self.assertEqual([u.entry.path for u in updates], [s.path for s in SIGNALS])
            for update in updates:
                point = update.entry.value
                if unavailable:
                    self.assertIsNone(point.value)
                    self.assertIsNone(point.timestamp)
                else:
                    self.assertIs(point.timestamp, stamp)
                    self.assertLessEqual(point.timestamp.timestamp(), clock.wall)
            publications.append(timeout)
            if failure:
                raise failure

        sink = runtime.KuksaSink(None)
        sink._client = SimpleNamespace(set=receive, disconnect=lambda: disconnected.append(True))

        def connect():
            if connect_delay:
                clock.sleep(connect_delay)
            return sink._client

        with patch.dict(sys.modules, {"kuksa_client.grpc": sdk}), \
             patch.object(sink, "_connect", side_effect=connect), \
             patch.object(runtime.time, "time", side_effect=lambda: clock.wall), \
             patch.object(runtime.time, "monotonic", side_effect=lambda: clock.mono), \
             patch.object(runtime.time, "sleep", side_effect=clock.sleep):
            error = None
            try:
                sink.publish(values)
            except runtime.KuksaUnavailable as caught:
                error = caught
        return clock, publications, disconnected, error

    def test_original_timestamp_is_preserved_after_small_clock_lead(self):
        for lead in (.001, .020, .100):
            with self.subTest(lead=lead):
                clock, publications, _, error = self.trial(lead)
                self.assertIsNone(error)
                self.assertEqual(len(publications), 1)
                self.assertAlmostEqual(sum(clock.waits), lead, places=6)
                self.assertAlmostEqual(publications[0], 2-lead, places=6)

    def test_past_measurement_is_not_delayed_or_refreshed(self):
        clock, publications, _, error = self.trial(-10)
        self.assertIsNone(error)
        self.assertEqual(clock.waits, [])
        self.assertEqual(publications, [2])

    def test_explicit_unavailability_is_not_delayed(self):
        clock, publications, _, error = self.trial(10, unavailable=True)
        self.assertIsNone(error)
        self.assertEqual(clock.waits, [])
        self.assertEqual(publications, [2])

    def test_lead_outside_existing_budget_fails_closed(self):
        clock, publications, disconnected, error = self.trial(2.1)
        self.assertIsNotNone(error)
        self.assertEqual(publications, [])
        self.assertEqual(clock.waits, [])
        self.assertTrue(disconnected)

    def test_nonadvancing_clock_cannot_extend_publication_budget(self):
        clock, publications, disconnected, error = self.trial(.020, advance=False)
        self.assertIsNotNone(error)
        self.assertEqual(publications, [])
        self.assertLessEqual(sum(clock.waits), 2)
        self.assertTrue(disconnected)

    def test_connection_time_consumes_same_budget(self):
        _, publications, _, error = self.trial(.020, connect_delay=.1)
        self.assertIsNone(error)
        self.assertAlmostEqual(publications[0], 1.9)
        _, publications, disconnected, error = self.trial(.020, connect_delay=2.1)
        self.assertIsNotNone(error)
        self.assertEqual(publications, [])
        self.assertTrue(disconnected)

    def test_rpc_failure_closes_without_retry(self):
        _, publications, disconnected, error = self.trial(.020, failure=RuntimeError("unavailable"))
        self.assertIsNotNone(error)
        self.assertEqual(len(publications), 1)
        self.assertTrue(disconnected)


if __name__ == "__main__":
    unittest.main()
