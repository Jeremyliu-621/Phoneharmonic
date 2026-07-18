"""Laptop-side tests for the isolated UNO Q IMU stream probe.

No board, network, App Lab runtime, or running Phoneharmonic server is needed.

Run from the repository root:
    python server/tools/stream_probe_test.py
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
STREAMER_PATH = REPO / "firmware" / "uno_q" / "stream_probe" / "python" / "main.py"
MONITOR_PATH = SERVER / "tools" / "wand_monitor.py"
LAUNCHER = REPO / "firmware" / "uno_q" / "stream_probe" / "run_probe.sh"

sys.path.insert(0, str(SERVER))

from imu_telemetry import ImuTelemetry  # noqa: E402


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


streamer = _load("phoneharmonic_probe_streamer", STREAMER_PATH)
monitor = _load("phoneharmonic_wand_monitor", MONITOR_PATH)


class StreamerTests(unittest.TestCase):
    def test_csv_parser_accepts_exact_finite_row(self) -> None:
        row = streamer.parse_imu_csv("12,0.1,-0.2,9.81,1,2,-3")
        self.assertEqual(row, [12.0, 0.1, -0.2, 9.81, 1.0, 2.0, -3.0])

    def test_csv_parser_rejects_malformed_rows(self) -> None:
        for payload in (
            "1,2,3", "1,2,3,4,5,6,nope", "1,2,3,4,5,6,nan",
            "1,2,3,4,5,6,inf", b"\xff", None, [1, 2, 3, 4, 5, 6, 7],
        ):
            with self.subTest(payload=payload):
                self.assertIsNone(streamer.parse_imu_csv(payload))

    def test_queue_is_bounded_and_discards_oldest(self) -> None:
        samples = streamer.SampleBuffer(maxsize=2)
        for tw in (1.0, 2.0, 3.0):
            samples.put([tw, 0.0, 0.0, 9.81, 0.0, 0.0, 0.0])
        self.assertEqual(samples.snapshot(), {
            "accepted": 3, "rejected": 0, "dropped": 1, "queued": 2,
        })
        batch = samples.take_batch(2)
        self.assertEqual([row[0] for row in batch], [2.0, 3.0])

    def test_five_rows_batch_and_sequence_survives_reconnect_boundary(self) -> None:
        samples = streamer.SampleBuffer()
        client = streamer.StreamClient(
            streamer.ProbeConfig("ws://192.168.1.42:8080/ws", "lol1"), samples,
        )
        for tw in range(5):
            samples.put([float(tw), 0.0, 0.0, 9.81, 0.0, 0.0, 0.0])
        first = client.next_message()
        self.assertEqual(first["t"], "wand.imu")
        self.assertEqual(first["seq"], 1)
        self.assertEqual(len(first["frames"]), 5)

        # A reconnect uses the same StreamClient instance; it must not reset seq.
        client.client_id = "same-board"
        for tw in range(5, 10):
            samples.put([float(tw), 0.0, 0.0, 9.81, 0.0, 0.0, 0.0])
        second = client.next_message()
        self.assertEqual(second["seq"], 2)
        self.assertEqual(client.client_id, "same-board")


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.telemetry = ImuTelemetry()
        self.valid = [100, 0, 0, 9.81, 0, 0, 25]

    def test_validates_counts_and_returns_only_valid_frames(self) -> None:
        forwarded = self.telemetry.ingest(5, [self.valid, [1, 2]], 1234.0)
        self.assertEqual(len(forwarded), 1)
        self.assertTrue(all(isinstance(value, float) for value in forwarded[0]))
        snapshot = self.telemetry.snapshot()
        self.assertEqual(snapshot["batches"], 1)
        self.assertEqual(snapshot["frames"], 1)
        self.assertEqual(snapshot["invalid_frames"], 1)
        self.assertEqual(snapshot["seq"], 5)
        self.assertEqual(snapshot["last_rx_server_ms"], 1234.0)

    def test_forward_sequence_gaps_and_initial_baseline(self) -> None:
        self.telemetry.ingest(100, [self.valid], 1.0)
        self.assertEqual(self.telemetry.snapshot()["seq_gaps"], 0)
        self.telemetry.ingest(103, [self.valid], 2.0)
        self.assertEqual(self.telemetry.snapshot()["seq_gaps"], 2)

    def test_invalid_sequence_rejects_entire_batch(self) -> None:
        self.assertEqual(self.telemetry.ingest(-1, [self.valid], 1.0), [])
        self.assertEqual(self.telemetry.snapshot()["invalid_frames"], 1)

    def test_reset_clears_new_wand_diagnostics(self) -> None:
        self.telemetry.ingest(1, [self.valid], 1.0)
        self.telemetry.reset()
        self.assertEqual(self.telemetry.snapshot(), {
            "seq": None,
            "batches": 0,
            "frames": 0,
            "invalid_frames": 0,
            "seq_gaps": 0,
            "last_frame": None,
            "last_rx_server_ms": None,
        })


def make_snapshots(
    *,
    sample_rate: float = 60.0,
    batch_rate: float = 12.0,
    gravity: float = 9.81,
    moving: bool = True,
    invalid_frames: int = 0,
    seq_gaps: int = 0,
) -> list:
    snapshots = []
    step = 0.15
    for index in range(int(30.0 / step) + 1):
        elapsed = index * step
        in_motion = 8.0 <= elapsed <= 20.0
        gz = 30.0 if in_motion and moving else 0.0
        yaw = (elapsed - 8.0) * 10.0 if in_motion and moving else (120.0 if elapsed > 20 and moving else 0.0)
        imu = {
            "seq": round(elapsed * batch_rate),
            "batches": round(elapsed * batch_rate),
            "frames": round(elapsed * sample_rate),
            "invalid_frames": invalid_frames,
            "seq_gaps": seq_gaps,
            "last_frame": [elapsed * 1000.0, 0.0, 0.0, gravity, 0.0, 0.0, gz],
            "last_rx_server_ms": elapsed * 1000.0,
        }
        snapshots.append(monitor.ProbeSnapshot(elapsed, elapsed, yaw, imu))
    return snapshots


class MonitorTests(unittest.TestCase):
    def assert_check(self, checks, name: str, expected: bool) -> None:
        check = next(item for item in checks if item.name == name)
        self.assertEqual(check.passed, expected, check)

    def test_nominal_sixty_hz_fixture_passes(self) -> None:
        checks = monitor.evaluate_probe(make_snapshots(), 30.0)
        self.assertTrue(all(check.passed for check in checks), checks)

    def test_failure_fixtures_identify_independent_boundaries(self) -> None:
        fixtures = (
            (make_snapshots(gravity=1.0), "gravity units"),
            (make_snapshots(moving=False), "physical yaw movement"),
            (make_snapshots(invalid_frames=1), "valid frames"),
            (make_snapshots(seq_gaps=2), "sequence continuity"),
            (make_snapshots(sample_rate=20.0, batch_rate=4.0), "sample rate"),
        )
        for snapshots, failed_name in fixtures:
            with self.subTest(failed_name=failed_name):
                self.assert_check(monitor.evaluate_probe(snapshots, 30.0), failed_name, False)

    def test_missing_hardware_fails_before_stream_metrics(self) -> None:
        checks = monitor.evaluate_probe([], 30.0, hardware_connected=False)
        self.assertFalse(all(check.passed for check in checks))
        self.assert_check(checks, "hardware wand", False)

    def test_stream_stopping_early_fails_receive_continuity(self) -> None:
        snapshots = [item for item in make_snapshots() if item.elapsed <= 10.0]
        checks = monitor.evaluate_probe(snapshots, 30.0)
        self.assert_check(checks, "receive continuity", False)


class LauncherTests(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(LAUNCHER)], check=True)

    def test_dry_run_has_no_network_dependency(self) -> None:
        result = subprocess.run(
            [str(LAUNCHER), "--board", "arduino@uno-q.local",
             "--server-ip", "192.168.1.42", "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("no local or remote state changed", result.stdout)

    def test_dry_run_rejects_loopback(self) -> None:
        result = subprocess.run(
            [str(LAUNCHER), "--board", "arduino@uno-q.local",
             "--server-ip", "127.0.0.1", "--dry-run"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot be loopback", result.stderr)

    def test_dry_run_rejects_zero_duration_and_invalid_board(self) -> None:
        for extra_args, expected in (
            (["--duration", "0.0"], "positive number"),
            (["--board", "-oProxyCommand=bad"], "USER@HOST"),
        ):
            with self.subTest(extra_args=extra_args):
                args = [str(LAUNCHER), "--board", "arduino@uno-q.local",
                        "--server-ip", "192.168.1.42", "--dry-run"]
                if extra_args[0] == "--board":
                    args[1:3] = extra_args
                else:
                    args.extend(extra_args)
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
