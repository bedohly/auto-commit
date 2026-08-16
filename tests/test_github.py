"""Offline tests for the GitHub client helpers and commit messages."""

import io
import random
import unittest
import urllib.error

from autocommit import github, messages


class RepoParsingTests(unittest.TestCase):
    def test_repo_fields(self):
        repo = github._to_repo({
            "name": "activity-log",
            "owner": {"login": "octocat"},
            "default_branch": "trunk",
            "private": True,
            "fork": False,
            "permissions": {"push": True},
            "pushed_at": "2026-08-01T10:00:00Z",
        })
        self.assertEqual(repo.full_name, "octocat/activity-log")
        self.assertEqual(repo.default_branch, "trunk")
        self.assertTrue(repo.private)
        self.assertTrue(repo.can_push)

    def test_missing_default_branch_falls_back_to_main(self):
        repo = github._to_repo({"name": "x", "owner": {"login": "y"}})
        self.assertEqual(repo.default_branch, "main")

    def test_read_only_repository(self):
        repo = github._to_repo({"name": "x", "owner": {"login": "y"},
                                "permissions": {"push": False}})
        self.assertFalse(repo.can_push)


class UserTests(unittest.TestCase):
    def test_noreply_email(self):
        user = github.User(login="octocat", id=583231, name="The Octocat")
        self.assertEqual(user.noreply_email, "583231+octocat@users.noreply.github.com")
        self.assertEqual(user.display_name, "The Octocat")

    def test_display_name_falls_back_to_login(self):
        self.assertEqual(github.User(login="ghost", id=1).display_name, "ghost")


class PaginationTests(unittest.TestCase):
    def test_next_link_is_extracted(self):
        header = ('<https://api.github.com/user/repos?page=2>; rel="next", '
                  '<https://api.github.com/user/repos?page=9>; rel="last"')
        self.assertEqual(github._next_link(header),
                         "https://api.github.com/user/repos?page=2")

    def test_no_next_link(self):
        self.assertEqual(github._next_link(""), "")
        self.assertEqual(
            github._next_link('<https://api.github.com/user/repos?page=1>; rel="prev"'), "")


class ErrorMessageTests(unittest.TestCase):
    def _error(self, code, body=b'{"message": "Bad credentials"}'):
        return urllib.error.HTTPError(
            url="https://api.github.com/user", code=code, msg="err",
            hdrs=None, fp=io.BytesIO(body),
        )

    def test_401_is_explained(self):
        self.assertIn("token", github._describe_http_error(self._error(401)).lower())

    def test_404_is_explained(self):
        self.assertIn("404", github._describe_http_error(self._error(404)))

    def test_rate_limit_is_explained(self):
        error = self._error(403, b'{"message": "API rate limit exceeded"}')
        self.assertIn("rate limit", github._describe_http_error(error).lower())

    def test_client_requires_a_token(self):
        with self.assertRaises(github.GitHubError):
            github.GitHubClient("")


class MessageTests(unittest.TestCase):
    def test_casual_messages_come_from_the_pool(self):
        rng = random.Random(1)
        for _ in range(50):
            self.assertIn(messages.build(rng, "casual"), messages.CASUAL)

    def test_conventional_messages_are_prefixed(self):
        rng = random.Random(2)
        prefixes = tuple(kind + ": " for kind, _ in messages.CONVENTIONAL_TYPES)
        for _ in range(50):
            self.assertTrue(messages.build(rng, "conventional").startswith(prefixes))

    def test_mixed_uses_both_styles(self):
        rng = random.Random(3)
        produced = {messages.build(rng, "mixed") for _ in range(200)}
        casual = [text for text in produced if text in messages.CASUAL]
        conventional = [text for text in produced if ": " in text]
        self.assertTrue(casual)
        self.assertTrue(conventional)

    def test_unknown_style_falls_back_to_mixed(self):
        self.assertTrue(messages.build(random.Random(4), "nonsense"))


if __name__ == "__main__":
    unittest.main()
