import importlib.util
import json
import pathlib
import tempfile
import unittest


TOOLS_DIR = pathlib.Path(__file__).resolve().parent
MODULE_PATH = TOOLS_DIR / "parse_direct_kata_latency.py"
SPEC = importlib.util.spec_from_file_location("parse_direct_kata_latency", MODULE_PATH)
parse_direct_kata_latency = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parse_direct_kata_latency)


class ParseDirectKataLatencyTests(unittest.TestCase):
    def test_parse_run_dir_extracts_direct_kata_timeline(self):
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="kata-direct-lite-run-"))
        (run_dir / "raw").mkdir()
        (run_dir / "logs").mkdir()
        (run_dir / "summary").mkdir()

        request = {
            "run_id": "run-20260418T120000Z",
            "workload_type": "direct_kata_container",
            "sandbox_name": "kata-direct-lite-sandbox",
            "container_name": "kata-direct-lite-container",
            "namespace": "default",
            "runtime_handler": "kata",
            "hypervisor": "cloud-hypervisor",
            "t_request_sent": "2026-04-18T12:00:00.000000Z",
        }
        inspectp = {
            "status": {
                "id": "sandbox-1234",
                "metadata": {
                    "name": "kata-direct-lite-sandbox",
                    "uid": "sandbox-uid-1234",
                    "namespace": "default",
                },
                "createdAt": "2026-04-18T12:00:00.180000Z",
            }
        }
        inspect = {
            "status": {
                "id": "container-1234",
                "metadata": {"name": "kata-direct-lite-container"},
                "createdAt": "2026-04-18T12:00:00.910000Z",
                "startedAt": "2026-04-18T12:00:01.020000Z",
            }
        }
        containerd_log = """
2026-04-18T20:00:00.210000+0800 host containerd[1]: time="2026-04-18T20:00:00.210000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-direct-lite-sandbox,Uid:sandbox-uid-1234,Namespace:default,Attempt:0,}"
2026-04-18T20:00:00.260000+0800 host containerd[1]: time="2026-04-18T20:00:00.260000+08:00" level=info path=/opt/kata/bin/cloud-hypervisor sandbox=sandbox-1234
2026-04-18T20:00:00.620000+0800 host containerd[1]: time="2026-04-18T20:00:00.620000+08:00" level=info msg="VM started" sandbox=sandbox-1234
2026-04-18T20:00:00.830000+0800 host containerd[1]: time="2026-04-18T20:00:00.830000+08:00" level=info msg="Agent started in the sandbox" sandbox=sandbox-1234
2026-04-18T20:00:00.880000+0800 host containerd[1]: time="2026-04-18T20:00:00.880000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-direct-lite-sandbox,Uid:sandbox-uid-1234,Namespace:default,Attempt:0,} returns sandbox id \\"sandbox-1234\\""
2026-04-18T20:00:00.900000+0800 host containerd[1]: time="2026-04-18T20:00:00.900000+08:00" level=info msg="CreateContainer within sandbox \\"sandbox-1234\\" for container &ContainerMetadata{Name:kata-direct-lite-container,Attempt:0,}"
2026-04-18T20:00:00.970000+0800 host containerd[1]: time="2026-04-18T20:00:00.970000+08:00" level=info msg="CreateContainer within sandbox \\"sandbox-1234\\" for &ContainerMetadata{Name:kata-direct-lite-container,Attempt:0,} returns container id \\"container-1234\\""
2026-04-18T20:00:00.980000+0800 host containerd[1]: time="2026-04-18T20:00:00.980000+08:00" level=info msg="StartContainer for \\"container-1234\\""
2026-04-18T20:00:01.010000+0800 host containerd[1]: time="2026-04-18T20:00:01.010000+08:00" level=info msg="Container is started" container=container-1234 sandbox=sandbox-1234
""".strip()

        (run_dir / "raw" / "request.json").write_text(
            json.dumps(request), encoding="utf-8"
        )
        (run_dir / "raw" / "inspectp.json").write_text(
            json.dumps(inspectp), encoding="utf-8"
        )
        (run_dir / "raw" / "inspect.json").write_text(
            json.dumps(inspect), encoding="utf-8"
        )
        (run_dir / "logs" / "containerd.log").write_text(
            containerd_log, encoding="utf-8"
        )

        parsed = parse_direct_kata_latency.parse_run_dir(run_dir)

        self.assertEqual(parsed["sandbox_id"], "sandbox-1234")
        self.assertEqual(parsed["container_id"], "container-1234")
        self.assertEqual(
            parsed["t_run_pod_sandbox_request"], "2026-04-18T12:00:00.210000+0000"
        )
        self.assertEqual(
            parsed["t_cloud_hypervisor_spawn"], "2026-04-18T12:00:00.260000+0000"
        )
        self.assertEqual(parsed["t_vm_started"], "2026-04-18T12:00:00.620000+0000")
        self.assertEqual(
            parsed["t_agent_started"], "2026-04-18T12:00:00.830000+0000"
        )
        self.assertEqual(
            parsed["t_run_pod_sandbox_return"], "2026-04-18T12:00:00.880000+0000"
        )
        self.assertEqual(
            parsed["t_create_container_request"], "2026-04-18T12:00:00.900000+0000"
        )
        self.assertEqual(
            parsed["t_create_container_return"], "2026-04-18T12:00:00.970000+0000"
        )
        self.assertEqual(
            parsed["t_start_container_request"], "2026-04-18T12:00:00.980000+0000"
        )
        self.assertEqual(
            parsed["t_container_started"], "2026-04-18T12:00:01.010000+0000"
        )
        self.assertEqual(parsed["t_running"], "2026-04-18T12:00:01.020000+0000")
        self.assertAlmostEqual(parsed["request_to_running_seconds"], 1.02)
        self.assertAlmostEqual(parsed["sandbox_create_seconds"], 0.67)
        self.assertAlmostEqual(parsed["vm_boot_seconds"], 0.36)
        self.assertAlmostEqual(parsed["vm_to_agent_seconds"], 0.21)
        self.assertAlmostEqual(parsed["create_container_seconds"], 0.07)
        self.assertAlmostEqual(parsed["start_container_seconds"], 0.03)
        self.assertAlmostEqual(parsed["runtime_to_running_seconds"], 0.81)


if __name__ == "__main__":
    unittest.main()
