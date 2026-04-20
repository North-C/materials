import json
import os
import pathlib
import subprocess
import tempfile
import textwrap
import unittest


TOOLS_DIR = pathlib.Path(__file__).resolve().parent
SERIES_SCRIPT = TOOLS_DIR / "run-sample-series.sh"


class DirectNydusRunSampleSeriesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = pathlib.Path(
            tempfile.mkdtemp(prefix="kata-direct-nydus-series-test-")
        )
        self.fake_tools = self.temp_dir / "fake-tools"
        self.fake_tools.mkdir(parents=True, exist_ok=True)
        self.results_root = self.temp_dir / "results"
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.log_path = self.temp_dir / "call-log.txt"
        self.counter_path = self.temp_dir / "run-counter.txt"
        self.fail_once_flag = self.temp_dir / "fail-once.flag"

    def _write_script(self, path: pathlib.Path, body: str):
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def _prepare_fake_scripts(self):
        run_sample = self.fake_tools / "run-direct-cri-nydus-lite.sh"
        aggregate = self.fake_tools / "aggregate_batch_results.py"

        self._write_script(
            run_sample,
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                set -o errexit
                set -o nounset
                set -o pipefail
                count=0
                if [[ -f "{self.counter_path}" ]]; then
                  count=$(cat "{self.counter_path}")
                fi
                count=$((count + 1))
                printf '%s' "$count" > "{self.counter_path}"
                printf 'run-direct-cri-nydus-lite:%s\\n' "$count" >> "{self.log_path}"
                if [[ -f "{self.fail_once_flag}" ]]; then
                  rm -f "{self.fail_once_flag}"
                  exit 1
                fi
                run_dir="{self.results_root}/$(date -u +%F)/fake-run-$count"
                mkdir -p "$run_dir/summary"
                cat > "$run_dir/summary/result.json" <<EOF
                {{
                  "run_id": "fake-run-$count",
                  "workload_type": "direct_kata_container",
                  "runtime_handler": "kata",
                  "hypervisor": "cloud-hypervisor",
                  "snapshotter": "nydus",
                  "request_to_running_seconds": 1.05,
                  "sandbox_create_seconds": 0.80,
                  "vm_boot_seconds": 0.06,
                  "vm_to_agent_seconds": 0.48,
                  "create_container_seconds": 0.02,
                  "start_container_seconds": 0.03,
                  "validation_snapshotter_is_nydus": true,
                  "validation_kata_config_is_clh": true,
                  "validation_effective_image_matches_request": true,
                  "validation_nydus_log_seen": true
                }}
                EOF
                printf '%s\\n' "$run_dir"
                """
            ),
        )

        self._write_script(
            aggregate,
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import pathlib
                import sys

                args = sys.argv[1:]
                batch_dir = pathlib.Path(args[args.index("--batch-dir") + 1])
                sample_dirs = []
                warmup_dirs = []
                i = 0
                while i < len(args):
                    if args[i] == "--sample-run-dir":
                        sample_dirs.append(args[i + 1])
                        i += 2
                        continue
                    if args[i] == "--warmup-run-dir":
                        warmup_dirs.append(args[i + 1])
                        i += 2
                        continue
                    i += 1
                (batch_dir / "summary").mkdir(parents=True, exist_ok=True)
                payload = {
                  "batch_id": batch_dir.name,
                  "sample_run_count": len(sample_dirs),
                  "warmup_run_count": len(warmup_dirs),
                  "sample_results": [],
                  "summary": {"sample_count": len(sample_dirs)}
                }
                (batch_dir / "summary" / "batch-results.json").write_text(json.dumps(payload), encoding="utf-8")
                (batch_dir / "summary" / "batch-sample-results.csv").write_text("run_id\\n", encoding="utf-8")
                (batch_dir / "summary" / "batch-summary.csv").write_text("sample_count\\n", encoding="utf-8")
                """
            ),
        )

        return run_sample, aggregate

    def _run_series(self, extra_env: dict[str, str] | None = None):
        run_sample, aggregate = self._prepare_fake_scripts()
        env = {
            **dict(os.environ),
            "RESULTS_ROOT": str(self.results_root),
            "DIRECT_NYDUS_RUN_SAMPLE_SCRIPT": str(run_sample),
            "DIRECT_NYDUS_AGGREGATE_BATCH_RESULTS_SCRIPT": str(aggregate),
            "PATH": f"{self.fake_tools}:{os.environ.get('PATH', '')}",
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [
                "bash",
                str(SERIES_SCRIPT),
                "--batch-id",
                "batch-20260420T181000Z",
                "--warmup-count",
                "1",
                "--sample-count",
                "1",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=TOOLS_DIR.parents[3],
        )

    def test_retries_sample_run_once_then_succeeds(self):
        self.fail_once_flag.write_text("fail", encoding="utf-8")

        result = self._run_series({"DIRECT_NYDUS_RUN_SAMPLE_RETRIES": "1"})

        batch_dir = pathlib.Path(result.stdout.strip())
        self.assertTrue((batch_dir / "summary" / "batch-results.json").is_file())

        call_log = self.log_path.read_text(encoding="utf-8")
        self.assertIn("run-direct-cri-nydus-lite:1", call_log)
        self.assertIn("run-direct-cri-nydus-lite:2", call_log)

        meta = json.loads((batch_dir / "summary" / "batch-meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["failed_attempt_count"], 1)
        self.assertEqual(meta["successful_warmup_count"], 1)
        self.assertEqual(meta["successful_sample_count"], 1)

    def test_records_failed_attempt_when_no_retries_left(self):
        self.fail_once_flag.write_text("fail", encoding="utf-8")

        result = self._run_series({"DIRECT_NYDUS_RUN_SAMPLE_RETRIES": "0"})

        batch_dir = pathlib.Path(result.stdout.strip())
        meta = json.loads((batch_dir / "summary" / "batch-meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["failed_attempt_count"], 1)
        self.assertEqual(meta["successful_warmup_count"], 0)
        self.assertEqual(meta["successful_sample_count"], 1)
        self.assertTrue((batch_dir / "raw" / "failed-attempts.log").is_file())


if __name__ == "__main__":
    unittest.main()
