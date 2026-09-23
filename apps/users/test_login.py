from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class LoginVersionTest(SimpleTestCase):
    @override_settings(APP_COMMIT_SHA="abc1234", APP_COMMIT_DATE="2026-09-23")
    def test_login_displays_deployed_commit_version(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, "2026-09-23")
        self.assertContains(response, "abc1234")

    @override_settings(APP_COMMIT_SHA="", APP_COMMIT_DATE="")
    def test_login_hides_version_without_build_metadata(self):
        response = self.client.get(reverse("login"))

        self.assertNotContains(response, "Version:")
