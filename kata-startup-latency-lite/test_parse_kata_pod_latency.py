import importlib.util
import json
import pathlib
import tempfile
import unittest


TOOLS_DIR = pathlib.Path(__file__).resolve().parent
MODULE_PATH = TOOLS_DIR / "parse_kata_pod_latency.py"
SPEC = importlib.util.spec_from_file_location("parse_kata_pod_latency", MODULE_PATH)
parse_kata_pod_latency = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parse_kata_pod_latency)


class ParseKataPodLatencyTests(unittest.TestCase):
    def test_parse_run_dir_extracts_minimal_timeline(self):
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="kata-lite-run-"))
        (run_dir / "raw").mkdir()
        (run_dir / "logs").mkdir()
        (run_dir / "summary").mkdir()

        request = {
            "run_id": "run-20260416T120000Z",
            "workload_type": "k8s_pod",
            "pod_name": "kata-lite-120000",
            "namespace": "default",
            "runtime_handler": "kata",
            "hypervisor": "cloud-hypervisor",
            "t_request_sent": "2026-04-16T12:00:00.000000Z",
        }
        pod = {
            "metadata": {
                "name": "kata-lite-120000",
                "namespace": "default",
                "uid": "pod-uid-1234",
                "creationTimestamp": "2026-04-16T12:00:00.120000Z",
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {
                        "containerID": "containerd://ctr-1234",
                        "state": {
                            "running": {
                                "startedAt": "2026-04-16T12:00:01.450000Z"
                            }
                        },
                    }
                ]
            },
        }
        events = {
            "items": [
                {
                    "reason": "Scheduled",
                    "firstTimestamp": "2026-04-16T12:00:00.300000Z",
                }
            ]
        }

        kubelet_log = """
2026-04-16T20:00:00.360000+0800 host kubelet[1]: I0416 20:00:00.360000       1 kubelet.go:1703] "SyncPod enter" pod="default/kata-lite-120000" podUID="pod-uid-1234"
""".strip()
        scheduler_log = """
2026-04-16T20:00:00.280000+0800 host kube-scheduler[1]: I0416 20:00:00.280000       1 schedule_one.go:286] "Successfully bound pod to node" pod="default/kata-lite-120000" node="test-node"
""".strip()
        containerd_log = """
2026-04-16T20:00:00.520000+0800 host containerd[1]: time="2026-04-16T20:00:00.520000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-lite-120000,Uid:pod-uid-1234,Namespace:default,Attempt:0,}"
2026-04-16T20:00:01.020000+0800 host containerd[1]: time="2026-04-16T20:00:01.020000+08:00" level=info msg="VM started" sandbox=sandbox-1234
2026-04-16T20:00:01.260000+0800 host containerd[1]: time="2026-04-16T20:00:01.260000+08:00" level=info msg="Agent started in the sandbox" sandbox=sandbox-1234
2026-04-16T20:00:01.310000+0800 host containerd[1]: time="2026-04-16T20:00:01.310000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-lite-120000,Uid:pod-uid-1234,Namespace:default,Attempt:0,} returns sandbox id \\"sandbox-1234\\""
2026-04-16T20:00:01.420000+0800 host containerd[1]: time="2026-04-16T20:00:01.420000+08:00" level=info msg="Container is started" container=ctr-1234 sandbox=sandbox-1234
""".strip()

        (run_dir / "raw" / "request.json").write_text(
            json.dumps(request), encoding="utf-8"
        )
        (run_dir / "raw" / "pod.json").write_text(json.dumps(pod), encoding="utf-8")
        (run_dir / "raw" / "events.json").write_text(
            json.dumps(events), encoding="utf-8"
        )
        (run_dir / "logs" / "kubelet.log").write_text(kubelet_log, encoding="utf-8")
        (run_dir / "logs" / "kube-scheduler.log").write_text(
            scheduler_log, encoding="utf-8"
        )
        (run_dir / "logs" / "containerd.log").write_text(
            containerd_log, encoding="utf-8"
        )

        parsed = parse_kata_pod_latency.parse_run_dir(run_dir)

        self.assertEqual(parsed["pod_name"], "kata-lite-120000")
        self.assertEqual(parsed["pod_uid"], "pod-uid-1234")
        self.assertEqual(parsed["container_id"], "ctr-1234")
        self.assertEqual(parsed["sandbox_id"], "sandbox-1234")
        self.assertEqual(parsed["t_scheduled"], "2026-04-16T12:00:00.300000+0000")
        self.assertEqual(
            parsed["t_kubelet_syncpod_enter"], "2026-04-16T12:00:00.360000+0000"
        )
        self.assertEqual(
            parsed["t_run_pod_sandbox_request"], "2026-04-16T12:00:00.520000+0000"
        )
        self.assertEqual(parsed["t_vm_started"], "2026-04-16T12:00:01.020000+0000")
        self.assertEqual(
            parsed["t_agent_started"], "2026-04-16T12:00:01.260000+0000"
        )
        self.assertEqual(
            parsed["t_container_started"], "2026-04-16T12:00:01.420000+0000"
        )
        self.assertEqual(parsed["t_running"], "2026-04-16T12:00:01.450000+0000")
        self.assertAlmostEqual(parsed["request_to_running_seconds"], 1.45)
        self.assertAlmostEqual(parsed["object_create_to_running_seconds"], 1.33)
        self.assertAlmostEqual(parsed["schedule_latency_seconds"], 0.18)
        self.assertAlmostEqual(parsed["kubelet_to_runtime_seconds"], 0.16)
        self.assertAlmostEqual(parsed["vm_boot_seconds"], 0.5)
        self.assertAlmostEqual(parsed["vm_to_agent_seconds"], 0.24)
        self.assertAlmostEqual(parsed["runtime_to_running_seconds"], 0.93)


if __name__ == "__main__":
    unittest.main()
