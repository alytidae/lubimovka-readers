from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from apps.users.models import User
from apps.competitions.models import Competition, CompetitionRole
from apps.users.forms import CustomUserAddForm, CustomUserChangeForm


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


class TestUserCreateView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Create User Comp", date=date(2026, 1, 1)
        )
        cls.admin_user = User.objects.create_user(
            username="cu_admin", password="pwd", is_superuser=True
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_create_user_and_assign_role(self):
        url = reverse(
            "users:create", kwargs={"competition_slug": self.competition.slug}
        )
        response = self.client.post(
            url,
            {
                "username": "new_reader",
                "role": "reader",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="new_reader").exists())
        self.assertTrue(
            CompetitionRole.objects.filter(
                user__username="new_reader",
                competition=self.competition,
                role="reader",
            ).exists()
        )

    def test_non_admin_cannot_create_user(self):
        reader = User.objects.create_user(username="cu_reader", password="pwd")
        CompetitionRole.objects.create(
            user=reader, competition=self.competition, role="reader"
        )
        self.client.force_login(reader)
        url = reverse(
            "users:create", kwargs={"competition_slug": self.competition.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class TestUserUpdateView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Update User Comp", date=date(2026, 1, 1)
        )
        cls.admin_user = User.objects.create_user(
            username="uu_admin", password="pwd", is_superuser=True
        )
        cls.target_user = User.objects.create_user(username="uu_target", password="pwd")
        CompetitionRole.objects.create(
            user=cls.target_user,
            competition=cls.competition,
            role="reader",
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_admin_can_update_user_role(self):
        url = reverse(
            "users:update",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.target_user.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "username": "uu_target",
                "role": "moderator",
                "role_is_active": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        role = CompetitionRole.objects.get(
            user=self.target_user, competition=self.competition
        )
        self.assertEqual(role.role, "moderator")

    def test_admin_can_deactivate_user_role(self):
        url = reverse(
            "users:update",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.target_user.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "username": "uu_target",
                "role": "reader",
                "role_is_active": False,
            },
        )
        self.assertEqual(response.status_code, 302)
        role = CompetitionRole.objects.get(
            user=self.target_user, competition=self.competition
        )
        self.assertFalse(role.is_active)


class TestUserDetailView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Detail User Comp", date=date(2026, 1, 1)
        )
        cls.admin_user = User.objects.create_user(
            username="ud_admin", password="pwd", is_superuser=True
        )
        cls.reader = User.objects.create_user(username="ud_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.outsider = User.objects.create_user(username="ud_outsider", password="pwd")

    def setUp(self):
        self.client = Client()

    def test_admin_can_see_user_detail(self):
        self.client.force_login(self.admin_user)
        url = reverse(
            "users:detail",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.reader.pk,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_reader_can_see_own_detail(self):
        self.client.force_login(self.reader)
        url = reverse(
            "users:detail",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.reader.pk,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_outsider_cannot_see_user_detail(self):
        self.client.force_login(self.outsider)
        url = reverse(
            "users:detail",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.reader.pk,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class TestUserListView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="List User Comp", date=date(2026, 1, 1)
        )
        cls.admin_user = User.objects.create_user(
            username="ul_admin", password="pwd", is_superuser=True
        )
        cls.reader = User.objects.create_user(username="ul_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.mod = User.objects.create_user(username="ul_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )

    def setUp(self):
        self.client = Client()

    def test_reader_sees_only_moderators(self):
        self.client.force_login(self.reader)
        url = reverse("users:list", kwargs={"competition_slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        visible_usernames = [u.username for u in response.context["object_list"]]
        self.assertNotIn("ul_reader", visible_usernames)
        self.assertIn("ul_mod", visible_usernames)

    def test_admin_sees_all_users(self):
        self.client.force_login(self.admin_user)
        url = reverse("users:list", kwargs={"competition_slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        visible_usernames = [u.username for u in response.context["object_list"]]
        self.assertIn("ul_reader", visible_usernames)
        self.assertIn("ul_mod", visible_usernames)

    def test_moderator_sees_all_users(self):
        self.client.force_login(self.mod)
        url = reverse("users:list", kwargs={"competition_slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        visible_usernames = [u.username for u in response.context["object_list"]]
        self.assertIn("ul_reader", visible_usernames)
        self.assertIn("ul_mod", visible_usernames)


class TestModeratorInviteRestrictions(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Mod Invite Comp", date=date(2026, 1, 1)
        )
        cls.mod = User.objects.create_user(username="mi_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="mi_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )

    def setUp(self):
        self.client = Client()

    def test_moderator_can_invite(self):
        self.client.force_login(self.mod)
        url = reverse(
            "users:invite", kwargs={"competition_slug": self.competition.slug}
        )
        response = self.client.post(url, {"username": "mi_reader", "role": "reader"})
        self.assertEqual(response.status_code, 302)

    def test_reader_cannot_invite(self):
        self.client.force_login(self.reader)
        url = reverse(
            "users:invite", kwargs={"competition_slug": self.competition.slug}
        )
        response = self.client.post(url, {"username": "anyone", "role": "reader"})
        self.assertEqual(response.status_code, 403)


class TestCustomUserChangeForm(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="ChangeForm Comp", date=date(2026, 1, 1)
        )
        cls.target = User.objects.create_user(username="cf_target", password="pwd")
        CompetitionRole.objects.create(
            user=cls.target, competition=cls.competition, role="reader"
        )

    def test_form_with_moderator_editor_restricts_role_choices(self):
        form = CustomUserChangeForm(
            data={
                "username": "cf_target",
                "role": "reader",
                "role_is_active": True,
            },
            editor_role="moderator",
            current_role="reader",
            current_role_is_active=True,
        )
        self.assertEqual(form.fields["role"].choices, [("reader", _("Reader"))])

    def test_form_with_admin_editor_has_all_roles(self):
        form = CustomUserChangeForm(
            data={
                "username": "cf_target",
                "role": "moderator",
                "role_is_active": True,
            },
            editor_role="admin",
            current_role="reader",
            current_role_is_active=True,
        )
        self.assertEqual(len(form.fields["role"].choices), 3)

    def test_form_initial_values_set(self):
        form = CustomUserChangeForm(
            data={
                "username": "cf_target",
                "role": "reader",
                "role_is_active": False,
            },
            editor_role="admin",
            current_role="reader",
            current_role_is_active=False,
        )
        self.assertEqual(form.fields["role"].initial, "reader")
        self.assertEqual(form.fields["role_is_active"].initial, False)


class TestCustomUserAddFormModeratorRestriction(TestCase):
    def test_moderator_creator_only_sees_reader_role(self):
        form = CustomUserAddForm(
            data={
                "username": "mod_created_user",
                "role": "reader",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
            creator_role="moderator",
        )
        self.assertEqual(form.fields["role"].choices, [("reader", _("Reader"))])

    def test_admin_creator_sees_all_roles(self):
        form = CustomUserAddForm(
            data={
                "username": "admin_created_user",
                "role": "admin",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
            creator_role="admin",
        )
        self.assertEqual(len(form.fields["role"].choices), 3)


class TestUserUpdateViewModeratorRestrictions(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="ModRestr Comp", date=date(2026, 1, 1)
        )
        cls.mod = User.objects.create_user(username="mr_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="mr_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.other_mod = User.objects.create_user(username="mr_mod2", password="pwd")
        CompetitionRole.objects.create(
            user=cls.other_mod, competition=cls.competition, role="moderator"
        )
        cls.role_admin = User.objects.create_user(username="mr_admin", password="pwd")
        CompetitionRole.objects.create(
            user=cls.role_admin, competition=cls.competition, role="admin"
        )

    def setUp(self):
        self.client = Client()

    def test_moderator_can_edit_reader(self):
        self.client.force_login(self.mod)
        url = reverse(
            "users:update",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.reader.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "username": "mr_reader",
                "role": "reader",
                "role_is_active": False,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_moderator_can_edit_self(self):
        self.client.force_login(self.mod)
        url = reverse(
            "users:update",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.mod.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "username": "mr_mod",
                "role": "reader",
                "role_is_active": True,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_moderator_cannot_edit_other_moderator(self):
        self.client.force_login(self.mod)
        url = reverse(
            "users:update",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.other_mod.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "username": "mr_mod2",
                "role": "moderator",
                "role_is_active": True,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_moderator_cannot_edit_admin(self):
        self.client.force_login(self.mod)
        url = reverse(
            "users:update",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.role_admin.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "username": "mr_admin",
                "role": "admin",
                "role_is_active": True,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_reader_cannot_edit_user(self):
        reader = User.objects.create_user(username="mr_reader2", password="pwd")
        CompetitionRole.objects.create(
            user=reader, competition=self.competition, role="reader"
        )
        self.client.force_login(reader)
        url = reverse(
            "users:update",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.reader.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "username": "mr_reader",
                "role": "reader",
                "role_is_active": True,
            },
        )
        self.assertEqual(response.status_code, 403)


class TestUserCreateViewRoleAdmin(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="ModCreate Comp", date=date(2026, 1, 1)
        )
        cls.role_admin = User.objects.create_user(username="mc_admin", password="pwd")
        CompetitionRole.objects.create(
            user=cls.role_admin, competition=cls.competition, role="admin"
        )
        cls.mod = User.objects.create_user(username="mc_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )

    def setUp(self):
        self.client = Client()

    def test_role_admin_can_create_user(self):
        self.client.force_login(self.role_admin)
        url = reverse(
            "users:create", kwargs={"competition_slug": self.competition.slug}
        )
        response = self.client.post(
            url,
            {
                "username": "mc_new_reader",
                "role": "reader",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="mc_new_reader").exists())
        self.assertTrue(
            CompetitionRole.objects.filter(
                user__username="mc_new_reader",
                competition=self.competition,
                role="reader",
            ).exists()
        )

    def test_moderator_cannot_create_user(self):
        self.client.force_login(self.mod)
        url = reverse(
            "users:create", kwargs={"competition_slug": self.competition.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class TestUserGetRole(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="GetRole Comp", date=date(2026, 1, 1)
        )
        cls.superuser = User.objects.create_user(
            username="gr_super", password="pwd", is_superuser=True
        )
        cls.reader = User.objects.create_user(username="gr_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.inactive_reader = User.objects.create_user(
            username="gr_inactive", password="pwd"
        )
        CompetitionRole.objects.create(
            user=cls.inactive_reader,
            competition=cls.competition,
            role="reader",
            is_active=False,
        )
        cls.outsider = User.objects.create_user(username="gr_outsider", password="pwd")

    def test_superuser_gets_admin_role(self):
        self.assertEqual(self.superuser.get_role(self.competition), "admin")

    def test_active_reader_gets_reader_role(self):
        self.assertEqual(self.reader.get_role(self.competition), "reader")

    def test_inactive_role_returns_none(self):
        self.assertIsNone(self.inactive_reader.get_role(self.competition))

    def test_no_role_returns_none(self):
        self.assertIsNone(self.outsider.get_role(self.competition))

    def test_moderator_gets_moderator_role(self):
        mod = User.objects.create_user(username="gr_mod", password="pwd")
        CompetitionRole.objects.create(
            user=mod, competition=self.competition, role="moderator"
        )
        self.assertEqual(mod.get_role(self.competition), "moderator")
