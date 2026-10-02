import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from wanstudio.models import Scene
from wanstudio.runpod import RunPodV2
from wanstudio.store import ProjectStore


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload; self.status_code = status; self.ok = 200 <= status < 300; self.content = b"{}"
    def json(self): return self._payload


class CoreTests(unittest.TestCase):
    def test_scene_mode_switches_for_dialogue_or_audio(self):
        scene = Scene()
        self.assertEqual(scene.mode, "wan22_lightning")
        scene.dialogue = "Hello"
        self.assertEqual(scene.mode, "wan22_s2v")
        scene.dialogue = ""; scene.audio_path = "voice.wav"
        self.assertEqual(scene.mode, "wan22_s2v")

    def test_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            store = ProjectStore(Path(td))
            project = store.create("My Movie")
            project.scenes.append(Scene(title="Intro", motion_prompt="slow zoom"))
            store.save(project)
            loaded = store.load("My_Movie")
            self.assertEqual(loaded.scenes[0].motion_prompt, "slow zoom")

    def test_runpod_create_uses_ephemeral_disk_and_no_mount(self):
        client = RunPodV2("secret")
        calls = []
        def request(method, url, timeout, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse({"id": "pod123", "status": "PROVISIONING"}, 201)
        client.session.request = request
        result = client.create_temporary_pod(
            image="ghcr.io/example/wan-studio-worker:latest",
            gpu_id="NVIDIA A100 80GB PCIe",
            cloud="COMMUNITY",
            disk_gb=200,
            worker_token="token",
            idle_exit_seconds=900,
        )
        self.assertEqual(result["id"], "pod123")
        body = calls[0][2]["json"]
        self.assertEqual(body["disk"], 200)
        self.assertEqual(body["mounts"], {})
        self.assertEqual(body["ports"], ["8000/http"])
        self.assertNotIn("volume", body)


if __name__ == "__main__":
    unittest.main()
