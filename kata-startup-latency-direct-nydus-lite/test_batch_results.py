import importlib.util
import json
import pathlib
import tempfile
import unittest


TOOLS_DIR = pathlib.Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    module_path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AggregateDirectNydusBatchResultsTests(unittest.TestCase):
    def setUp(self):
        self.aggregator = load_module(
            "aggregate_direct_nydus_batch_results",
            "aggregate_batch_results.py",
        )
        self.temp_dir = pathlib.Path(
            tempfile.mkdtemp(prefix="kata-direct-nydus-batch-results-")
        )

    def _write_json(self, path: pathlib.Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _make_run_dir(
        self,
        run_id: str,
        *,
        request_to_running: float,
        sandbox_create: float,
        vm_boot: float,
        vm_to_agent: float,
    ) -> pathlib.Path:
        run_dir = self.temp_dir / run_id
        summary_dir = run_dir / "summary"
        summary_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(
            summary_dir / "result.json",
            {
                "run_id": run_id,
                "workload_type": "direct_kata_container",
                "runtime_handler": "kata",
                "hypervisor": "cloud-hypervisor",
                "snapshotter": "nydus",
                "source_image": "sealos.hub:5000/pause:3.9",
                "effective_image": "sealos.hub:5000/kata-direct-nydus/pause:nydus-lite",
                "request_to_running_seconds": request_to_running,
                "sandbox_create_seconds": sandbox_create,
                "vm_boot_seconds": vm_boot,
                "vm_to_agent_seconds": vm_to_agent,
                "create_container_seconds": 0.02,
                "start_container_seconds": 0.03,
                "validation_snapshotter_is_nydus": True,
                "validation_kata_config_is_clh": True,
                "validation_effective_image_matches_request": True,
                "validation_nydus_log_seen": True,
            },
        )
        return run_dir

    def test_summarize_batch_results_computes_metric_stats(self):
        sample_a = self._make_run_dir(
            "run-a001",
            request_to_running=1.0,
            sandbox_create=0.75,
            vm_boot=0.05,
            vm_to_agent=0.48,
        )
        sample_b = self._make_run_dir(
            "run-b002",
            request_to_running=1.2,
            sandbox_create=0.80,
            vm_boot=0.06,
            vm_to_agent=0.50,
        )

        summary = self.aggregator.summarize_batch_results(
            batch_id="batch-20260420T180000Z",
            sample_run_dirs=[sample_a, sample_b],
            warmup_run_dirs=[],
        )

        self.assertEqual(summary["sample_run_count"], 2)
        self.assertEqual(len(summary["sample_results"]), 2)
        self.assertEqual(summary["summary"]["sample_count"], 2)
        self.assertAlmostEqual(
            summary["summary"]["metrics"]["request_to_running_seconds"]["mean"], 1.1
        )
        self.assertAlmostEqual(
            summary["summary"]["metrics"]["sandbox_create_seconds"]["p50"], 0.775
        )
        self.assertEqual(summary["summary"]["validation_success_count"], 2)

    def test_write_batch_artifacts_emits_json_and_csv_files(self):
        sample_run = self._make_run_dir(
            "run-c003",
            request_to_running=1.1,
            sandbox_create=0.77,
            vm_boot=0.05,
            vm_to_agent=0.49,
        )
        batch_dir = self.temp_dir / "batch-20260420T180100Z"

        summary = self.aggregator.summarize_batch_results(
            batch_id=batch_dir.name,
            sample_run_dirs=[sample_run],
            warmup_run_dirs=[],
        )
        self.aggregator.write_batch_artifacts(batch_dir, summary)

        summary_json = json.loads(
            (batch_dir / "summary" / "batch-results.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary_json["batch_id"], batch_dir.name)

        sample_csv = (batch_dir / "summary" / "batch-sample-results.csv").read_text(
            encoding="utf-8"
        )
        batch_csv = (batch_dir / "summary" / "batch-summary.csv").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "run_id,workload_type,runtime_handler,hypervisor,snapshotter", sample_csv
        )
        self.assertIn("run-c003,direct_kata_container,kata,cloud-hypervisor,nydus", sample_csv)
        self.assertIn(
            "sample_count,validation_success_count,validation_failure_count,validation_success_rate,request_to_running_seconds_mean",
            batch_csv,
        )
        self.assertIn("1,1,0,1.0,1.1", batch_csv)


if __name__ == "__main__":
    unittest.main()
