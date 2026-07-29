import unittest

from scripts.build_ankiaddon import iter_package_files


class TestIterPackageFiles(unittest.TestCase):
    def test_excludes_test_doubles_from_package(self) -> None:
        """Test doubles (MockClient/MockTransport) are for tests/ only and
        must never ship inside the distributed .ankiaddon."""
        arcnames = [arcname for _source, arcname in iter_package_files()]
        mock_entries = [name for name in arcnames if "mocks" in name.split("/")]
        self.assertEqual(mock_entries, [])

    def test_still_includes_the_rest_of_the_package(self) -> None:
        arcnames = [arcname for _source, arcname in iter_package_files()]
        self.assertIn("ankiminder/addon.py", arcnames)
        self.assertIn("manifest.json", arcnames)


if __name__ == "__main__":
    unittest.main()
