"""Tests for app/core/utils.py: is_double_jeopardy 3D matching."""

from app.core.utils import is_double_jeopardy


class TestDoubleJeopardy:
    """Test is_double_jeopardy 3D matching (file + snippet + line radius)."""

    def setup_method(self):
        self.check = is_double_jeopardy

    def _issue(self, file="foo.py", line=10, snippet="x = 1"):
        return {"file": file, "approx_line": line, "snippet": snippet}

    def test_exact_match(self):
        assert self.check(self._issue(), [self._issue()])

    def test_snippet_containment(self):
        assert self.check(
            self._issue(snippet="x = 1"),
            [self._issue(snippet="x = 1  # comment")],
        )

    def test_snippet_reverse_containment(self):
        assert self.check(
            self._issue(snippet="x = 1  # comment"),
            [self._issue(snippet="x = 1")],
        )

    def test_within_line_radius(self):
        assert self.check(self._issue(line=12), [self._issue(line=10, snippet="")])

    def test_outside_line_radius(self):
        assert not self.check(self._issue(line=20, snippet=""), [self._issue(line=10, snippet="")])

    def test_different_file(self):
        assert not self.check(self._issue(file="bar.py"), [self._issue(file="foo.py")])

    def test_different_snippet_different_line(self):
        assert not self.check(
            self._issue(file="foo.py", line=50, snippet="y = 2"),
            [self._issue(file="foo.py", line=10, snippet="x = 1")],
        )

    def test_empty_seen(self):
        assert not self.check(self._issue(), [])

    def test_unknown_file(self):
        assert not self.check({"file": "unknown", "approx_line": 1, "snippet": "x"}, [self._issue()])
