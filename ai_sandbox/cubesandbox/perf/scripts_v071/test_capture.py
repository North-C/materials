"""Offline capture tests: temporary files and a harmless failing Python child only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("capture", Path(__file__).with_name("capture.py"))
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "source.log"
        self.delta = self.root / "delta.log"
        self.log.write_bytes(b"old history\n")

    def test_only_new_bytes_are_captured(self):
        before = capture.snapshot(self.log)
        with self.log.open("ab") as stream:
            stream.write(b"new one\nnew two\n")
        result = capture.capture_delta(self.log, before, self.delta, 1000)
        self.assertEqual(self.delta.read_bytes(), b"new one\nnew two\n")
        self.assertEqual(result["status"], "captured")
        self.assertEqual(result["read_start"], len(b"old history\n"))
        self.assertEqual(stat.S_IMODE(self.delta.stat().st_mode), 0o600)

    def test_rotation_never_copies_replacement(self):
        before = capture.snapshot(self.log)
        self.log.rename(self.root / "rotated.log")
        self.log.write_bytes(b"replacement history\n")
        result = capture.capture_delta(self.log, before, self.delta, 1000)
        self.assertEqual(result["status"], "rotated")
        self.assertFalse(self.delta.exists())

    def test_truncation_and_regrowth_are_detected(self):
        before = capture.snapshot(self.log)
        self.log.write_bytes(b"small")
        result = capture.capture_delta(self.log, before, self.delta, 1000)
        self.assertEqual(result["status"], "truncated")
        self.log.write_bytes(b"replacement much longer than before\n")
        result = capture.capture_delta(self.log, before, self.delta, 1000)
        self.assertEqual(result["status"], "rewritten")
        self.assertFalse(self.delta.exists())

    def test_cap_reports_omitted_bytes(self):
        before = capture.snapshot(self.log)
        with self.log.open("ab") as stream:
            stream.write(b"0123456789\n")
        result = capture.capture_delta(self.log, before, self.delta, 4)
        self.assertEqual(self.delta.read_bytes(), b"0123")
        self.assertEqual(result["captured_bytes"], 4)
        self.assertEqual(result["omitted_bytes"], 7)
        self.assertIn("byte_cap_exceeded", result["gaps"])
        self.assertIn("partial_last_line", result["gaps"])

    def test_partial_first_line_is_explicit(self):
        self.log.write_bytes(b"partial old")
        before = capture.snapshot(self.log)
        with self.log.open("ab") as stream:
            stream.write(b" continued\nnew\n")
        result = capture.capture_delta(self.log, before, self.delta, 1000)
        self.assertIn("partial_first_line", result["gaps"])

    def test_missing_initial_file_is_not_read_from_zero(self):
        absent = self.root / "absent.log"
        before = capture.snapshot(absent)
        absent.write_bytes(b"unknown pre-existing content\n")
        result = capture.capture_delta(absent, before, self.delta, 1000)
        self.assertIn("no_readable_start_offset", result["gaps"])
        self.assertFalse(self.delta.exists())


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "owned.json"

    def test_unknown_phase_is_retained_without_guessing(self):
        self.path.write_text(json.dumps({"formal": [], "warmup": [], "unknown_phase": ["sandbox-a"]}))
        ids, record = capture.load_owned_ids(self.path, None)
        self.assertEqual(ids["unknown_phase"], ["sandbox-a"])
        self.assertEqual(ids["formal"], [])
        self.assertIn("ownership_phase_unknown", record["gaps"])

    def test_stale_file_rejected(self):
        self.path.write_text(json.dumps({"formal": ["sandbox-a"], "warmup": [], "unknown_phase": []}))
        before = capture.ownership_fingerprint(self.path)
        ids, record = capture.load_owned_ids(self.path, before)
        self.assertEqual(record["status"], "stale")
        self.assertEqual(ids["formal"], [])

    def test_duplicate_phase_assignment_rejected(self):
        self.path.write_text(json.dumps({"formal": ["sandbox-a"], "warmup": ["sandbox-a"], "unknown_phase": []}))
        ids, record = capture.load_owned_ids(self.path, None)
        self.assertEqual(record["status"], "invalid")
        self.assertFalse(any(ids.values()))


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "node.log"
        self.log.write_text("old\n")
        self.binary = self.root / "client"
        self.binary.write_bytes(b"test client fixture; never executed\n")
        self.binary.chmod(0o700)
        self.output = self.root / "capture"
        self.expected = hashlib.sha256(self.binary.read_bytes()).hexdigest()

    def arguments(self, extra=None):
        argv = ["--output", str(self.output), "--benchmark-binary", str(self.binary),
                "--template-id", "tpl-test", "--tail-seconds", "0"]
        for name in list(capture.DEFAULT_LOGS) + ["api"]:
            argv += ["--log", name + "=" + str(self.log)]
        return capture.parser().parse_args(argv + (extra or []))

    def test_failed_command_still_saves_deltas_and_manifest(self):
        secret = "SENSITIVE_ARGUMENT_MUST_NOT_APPEAR"
        code = ("import os,pathlib; p=pathlib.Path(" + repr(str(self.log)) + "); "
                "p.open('a').write('command evidence\\n'); "
                "pathlib.Path(os.environ['CUBE_CAPTURE_OWNED_IDS']).write_text(" +
                repr(json.dumps({"formal": ["owned-1"], "warmup": [], "unknown_phase": []})) + "); "
                "print('diagnostic failure fixture'); raise SystemExit(7)")
        args = self.arguments(["--owned-ids", str(self.root / "ids.json"), "--", sys.executable, "-c", code, secret])
        args.command = args.command[1:]
        metrics_result = {"status": "unavailable", "gaps": ["fixture_offline"]}
        with mock.patch.object(capture.platform, "system", return_value="Linux"), \
             mock.patch.object(capture, "OFFICIAL_SHA256", self.expected), \
             mock.patch.object(capture, "capture_metrics", return_value=metrics_result.copy()) as metrics:
            result, manifest = capture.run_capture(args)
        self.assertEqual(result, 7)
        self.assertEqual(manifest["status"], "captured")
        self.assertEqual(metrics.call_count, 2)
        self.assertEqual((self.output / "evidence/shim_stat-delta.log").read_text(), "command evidence\n")
        self.assertEqual((self.output / "evidence/command.log").read_text(), "diagnostic failure fixture\n")
        self.assertEqual(json.loads((self.output / "owned-sandbox-ids.json").read_text())["formal"], ["owned-1"])
        self.assertLessEqual(manifest["command"]["ended_at"], manifest["ended_at"])
        for path in self.output.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret, path.read_text())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)

    def test_preflight_never_runs_command_or_metrics(self):
        args = self.arguments(["--preflight-only"])
        with mock.patch.object(capture.platform, "system", return_value="Linux"), \
             mock.patch.object(capture, "OFFICIAL_SHA256", self.expected), \
             mock.patch.object(capture, "capture_metrics") as metrics, \
             mock.patch.object(capture, "run_command") as command:
            code, manifest = capture.run_capture(args)
        self.assertEqual(code, 0)
        self.assertEqual(manifest["status"], "preflight_only")
        metrics.assert_not_called()
        command.assert_not_called()

    def test_wrong_binary_fails_before_creating_output(self):
        args = self.arguments(["--preflight-only"])
        with mock.patch.object(capture.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(ValueError, "sha256_mismatch"):
                capture.run_capture(args)
        self.assertFalse(self.output.exists())

    def test_existing_output_never_reused(self):
        self.output.mkdir()
        marker = self.output / "keep"
        marker.write_text("preserve")
        args = self.arguments(["--preflight-only"])
        with mock.patch.object(capture.platform, "system", return_value="Linux"), \
             mock.patch.object(capture, "OFFICIAL_SHA256", self.expected):
            with self.assertRaises(FileExistsError):
                capture.run_capture(args)
        self.assertEqual(marker.read_text(), "preserve")

    def test_launch_failure_keeps_manifest_with_127(self):
        args = self.arguments(["--", str(self.root / "does-not-exist")])
        args.command = args.command[1:]
        with mock.patch.object(capture.platform, "system", return_value="Linux"), \
             mock.patch.object(capture, "OFFICIAL_SHA256", self.expected), \
             mock.patch.object(capture, "capture_metrics", return_value={"status": "unavailable", "gaps": []}):
            code, manifest = capture.run_capture(args)
        self.assertEqual(code, 127)
        self.assertEqual(manifest["command"]["launch_error_type"], "FileNotFoundError")
        self.assertTrue((self.output / "capture-manifest.json").is_file())

    def test_child_console_is_bounded(self):
        self.output.mkdir()
        (self.output / "evidence").mkdir()
        result = capture.run_command([sys.executable, "-c", "import sys; sys.stdout.write('x' * (5 * 1024 * 1024))"],
                                     self.output, "tpl-test", self.binary, None)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual((self.output / "evidence/command.log").stat().st_size, 4 * capture.MIB)
        self.assertEqual(result["console"]["omitted_bytes"], capture.MIB)
        self.assertIn("command_output_cap_exceeded", result["console"]["gaps"])


if __name__ == "__main__":
    unittest.main()
