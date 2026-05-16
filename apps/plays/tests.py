from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from apps.users.models import User
from apps.competitions.models import Competition, CompetitionRole
from apps.plays.models import Play
from apps.reviews.models import Review


class TestPlayVisibilityAndActions(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Test Visibility",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
            are_phase1_reviews_visible=False,
        )

        cls.reader = User.objects.create_user(username="reader", password="pwd")
        cls.mod = User.objects.create_user(username="mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )

        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Hidden Play",
            author_email="a@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_reader_cannot_see_unassigned_play_in_list(self):
        self.client.force_login(self.reader)
        url = reverse("plays:list", kwargs={"competition_slug": self.competition.slug})
        response = self.client.get(url)
        self.assertNotIn(self.play, response.context["object_list"])

    def test_moderator_sees_all_plays_in_list(self):
        self.client.force_login(self.mod)
        url = reverse("plays:list", kwargs={"competition_slug": self.competition.slug})
        response = self.client.get(url)
        self.assertIn(self.play, response.context["object_list"])

    def test_reader_cannot_activate_play(self):
        self.client.force_login(self.reader)
        url = reverse(
            "plays:activate",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_moderator_can_deactivate_play(self):
        self.client.force_login(self.mod)
        url = reverse(
            "plays:deactivate",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        self.client.post(url)
        self.play.refresh_from_db()
        self.assertFalse(self.play.is_active)


class TestForcePhase2Views(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Force P2 Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.admin = User.objects.create_user(
            username="fp2_admin", password="pwd", is_superuser=True
        )
        cls.role_admin = User.objects.create_user(username="fp2_radm", password="pwd")
        CompetitionRole.objects.create(
            user=cls.role_admin, competition=cls.competition, role="admin"
        )
        cls.mod = User.objects.create_user(username="fp2_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="fp2_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Force P2 Play",
            author_email="fp2@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_superuser_can_force_phase_2(self):
        self.client.force_login(self.admin)
        url = reverse(
            "plays:force-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse(
                "plays:detail",
                kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
            ),
        )
        self.play.refresh_from_db()
        self.assertTrue(self.play.force_phase_2)

    def test_role_admin_can_force_phase_2(self):
        self.client.force_login(self.role_admin)
        url = reverse(
            "plays:force-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertTrue(self.play.force_phase_2)

    def test_moderator_cannot_force_phase_2(self):
        self.client.force_login(self.mod)
        url = reverse(
            "plays:force-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.play.refresh_from_db()
        self.assertFalse(self.play.force_phase_2)

    def test_reader_cannot_force_phase_2(self):
        self.client.force_login(self.reader)
        url = reverse(
            "plays:force-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.play.refresh_from_db()
        self.assertFalse(self.play.force_phase_2)

    def test_admin_can_unforce_phase_2(self):
        self.play.force_phase_2 = True
        self.play.save()
        self.client.force_login(self.admin)
        url = reverse(
            "plays:unforce-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertFalse(self.play.force_phase_2)

    def test_cannot_force_phase_2_during_phase_2(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        self.client.force_login(self.admin)
        url = reverse(
            "plays:force-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertFalse(self.play.force_phase_2)

    def test_cannot_force_phase_2_during_setup(self):
        self.competition.status = Competition.Status.SETUP
        self.competition.save()
        self.client.force_login(self.admin)
        url = reverse(
            "plays:force-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertFalse(self.play.force_phase_2)

    def test_cannot_force_phase_2_when_finished(self):
        self.competition.status = Competition.Status.FINISHED
        self.competition.save()
        self.client.force_login(self.admin)
        url = reverse(
            "plays:force-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertFalse(self.play.force_phase_2)
