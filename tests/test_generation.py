import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wanstudio.generation import run_batch
from wanstudio.models import Scene
from wanstudio.settings import Settings
from wanstudio.store import ProjectStore


class GenerationTests(unittest.TestCase):
    @patch("wanstudio.generation.WorkerClient")
    @patch("wanstudio.generation.RunPodV2")
    def test_download_happens_before_terminate(self, runpod_cls, worker_cls):
        with tempfile.TemporaryDirectory() as td:
            store = ProjectStore(Path(td))
            project = store.create("test")
            image = Path(td) / "img.png"; image.write_bytes(b"img")
            scene = Scene(title="Scene 1", motion_prompt="blink", image_path=str(image))
            project.scenes.append(scene); store.save(project)
            events = []
            rp = runpod_cls.return_value
            rp.create_temporary_pod.return_value = {"id": "pod123"}
            rp.wait_running.return_value = {"status": "RUNNING"}
            rp.terminate.side_effect = lambda pod: events.append("terminate")
            worker = worker_cls.return_value
            worker.submit.return_value = "job1"
            worker.wait_job.return_value = {"status": "succeeded"}
            def download(job, dest):
                events.append("download"); Path(dest).write_bytes(b"video"); return dest
            worker.download.side_effect = download
            result = run_batch(store, project, "key", Settings(worker_image="ghcr.io/example/worker:latest"))
            self.assertIn("Generated and downloaded 1", result)
            self.assertEqual(events, ["download", "terminate"])


if __name__ == "__main__":
    unittest.main()
