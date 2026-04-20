import importlib.util
import json
import pathlib
import tempfile
import unittest


TOOLS_DIR = pathlib.Path(__file__).resolve().parent
MODULE_PATH = TOOLS_DIR / "parse_direct_nydus_kata_latency.py"
SPEC = importlib.util.spec_from_file_location(
    "parse_direct_nydus_kata_latency", MODULE_PATH
)
parse_direct_nydus_kata_latency = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parse_direct_nydus_kata_latency)


class ParseDirectNydusKataLatencyTests(unittest.TestCase):
    def test_parse_run_dir_extracts_nydus_timeline_and_validations(self):
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="kata-direct-nydus-lite-run-"))
        (run_dir / "raw").mkdir()
        (run_dir / "logs").mkdir()
        (run_dir / "summary").mkdir()

        request = {
            "run_id": "run-20260420T100000Z",
            "workload_type": "direct_kata_container",
            "sandbox_name": "kata-direct-nydus-lite-sandbox",
            "container_name": "kata-direct-nydus-lite-container",
            "namespace": "default",
            "runtime_handler": "kata",
            "hypervisor": "cloud-hypervisor",
            "source_image": "sealos.hub:5000/pause:3.9",
            "effective_image": "localhost/kata-direct-nydus/pause:converted",
            "image_conversion_mode": "converted-local",
            "expected_snapshotter": "nydus",
            "t_request_sent": "2026-04-20T10:00:00.000000Z",
        }
        inspectp = {
            "status": {
                "id": "sandbox-nydus-1234",
                "metadata": {
                    "name": "kata-direct-nydus-lite-sandbox",
                    "uid": "sandbox-uid-1234",
                    "namespace": "default",
                },
                "createdAt": "2026-04-20T10:00:00.180000Z",
            },
            "info": {
                "image": "localhost/kata-direct-nydus/pause:converted",
                "snapshotter": "nydus",
                "runtimeHandler": "kata",
                "runtimeType": "io.containerd.kata.v2",
                "runtimeOptions": {
                    "config_path": "/opt/kata/share/defaults/kata-containers/configuration-clh.toml"
                },
            },
        }
        inspect = {
            "status": {
                "id": "container-nydus-1234",
                "metadata": {"name": "kata-direct-nydus-lite-container"},
                "createdAt": "2026-04-20T10:00:00.910000Z",
                "startedAt": "2026-04-20T10:00:01.050000Z",
                "image": {
                    "image": "localhost/kata-direct-nydus/pause:converted",
                    "userSpecifiedImage": "localhost/kata-direct-nydus/pause:converted",
                },
                "imageRef": "localhost/kata-direct-nydus/pause@sha256:abcd",
            },
            "info": {
                "sandboxID": "sandbox-nydus-1234",
                "snapshotter": "nydus",
                "runtimeType": "io.containerd.kata.v2",
                "runtimeOptions": {
                    "config_path": "/opt/kata/share/defaults/kata-containers/configuration-clh.toml"
                },
                "config": {
                    "image": {"image": "localhost/kata-direct-nydus/pause:converted"}
                },
            },
        }
        containerd_log = """
2026-04-20T18:00:00.210000+0800 host containerd[1]: time="2026-04-20T18:00:00.210000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-direct-nydus-lite-sandbox,Uid:sandbox-uid-1234,Namespace:default,Attempt:0,}"
2026-04-20T18:00:00.260000+0800 host containerd[1]: time="2026-04-20T18:00:00.260000+08:00" level=info path=/opt/kata/bin/cloud-hypervisor sandbox=sandbox-nydus-1234
2026-04-20T18:00:00.620000+0800 host containerd[1]: time="2026-04-20T18:00:00.620000+08:00" level=info msg="VM started" sandbox=sandbox-nydus-1234
2026-04-20T18:00:00.830000+0800 host containerd[1]: time="2026-04-20T18:00:00.830000+08:00" level=info msg="Agent started in the sandbox" sandbox=sandbox-nydus-1234
2026-04-20T18:00:00.880000+0800 host containerd[1]: time="2026-04-20T18:00:00.880000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-direct-nydus-lite-sandbox,Uid:sandbox-uid-1234,Namespace:default,Attempt:0,} returns sandbox id \\"sandbox-nydus-1234\\""
2026-04-20T18:00:00.900000+0800 host containerd[1]: time="2026-04-20T18:00:00.900000+08:00" level=info msg="CreateContainer within sandbox \\"sandbox-nydus-1234\\" for container &ContainerMetadata{Name:kata-direct-nydus-lite-container,Attempt:0,}"
2026-04-20T18:00:00.970000+0800 host containerd[1]: time="2026-04-20T18:00:00.970000+08:00" level=info msg="CreateContainer within sandbox \\"sandbox-nydus-1234\\" for &ContainerMetadata{Name:kata-direct-nydus-lite-container,Attempt:0,} returns container id \\"container-nydus-1234\\""
2026-04-20T18:00:00.980000+0800 host containerd[1]: time="2026-04-20T18:00:00.980000+08:00" level=info msg="StartContainer for \\"container-nydus-1234\\""
2026-04-20T18:00:01.040000+0800 host containerd[1]: time="2026-04-20T18:00:01.040000+08:00" level=info msg="Container is started" container=container-nydus-1234 sandbox=sandbox-nydus-1234
""".strip()
        nydus_log = """
2026-04-20T18:00:00.120000+0800 host containerd-nydus-grpc[1]: time="2026-04-20T18:00:00.120000+08:00" level=info msg="prepare snapshot" image_ref="localhost/kata-direct-nydus/pause:converted"
2026-04-20T18:00:00.170000+0800 host containerd-nydus-grpc[1]: time="2026-04-20T18:00:00.170000+08:00" level=info msg="mount snapshot" image_ref="localhost/kata-direct-nydus/pause:converted"
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
        (run_dir / "logs" / "nydus-snapshotter.log").write_text(
            nydus_log, encoding="utf-8"
        )

        parsed = parse_direct_nydus_kata_latency.parse_run_dir(run_dir)

        self.assertEqual(parsed["snapshotter"], "nydus")
        self.assertEqual(
            parsed["kata_config_path"],
            "/opt/kata/share/defaults/kata-containers/configuration-clh.toml",
        )
        self.assertEqual(parsed["effective_image"], request["effective_image"])
        self.assertEqual(parsed["t_nydus_prepare"], "2026-04-20T10:00:00.120000+0000")
        self.assertEqual(parsed["t_nydus_mount"], "2026-04-20T10:00:00.170000+0000")
        self.assertTrue(parsed["validation_snapshotter_is_nydus"])
        self.assertTrue(parsed["validation_kata_config_is_clh"])
        self.assertTrue(parsed["validation_effective_image_matches_request"])
        self.assertTrue(parsed["validation_nydus_log_seen"])
        self.assertAlmostEqual(parsed["request_to_running_seconds"], 1.05)

    def test_parse_run_dir_accepts_config_image_and_containerd_nydus_evidence(self):
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="kata-direct-nydus-lite-fallback-"))
        (run_dir / "raw").mkdir()
        (run_dir / "logs").mkdir()
        (run_dir / "summary").mkdir()

        request = {
            "run_id": "run-20260420T100200Z",
            "workload_type": "direct_kata_container",
            "sandbox_name": "kata-direct-nydus-lite-sandbox",
            "container_name": "kata-direct-nydus-lite-container",
            "namespace": "default",
            "runtime_handler": "kata",
            "hypervisor": "cloud-hypervisor",
            "source_image": "sealos.hub:5000/pause:3.9",
            "effective_image": "sealos.hub:5000/kata-direct-nydus/sealos.hub-5000-pause-3.9:nydus-lite",
            "expected_snapshotter": "nydus",
            "expected_kata_config_path": "/tmp/configuration-clh-nydus.toml",
            "t_request_sent": "2026-04-20T10:02:00.000000Z",
        }
        inspectp = {
            "status": {
                "id": "sandbox-nydus-5678",
                "metadata": {
                    "name": "kata-direct-nydus-lite-sandbox",
                    "uid": "sandbox-uid-5678",
                    "namespace": "default",
                },
                "createdAt": "2026-04-20T10:02:00.100000Z",
            },
            "info": {
                "image": "sealos.hub:5000/kata-direct-nydus/pause:nydus-lite",
                "snapshotter": "nydus",
                "runtimeOptions": {
                    "config_path": "/tmp/configuration-clh-nydus.toml"
                },
            },
        }
        inspect = {
            "status": {
                "id": "container-nydus-5678",
                "startedAt": "2026-04-20T10:02:01.000000Z",
                "image": {
                    "image": "sealos.hub:5000/kata-direct-nydus/pause:nydus-lite",
                },
            },
            "info": {
                "snapshotter": "nydus",
                "runtimeOptions": {
                    "config_path": "/tmp/configuration-clh-nydus.toml"
                },
                "config": {
                    "image": {
                        "image": "sealos.hub:5000/kata-direct-nydus/sealos.hub-5000-pause-3.9:nydus-lite"
                    }
                },
            },
        }
        containerd_log = """
