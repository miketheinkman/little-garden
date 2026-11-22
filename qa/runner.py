from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import connections
from django.test.runner import DiscoverRunner


class GardenTestRunner(DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        if not any(label.startswith("qa") for label in test_labels or ()):
            return super().run_tests(test_labels, **kwargs)
        # Parent and child browser requests must use separate SQLite connections.
        config = connections["default"].settings_dict["TEST"]
        original = config["NAME"]
        with TemporaryDirectory(prefix="little-garden-qa-") as path:
            config["NAME"] = str(Path(path) / "household.sqlite3")
            try:
                return super().run_tests(test_labels, **kwargs)
            finally:
                config["NAME"] = original
