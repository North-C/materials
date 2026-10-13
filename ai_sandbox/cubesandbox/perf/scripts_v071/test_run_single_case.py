"""Offline tests: original suite control flow, mocked API/guest/gate/benchmark."""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("single_case_adapter", HERE / "run_single_case.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class OfflineAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.suite_dir = self.root / "suite"
        self.suite_dir.mkdir()
        for name in ("run_suite.py", "host_quiet_gate.py"):
            shutil.copyfile(HERE / "reference/deployed-suite" / name, self.suite_dir / name)
        (self.suite_dir / "host_quiet_gate.py").chmod(0o700)
        self.binary = self.root / "fixture-bench"
        self.binary.write_bytes(b"offline fixture, must never be executed\n")
        self.binary.chmod(0o700)
        self.binary_hash = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.capture = self.root / "capture"
        self.capture.mkdir()
        self.owned = self.capture / "owned-source.json"
        self.environment = {
            "CUBE_CAPTURE_DIR": str(self.capture), "CUBE_CAPTURE_TEMPLATE_ID": "tpl-dedicated-fixture",
            "CUBE_CAPTURE_BENCHMARK_BINARY": str(self.binary), "CUBE_CAPTURE_OWNED_IDS": str(self.owned),
            "E2B_API_URL": "http://wrong-host.invalid", "CUBE_PROXY_NODE_IP": "wrong-host.invalid",
            "CUBE_PERF_TAP_MIN_READY": "1",
        }
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # Fixture imports happen before the adapter's own no-bytecode context.
        self.stack.enter_context(mock.patch.object(sys, "dont_write_bytecode", True))
        self.stack.enter_context(mock.patch.dict(os.environ, self.environment, clear=True))
        self.stack.enter_context(mock.patch.object(adapter, "OFFICIAL_SHA256", self.binary_hash))
        summary = types.ModuleType("summarize_results")
        summary.summarize = lambda report, folder: "Offline fixture summary\n"
        self.stack.enter_context(mock.patch.dict(sys.modules, {"summarize_results": summary}))
        # Any accidentally unmocked remote request, child process or URL fetch
        # fails the test instead of reaching a real deployment.
        self.stack.enter_context(mock.patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")))
        self.stack.enter_context(mock.patch("subprocess.run", side_effect=AssertionError("process launch forbidden")))
        self.stack.enter_context(mock.patch("subprocess.check_output", side_effect=AssertionError("process launch forbidden")))

    def args(self, execute=False):
        return adapter.parser().parse_args([
            "--suite-dir", str(self.suite_dir), "--native-binary-sha256", self.binary_hash,
            *(["--execute"] if execute else []),
        ])

    def load_original(self):
        return adapter.load_suite(self.suite_dir / "run_suite.py")

    def test_original_reference_plan_reduced_to_exactly_one_case(self):
        suite = self.load_original()
        self.assertEqual(len(suite.plan("reference", ["3.2"], [])), 7)
        selected = adapter.single_case_plan(suite.plan)
        self.assertEqual(selected("reference", ["3.2"], []), [adapter.CASE])
        for profile, sections, points in (("quick", ["3.2"], []),
                                          ("reference", ["3.2", "3.3"], []),
                                          ("reference", ["3.2"], [100])):
            with self.assertRaises(ValueError):
                selected(profile, sections, points)

    def test_changed_or_duplicate_target_plan_is_rejected(self):
        command = [*adapter.CASE[2]]
        command[command.index("-n") + 1] = "200"
        for commands in ([], [adapter.CASE, adapter.CASE], [("3.2", "c100n100", command)]):
            with self.assertRaisesRegex(ValueError, "plan_mismatch"):
                adapter.single_case_plan(lambda *args: commands)("reference", ["3.2"], [])

    def test_dry_run_calls_original_main_without_api_or_load(self):
        suite = self.load_original()
        original_plan = suite.plan
        with mock.patch.object(adapter, "load_suite", return_value=suite), \
             mock.patch.object(suite, "API", side_effect=AssertionError("API forbidden")) as api, \
             mock.patch.object(suite, "run_command", side_effect=AssertionError("load forbidden")) as command:
            code, status = adapter.run(self.args())
        self.assertEqual(code, 0)
        self.assertEqual(status["status"], "dry_run")
        self.assertFalse(status["execute_requested"])
        self.assertFalse(status["benchmark_invocation_recorded"])
        self.assertFalse(self.owned.exists())
        self.assertFalse((self.capture / "suite-results").exists())
        self.assertIs(suite.plan, original_plan)
        api.assert_not_called()
        command.assert_not_called()
        self.assertEqual(os.environ["E2B_API_URL"], "http://wrong-host.invalid")

    def test_suite_hash_mismatch_blocks_import_and_records_failure(self):
        with (self.suite_dir / "run_suite.py").open("a") as stream:
            stream.write("\n# changed fixture\n")
        with mock.patch.object(adapter, "load_suite") as loader:
            code, status = adapter.run(self.args(execute=True))
        self.assertEqual(code, 2)
        self.assertEqual(status["reason_code"], "suite_sha256_mismatch")
        self.assertFalse(status["suite_main_invoked"])
        self.assertFalse(self.owned.exists())
        loader.assert_not_called()
        self.assertEqual(json.loads((self.capture / "adapter-status.json").read_text())["exit_code"], 2)

    def test_optional_master_config_is_forwarded(self):
        config = self.root / "master-conf.yaml"
        args = adapter.parser().parse_args([
            "--suite-dir", str(self.suite_dir), "--native-binary-sha256", self.binary_hash,
            "--master-config", str(config),
        ])
        suite = self.load_original()
        observed = []
        def main():
            observed.extend(sys.argv)
            return 0
        with mock.patch.object(adapter, "load_suite", return_value=suite), \
             mock.patch.object(suite, "main", side_effect=main):
            code, status = adapter.run(args)
        self.assertEqual(code, 0)
        self.assertEqual(observed[observed.index("--master-config") + 1], str(config.resolve()))

    def test_official_binary_hash_mismatch_blocks_import(self):
        self.binary.write_bytes(b"changed binary\n")
        with mock.patch.object(adapter, "load_suite") as loader:
            code, status = adapter.run(self.args(execute=True))
        self.assertEqual(code, 2)
        self.assertEqual(status["reason_code"], "native_binary_sha256_mismatch")
        loader.assert_not_called()

    def test_explicit_expected_hash_cannot_select_an_arbitrary_binary(self):
        args = self.args()
        args.native_binary_sha256 = "0" * 64
        code, status = adapter.run(args)
        self.assertEqual(code, 2)
        self.assertEqual(status["reason_code"], "expected_official_binary_sha256_required")

    def prepare_execution(self, preflight_error=None):
        suite = self.load_original()
        template_id = self.environment["CUBE_CAPTURE_TEMPLATE_ID"]
        active = []
        api = mock.Mock()
        api.sandboxes.side_effect = lambda: list(active)
        api.snapshots.return_value = set()

        def request(method, path, params=None):
            self.assertEqual(method, "DELETE")
            sid = path.removeprefix("/sandboxes/")
            active[:] = [item for item in active if item["sandboxID"] != sid]
            return None, 204

        api.request.side_effect = request

        def benchmark(command, env, log, timeout):
            self.assertEqual(Path(command[0]), self.binary.resolve())
            self.assertEqual(command[1:9], ["-c", "100", "-n", "100", "-w", "3", "-m", "create-only"])
            self.assertEqual(timeout, 600)
            self.assertEqual(env["E2B_API_URL"], "http://127.0.0.1:3000")
            self.assertEqual(env["CUBE_PROXY_NODE_IP"], "192.168.25.90")
            self.assertEqual(env["CUBE_PROXY_PORT_HTTP"], "18080")
            self.assertEqual(env["CUBE_PERF_TAP_MIN_READY"], "4000")
            self.assertEqual(env["CUBE_PERF_QUIET_SAMPLES"], "5")
            self.assertEqual(env["CUBE_PERF_GATE_INTERVAL"], "5")
            self.assertEqual(env["CUBE_PERF_GATE_TIMEOUT"], "120")
            self.assertEqual(env["E2B_API_KEY"], "capture-noauth-placeholder")
            output = Path(command[command.index("-o") + 1])
            output.write_text(json.dumps({"config": {"template": template_id},
                                         "summary": {"successful": 100, "errors": 0},
                                         "raw": [{"seq": number, "duration": 123} for number in range(100)]}))
            active.extend({"sandboxID": f"fixture-{number:03}", "templateID": template_id, "state": "running"}
                          for number in range(103))

        self.stack.enter_context(mock.patch.object(adapter, "load_suite", return_value=suite))
        self.stack.enter_context(mock.patch.object(suite, "API", return_value=api))
        self.stack.enter_context(mock.patch.object(suite, "sample_memory", return_value={"local": 256 * 1024 * 1024}))
        gate = self.stack.enter_context(mock.patch.object(suite, "run_host_gate"))
        guest = self.stack.enter_context(mock.patch.object(suite, "guest_preflight", side_effect=preflight_error))
        command = self.stack.enter_context(mock.patch.object(suite, "run_command", side_effect=benchmark))
        self.stack.enter_context(mock.patch.object(suite.time, "sleep"))
        return suite, api, gate, guest, command

    def test_original_main_runs_only_single_case_and_original_ledger_cleanup(self):
        suite, api, gate, guest, command = self.prepare_execution()
        code, status = adapter.run(self.args(execute=True))
        self.assertEqual(code, 0)
        self.assertEqual(status["suite_status"], "complete")
        self.assertEqual(status["case_status"], "complete")
        self.assertTrue(status["benchmark_invocation_recorded"])
        self.assertEqual(command.call_count, 1)
        self.assertEqual(gate.call_count, 2)
        self.assertEqual(guest.call_count, 1)
        self.assertEqual(api.request.call_count, 103)
        self.assertEqual(api.sandboxes(), [])
        owned = json.loads(self.owned.read_text())
        self.assertEqual(owned["formal"], [])
        self.assertEqual(owned["warmup"], [])
        self.assertEqual(len(owned["unknown_phase"]), 103)
        self.assertEqual(status["ownership"]["ledger_status"], "drained")
        self.assertEqual((self.capture / "startup-latency/c100n100.raw.json").read_bytes(),
                         (self.capture / "suite-results/c100n100.json").read_bytes())
        report = json.loads((self.capture / "suite-results/report.json").read_text())
        self.assertEqual([item["label"] for item in report["commands"]], ["c100n100"])
        self.assertEqual(report["memory_reserve_gib"], 64)
        self.assertFalse(list(self.suite_dir.rglob("__pycache__")))

    def test_guest_preflight_failure_exports_empty_ids_without_claiming_execution(self):
        suite, api, gate, guest, command = self.prepare_execution(RuntimeError("offline guest failure"))
        code, status = adapter.run(self.args(execute=True))
        self.assertEqual(code, 1)
        self.assertEqual(status["status"], "suite_failed")
        self.assertFalse(status["benchmark_invocation_recorded"])
        self.assertEqual(status["suite_preflight"], "failed")
        self.assertEqual(status["ownership"]["status"], "missing")
        self.assertEqual(json.loads(self.owned.read_text()), {"formal": [], "warmup": [], "unknown_phase": []})
        self.assertFalse((self.capture / "startup-latency/c100n100.raw.json").exists())
        command.assert_not_called()
        api.request.assert_not_called()

    def test_invalid_ledger_never_assigns_ids(self):
        results = self.capture / "suite-results"
        results.mkdir()
        (results / "c100n100.delete.json").write_text(json.dumps({
            "ownership_mode": "exclusive-template", "template_id": "foreign-template",
            "observed_ids": ["foreign-sandbox"], "status": "drained"}))
        status = {}
        errors = adapter.export_evidence(self.capture, self.owned, "tpl-dedicated-fixture", status)
        self.assertEqual(errors, ["ownership_ledger_invalid"])
        self.assertEqual(json.loads(self.owned.read_text()), {"formal": [], "warmup": [], "unknown_phase": []})

    def test_existing_output_is_preserved(self):
        self.owned.write_text("keep existing evidence")
        with self.assertRaisesRegex(ValueError, "already_exists_or_conflicts"):
            adapter.run(self.args(execute=True))
        self.assertEqual(self.owned.read_text(), "keep existing evidence")

    def test_false_success_without_suite_evidence_is_rejected(self):
        suite = self.load_original()
        with mock.patch.object(adapter, "load_suite", return_value=suite), \
             mock.patch.object(suite, "main", return_value=0):
            code, status = adapter.run(self.args(execute=True))
        self.assertEqual(code, 2)
        self.assertEqual(status["status"], "suite_success_evidence_incomplete")
        self.assertFalse(status["benchmark_invocation_recorded"])


if __name__ == "__main__":
    unittest.main()