2026-04-20T18:02:00.200000+0800 host containerd[1]: time="2026-04-20T18:02:00.200000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-direct-nydus-lite-sandbox,Uid:sandbox-uid-5678,Namespace:default,Attempt:0,}"
2026-04-20T18:02:00.210000+0800 host containerd[1]: time="2026-04-20T18:02:00.210000+08:00" level=info msg="starting nydusd" image="sealos.hub:5000/kata-direct-nydus/sealos.hub-5000-pause-3.9:nydus-lite"
2026-04-20T18:02:00.230000+0800 host containerd[1]: time="2026-04-20T18:02:00.230000+08:00" level=info msg="nydusd started" image="sealos.hub:5000/kata-direct-nydus/sealos.hub-5000-pause-3.9:nydus-lite"
2026-04-20T18:02:00.260000+0800 host containerd[1]: time="2026-04-20T18:02:00.260000+08:00" level=info path=/opt/kata/bin/cloud-hypervisor sandbox=sandbox-nydus-5678
2026-04-20T18:02:00.620000+0800 host containerd[1]: time="2026-04-20T18:02:00.620000+08:00" level=info msg="VM started" sandbox=sandbox-nydus-5678
2026-04-20T18:02:00.830000+0800 host containerd[1]: time="2026-04-20T18:02:00.830000+08:00" level=info msg="Agent started in the sandbox" sandbox=sandbox-nydus-5678
2026-04-20T18:02:00.880000+0800 host containerd[1]: time="2026-04-20T18:02:00.880000+08:00" level=info msg="RunPodSandbox for &PodSandboxMetadata{Name:kata-direct-nydus-lite-sandbox,Uid:sandbox-uid-5678,Namespace:default,Attempt:0,} returns sandbox id \\"sandbox-nydus-5678\\""
2026-04-20T18:02:00.900000+0800 host containerd[1]: time="2026-04-20T18:02:00.900000+08:00" level=info msg="CreateContainer within sandbox \\"sandbox-nydus-5678\\" for container &ContainerMetadata{Name:kata-direct-nydus-lite-container,Attempt:0,}"
2026-04-20T18:02:00.970000+0800 host containerd[1]: time="2026-04-20T18:02:00.970000+08:00" level=info msg="CreateContainer within sandbox \\"sandbox-nydus-5678\\" for &ContainerMetadata{Name:kata-direct-nydus-lite-container,Attempt:0,} returns container id \\"container-nydus-5678\\""
2026-04-20T18:02:00.980000+0800 host containerd[1]: time="2026-04-20T18:02:00.980000+08:00" level=info msg="StartContainer for \\"container-nydus-5678\\""
2026-04-20T18:02:00.990000+0800 host containerd[1]: time="2026-04-20T18:02:00.990000+08:00" level=info msg="Container is started" container=container-nydus-5678 sandbox=sandbox-nydus-5678
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
        (run_dir / "logs" / "nydus-snapshotter.log").write_text("", encoding="utf-8")

        parsed = parse_direct_nydus_kata_latency.parse_run_dir(run_dir)

        self.assertTrue(parsed["validation_effective_image_matches_request"])
        self.assertTrue(parsed["validation_nydus_log_seen"])
        self.assertEqual(parsed["effective_image_runtime"], "sealos.hub:5000/kata-direct-nydus/pause:nydus-lite")

    def test_parse_run_dir_marks_validation_failures(self):
        run_dir = pathlib.Path(tempfile.mkdtemp(prefix="kata-direct-nydus-lite-bad-"))
        (run_dir / "raw").mkdir()
        (run_dir / "logs").mkdir()
        (run_dir / "summary").mkdir()

        request = {
            "run_id": "run-20260420T100100Z",
            "workload_type": "direct_kata_container",
            "sandbox_name": "bad-sandbox",
            "container_name": "bad-container",
            "namespace": "default",
            "runtime_handler": "kata",
            "hypervisor": "cloud-hypervisor",
            "source_image": "busybox:latest",
            "effective_image": "localhost/kata-direct-nydus/busybox:converted",
            "expected_snapshotter": "nydus",
            "t_request_sent": "2026-04-20T10:01:00.000000Z",
        }
        inspectp = {
            "status": {
                "id": "sandbox-bad",
                "metadata": {
                    "name": "bad-sandbox",
                    "uid": "bad-sandbox-uid",
                    "namespace": "default",
                },
                "createdAt": "2026-04-20T10:01:00.100000Z",
            },
            "info": {
                "image": "busybox:latest",
                "snapshotter": "overlayfs",
                "runtimeOptions": {
                    "config_path": "/opt/kata/share/defaults/kata-containers/configuration-qemu.toml"
                },
            },
        }
        inspect = {
            "status": {
                "id": "container-bad",
                "startedAt": "2026-04-20T10:01:00.500000Z",
                "image": {"image": "busybox:latest"},
            },
            "info": {
                "snapshotter": "overlayfs",
                "runtimeOptions": {
                    "config_path": "/opt/kata/share/defaults/kata-containers/configuration-qemu.toml"
                },
                "config": {"image": {"image": "busybox:latest"}},
            },
        }

        (run_dir / "raw" / "request.json").write_text(
            json.dumps(request), encoding="utf-8"
        )
        (run_dir / "raw" / "inspectp.json").write_text(
            json.dumps(inspectp), encoding="utf-8"
        )
        (run_dir / "raw" / "inspect.json").write_text(
            json.dumps(inspect), encoding="utf-8"
        )
        (run_dir / "logs" / "containerd.log").write_text("", encoding="utf-8")
        (run_dir / "logs" / "nydus-snapshotter.log").write_text(
            "", encoding="utf-8"
        )

        parsed = parse_direct_nydus_kata_latency.parse_run_dir(run_dir)

        self.assertFalse(parsed["validation_snapshotter_is_nydus"])
        self.assertFalse(parsed["validation_kata_config_is_clh"])
        self.assertFalse(parsed["validation_effective_image_matches_request"])
        self.assertFalse(parsed["validation_nydus_log_seen"])


if __name__ == "__main__":
    unittest.main()
