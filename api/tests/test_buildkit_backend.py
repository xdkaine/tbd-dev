import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("backend", Path(__file__).parents[1] / "app/services/buildkit_backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def fixture(path):
    with tarfile.open(path, "w") as tf:
        for name, data in {"index.json": {"manifests": [{"digest": "sha256:" + "a" * 64}]},
                           "blobs/sha256/" + "a" * 64: {"config": {"digest": "sha256:" + "b" * 64}, "layers": [{"size": 42}]}}.items():
            content = json.dumps(data).encode()
            info = tarfile.TarInfo(name); info.size = len(content)
            tf.addfile(info, io.BytesIO(content))


class BackendTests(unittest.TestCase):
    def test_context_and_external_dockerfile(self):
        with patch.dict(os.environ, {"BUILDKIT_HOST": "tcp://buildkit:1234"}):
            cmd = backend.build_command("/repo", "web", "infra/Dockerfile.prod", "/out.tar", {"tbd.build": "id"})
        self.assertIn("context=/repo/web", cmd)
        self.assertIn("dockerfile=/repo/infra", cmd)
        self.assertIn("filename=Dockerfile.prod", cmd)
        self.assertIn("--tlscacert", cmd)

    def test_reject_outside_context(self):
        with self.assertRaises(ValueError):
            backend.build_command("/repo", "../secret", None, "/out", {})

    def test_identity(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.tar"; fixture(path)
            self.assertEqual(backend.archive_identity(path), ("sha256:" + "b" * 64, 42))

    def test_two_tags_no_credentials_in_arguments_and_cleanup(self):
        calls = []; auth_paths = []
        async def run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "buildctl":
                output = next(x for x in cmd if x.startswith("type=oci,dest="))[14:]
                fixture(output)
            else:
                authfile = Path(cmd[cmd.index("--authfile") + 1]); auth_paths.append(authfile)
                self.assertEqual(authfile.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("secret-password", " ".join(cmd))
            return 0, ""
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"BUILDKIT_HOST": "tcp://buildkit:1234"}):
            result = asyncio.run(backend.build_and_publish(run, repo_dir=td, context=".", dockerfile=None,
                image_tag="registry/test:abc", latest_tag="registry/test:latest", labels={},
                registry_url="https://registry", username="user", password="secret-password", log_lines=[]))
        self.assertEqual(len(calls), 3)
        self.assertNotIn("--dest-tls-verify=false", calls[1])
        self.assertTrue(all(not p.exists() for p in auth_paths))
        self.assertEqual(result[1], 42)

    def test_latest_push_failure_is_not_success(self):
        calls = []
        async def run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "buildctl":
                fixture(next(x for x in cmd if x.startswith("type=oci,dest="))[14:])
            elif cmd[-1].endswith(":latest"):
                return 1, "denied"
            return 0, ""
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"BUILDKIT_HOST": "tcp://buildkit:1234"}):
            with self.assertRaisesRegex(RuntimeError, "Registry push failed"):
                asyncio.run(backend.build_and_publish(run, repo_dir=td, context=".", dockerfile=None,
                    image_tag="registry/test:abc", latest_tag="registry/test:latest", labels={},
                    registry_url="http://registry", username="user", password="pw", log_lines=[]))
        self.assertEqual(len(calls), 3)
        self.assertIn("--dest-tls-verify=false", calls[1])

    def test_build_failure_does_not_publish(self):
        calls = []
        async def run(cmd, **kwargs):
            calls.append(cmd); return 1, "failed"
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"BUILDKIT_HOST": "tcp://buildkit:1234"}):
            with self.assertRaises(RuntimeError):
                asyncio.run(backend.build_and_publish(run, repo_dir=td, context=".", dockerfile=None,
                    image_tag="registry/test:abc", latest_tag="registry/test:latest", labels={},
                    registry_url="https://registry", username="user", password="pw", log_lines=[]))
        self.assertEqual(len(calls), 1)

class CredentialLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_pull_auth_exists_before_build_and_is_scoped(self):
        configs = []
        async def run(cmd, **kwargs):
            if cmd[0] == "buildctl":
                config_dir = Path(kwargs["env"]["DOCKER_CONFIG"])
                configs.append(config_dir)
                self.assertEqual(config_dir.stat().st_mode & 0o777, 0o700)
                config = config_dir / "config.json"
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                self.assertEqual(set(json.loads(config.read_text())["auths"]), {"10.128.30.57:4044"})
                self.assertFalse(config_dir.is_relative_to(Path(kwargs["cwd"])))
                self.assertNotIn("private-password", " ".join(cmd))
                self.assertEqual(set(kwargs["env"]), {"DOCKER_CONFIG"})
                fixture(next(x for x in cmd if x.startswith("type=oci,dest="))[14:])
            else:
                self.assertEqual(Path(cmd[cmd.index("--authfile")+1]).parent, configs[0])
            return 0, ""
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"BUILDKIT_HOST": "tcp://buildkit:1234", "DOCKER_CONFIG": "original"}):
            await backend.build_and_publish(run, repo_dir=td, context=".", dockerfile=None,
                image_tag="10.128.30.57:4044/test:abc", latest_tag="10.128.30.57:4044/test:latest", labels={},
                registry_url="http://10.128.30.57:4044", username="user", password="private-password", log_lines=[])
            self.assertEqual(os.environ["DOCKER_CONFIG"], "original")
        self.assertTrue(all(not path.exists() for path in configs))

    async def test_auth_cleanup_on_build_failure_exception_and_cancellation(self):
        for failure in ("exit", "exception", "cancel"):
            configs = []
            async def run(cmd, **kwargs):
                configs.append(Path(kwargs["env"]["DOCKER_CONFIG"]))
                self.assertTrue((configs[0]/"config.json").is_file())
                if failure == "exception": raise OSError("subprocess unavailable")
                if failure == "cancel": raise asyncio.CancelledError()
                return 1, "failed"
            error = asyncio.CancelledError if failure == "cancel" else OSError if failure == "exception" else RuntimeError
            with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"BUILDKIT_HOST": "tcp://buildkit:1234"}):
                with self.assertRaises(error):
                    await backend.build_and_publish(run, repo_dir=td, context=".", dockerfile=None,
                        image_tag="registry/test:abc", latest_tag="registry/test:latest", labels={},
                        registry_url="https://registry", username="user", password="private-password", log_lines=[])
            self.assertEqual(len(configs), 1)
            self.assertFalse(configs[0].exists())

if __name__ == "__main__": unittest.main()
