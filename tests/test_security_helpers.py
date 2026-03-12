import pytest

from app.security import is_api_path


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api", True),
        ("/api/", True),
        ("/api/save-subscription", True),
        ("/api/v1/status", True),
        ("/dashboard", False),
        ("/admin/logs", False),
        ("/apis", False),
        ("/API", False),
        ("api", False),
        ("", False),
    ],
)
def test_is_api_path_cases(path: str, expected: bool):
    assert is_api_path(path) is expected
