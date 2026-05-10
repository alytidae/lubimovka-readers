from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from apps.users.models import User
from apps.competitions.models import Competition, CompetitionRole
from apps.users.forms import CustomUserAddForm


class TestUserManagementAndForms(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Manage Comp", date=date(2026, 1, 1)
        )

        cls.admin_user = User.objects.create_user(
            username="admin", password="pwd", is_superuser=True
        )
        cls.existing_reader = User.objects.create_user(
            username="exists", password="pwd"
        )

    def setUp(self):
        self.client = Client()

    def test_invite_existing_user_adds_role_automatically(self):
        self.client.force_login(self.admin_user)
        url = reverse(
            "users:invite", kwargs={"competition_slug": self.competition.slug}
        )

        response = self.client.post(url, {"username": "exists", "role": "reader"})
        self.assertRedirects(
            response,
            reverse("users:list", kwargs={"competition_slug": self.competition.slug}),
        )

        has_role = CompetitionRole.objects.filter(
            user=self.existing_reader, competition=self.competition, role="reader"
        ).exists()
        self.assertTrue(has_role)

    def test_invite_new_user_redirects_to_create_form(self):
        self.client.force_login(self.admin_user)
        url = reverse(
            "users:invite", kwargs={"competition_slug": self.competition.slug}
        )

        response = self.client.post(url, {"username": "new_user", "role": "reader"})

        expected_url = (
            reverse("users:create", kwargs={"competition_slug": self.competition.slug})
            + "?username=new_user&role=reader"
        )
        self.assertRedirects(response, expected_url)

    def test_user_creation_form_passwords_must_match(self):
        form = CustomUserAddForm(
            data={
                "username": "new_user",
                "role": "reader",
                "password": "password123",
                "password_confirm": "password456",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password_confirm", form.errors)

    def test_user_creation_form_rejects_existing_username(self):
        form = CustomUserAddForm(
            data={
                "username": "exists",
                "role": "reader",
                "password": "password123",
                "password_confirm": "password123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)
