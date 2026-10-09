"""Protect process-local installation and upstream CLI configuration forwarding."""

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class LaunchTests(unittest.TestCase):
    """Require an importable factory rather than parent-only state inheritance."""

    def test_factory_installs_before_importing_upstream_application(self) -> None:
        factory = importlib.import_module("stackgen_docling.app")
        events = []
        application = object()

        def upstream_factory() -> object:
            events.append("create")
            return application

        original_import = __import__

        def check_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "docling_serve.app":
                self.assertEqual(events, ["install"])
                events.append("import")
            return original_import(name, *args, **kwargs)

        with (
            patch.object(
                factory, "install", side_effect=lambda: events.append("install")
            ),
            patch.dict(
                "sys.modules",
                {"docling_serve.app": SimpleNamespace(create_app=upstream_factory)},
            ),
            patch("builtins.__import__", side_effect=check_import),
        ):
            self.assertIs(factory.create_app(), application)
        self.assertEqual(events, ["install", "import", "create"])

    def test_cli_redirects_only_factory_and_preserves_worker_reload_ssl_options(
        self,
    ) -> None:
        launcher = importlib.import_module("stackgen_docling.__main__")
        options = {
            "app": "docling_serve.app:create_app",
            "factory": True,
            "workers": 2,
            "reload": False,
            "host": "127.0.0.1",
            "port": 5123,
            "root_path": "/convert",
            "ssl_certfile": "certificate.pem",
            "log_config": None,
        }
        upstream = SimpleNamespace(uvicorn=SimpleNamespace())

        def cli() -> None:
            upstream.uvicorn.run(**options)

        upstream.app = cli
        original_runner = upstream.uvicorn
        with (
            patch.object(launcher, "install"),
            patch.object(launcher.uvicorn, "run") as run,
            patch.dict("sys.modules", {"docling_serve.__main__": upstream}),
        ):
            launcher.main()
        run.assert_called_once_with(
            **{**options, "app": "stackgen_docling.app:create_app"}
        )
        self.assertIs(upstream.uvicorn, original_runner)


if __name__ == "__main__":
    unittest.main()
