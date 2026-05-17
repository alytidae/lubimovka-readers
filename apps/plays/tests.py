from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.db import IntegrityError
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

    def test_moderator_cannot_unforce_phase_2(self):
        self.play.force_phase_2 = True
        self.play.save()
        self.client.force_login(self.mod)
        url = reverse(
            "plays:unforce-phase-2",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.play.refresh_from_db()
        self.assertTrue(self.play.force_phase_2)

    def test_cannot_force_phase_2_outside_phase_1(self):
        for status in [
            Competition.Status.PHASE_2,
            Competition.Status.SETUP,
            Competition.Status.FINISHED,
        ]:
            self.play.refresh_from_db()
            self.play.force_phase_2 = False
            self.play.save()
            self.competition.status = status
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


class TestPlayIsAuthorOver45(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Age Comp",
            date=date(2026, 1, 1),
        )

    def test_author_over_45(self):
        play = Play.objects.create(
            competition=self.competition,
            title="Old Play",
            author_email="old@a.com",
            author_first_name="Old",
            author_year_of_birth=1970,
        )
        self.assertTrue(play.is_author_over_45)

    def test_author_under_45(self):
        play = Play.objects.create(
            competition=self.competition,
            title="Young Play",
            author_email="young@a.com",
            author_first_name="Young",
            author_year_of_birth=2000,
        )
        self.assertFalse(play.is_author_over_45)

    def test_author_no_year_returns_false(self):
        play = Play.objects.create(
            competition=self.competition,
            title="No Year Play",
            author_email="noyear@a.com",
            author_first_name="Unknown",
        )
        self.assertFalse(play.is_author_over_45)


class TestPlayActivateAdminAndModerator(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Activate Comp",
            date=date(2026, 1, 1),
        )
        cls.admin = User.objects.create_user(
            username="act_admin", password="pwd", is_superuser=True
        )
        cls.mod = User.objects.create_user(username="act_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Inactive Play",
            author_email="act@a.com",
            is_active=False,
        )

    def setUp(self):
        self.client = Client()

    def test_admin_can_activate_play(self):
        self.client.force_login(self.admin)
        url = reverse(
            "plays:activate",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertTrue(self.play.is_active)

    def test_moderator_can_activate_play(self):
        self.client.force_login(self.mod)
        url = reverse(
            "plays:activate",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertTrue(self.play.is_active)


class TestPlayUpdateCommentView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Comment Comp",
            date=date(2026, 1, 1),
        )
        cls.admin = User.objects.create_user(
            username="cmt_admin", password="pwd", is_superuser=True
        )
        cls.reader = User.objects.create_user(username="cmt_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Comment Play",
            author_email="cmt@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_admin_can_update_internal_comment(self):
        self.client.force_login(self.admin)
        url = reverse(
            "plays:edit-comment",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url, {"internal_comment": "Important note"})
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertEqual(self.play.internal_comment, "Important note")

    def test_reader_cannot_update_internal_comment(self):
        self.client.force_login(self.reader)
        url = reverse(
            "plays:edit-comment",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url, {"internal_comment": "Hack"})
        self.assertEqual(response.status_code, 403)


class TestPlayUpdateCommentModerator(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Comment Mod Comp",
            date=date(2026, 1, 1),
        )
        cls.mod = User.objects.create_user(username="cmtm_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Comment Mod Play",
            author_email="cmtm@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_moderator_can_update_internal_comment(self):
        self.client.force_login(self.mod)
        url = reverse(
            "plays:edit-comment",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url, {"internal_comment": "Mod note"})
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertEqual(self.play.internal_comment, "Mod note")


class TestPlayDetailVisibility(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Detail Vis Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
            are_phase1_reviews_visible=True,
            are_phase2_reviews_visible=False,
        )
        cls.admin = User.objects.create_user(
            username="dv_admin", password="pwd", is_superuser=True
        )
        cls.mod = User.objects.create_user(username="dv_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader1 = User.objects.create_user(username="dv_r1", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader1, competition=cls.competition, role="reader"
        )
        cls.reader2 = User.objects.create_user(username="dv_r2", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader2, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Detail Vis Play",
            author_email="dv@a.com",
            is_active=True,
        )
        Review.objects.create(
            reader=cls.reader1,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Good",
            is_hidden=False,
            is_obsolete=False,
        )
        Review.objects.create(
            reader=cls.reader2,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
            is_hidden=True,
            is_obsolete=False,
        )

    def setUp(self):
        self.client = Client()

    def test_admin_sees_all_reviews(self):
        self.client.force_login(self.admin)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        own_reviews = list(response.context["own_reviews"])
        self.assertEqual(len(own_reviews), 2)

    def test_reader_sees_own_submitted_reviews(self):
        self.client.force_login(self.reader1)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        own_reviews = list(response.context["own_reviews"])
        self.assertEqual(len(own_reviews), 1)
        self.assertEqual(own_reviews[0].reader, self.reader1)

    def test_reader_sees_other_visible_reviews(self):
        self.client.force_login(self.reader2)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        other_reviews = list(response.context["other_reviews"])
        other_readers = [r.reader for r in other_reviews]
        self.assertIn(self.reader1, other_readers)

    def test_reader_does_not_see_hidden_other_reviews(self):
        self.client.force_login(self.reader1)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        other_reviews = list(response.context["other_reviews"])
        other_readers = [r.reader for r in other_reviews]
        self.assertNotIn(self.reader2, other_readers)

    def test_reader_sees_active_review_in_my_active_review(self):
        new_play = Play.objects.create(
            competition=self.competition,
            title="Draft Play",
            author_email="draft@a.com",
            is_active=True,
        )
        review = Review.objects.create(
            reader=self.reader1,
            play=new_play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.DRAFT,
            is_obsolete=False,
        )
        self.client.force_login(self.reader1)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": new_play.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.context["my_active_review"], review)

    def test_no_visible_reviews_when_phase_hidden(self):
        comp = Competition.objects.create(
            title="Hidden Phase Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
            are_phase1_reviews_visible=False,
            are_phase2_reviews_visible=False,
        )
        reader_a = User.objects.create_user(username="hp_ra", password="pwd")
        reader_b = User.objects.create_user(username="hp_rb", password="pwd")
        CompetitionRole.objects.create(user=reader_a, competition=comp, role="reader")
        CompetitionRole.objects.create(user=reader_b, competition=comp, role="reader")
        play = Play.objects.create(
            competition=comp,
            title="Hidden Phase Play",
            author_email="hp@a.com",
            is_active=True,
        )
        Review.objects.create(
            reader=reader_a,
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
            is_hidden=False,
            is_obsolete=False,
        )
        Review.objects.create(
            reader=reader_b,
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
            is_hidden=False,
            is_obsolete=False,
        )
        self.client.force_login(reader_a)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": comp.slug, "pk": play.pk},
        )
        response = self.client.get(url)
        other_reviews = list(response.context["other_reviews"])
        self.assertEqual(len(other_reviews), 0)


class TestPlayUniqueConstraint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Unique Comp", date=date(2026, 1, 1)
        )

    def test_duplicate_play_raises_integrity_error(self):
        Play.objects.create(
            competition=self.competition,
            title="Unique Play",
            author_email="uniq@a.com",
            author_first_name="Test",
        )
        with self.assertRaises(IntegrityError):
            Play.objects.create(
                competition=self.competition,
                title="Unique Play",
                author_email="uniq@a.com",
                author_first_name="Test",
            )

    def test_same_title_different_email_ok(self):
        Play.objects.create(
            competition=self.competition,
            title="Same Title",
            author_email="a@a.com",
            author_first_name="A",
        )
        play2 = Play.objects.create(
            competition=self.competition,
            title="Same Title",
            author_email="b@b.com",
            author_first_name="B",
        )
        self.assertIsNotNone(play2.pk)


class TestPlayGetAbsoluteUrl(TestCase):
    def test_get_absolute_url(self):
        comp = Competition.objects.create(title="URL Comp", date=date(2026, 1, 1))
        play = Play.objects.create(
            competition=comp,
            title="URL Play",
            author_email="url@a.com",
            author_first_name="Test",
        )
        expected = reverse(
            "plays:detail",
            kwargs={"competition_slug": comp.slug, "pk": play.pk},
        )
        self.assertEqual(play.get_absolute_url(), expected)


class TestPlayDeactivateAdminAndReader(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Deact Comp",
            date=date(2026, 1, 1),
        )
        cls.admin = User.objects.create_user(
            username="deact_admin", password="pwd", is_superuser=True
        )
        cls.reader = User.objects.create_user(username="deact_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Deact Play",
            author_email="deact@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_admin_can_deactivate_play(self):
        self.client.force_login(self.admin)
        url = reverse(
            "plays:deactivate",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.play.refresh_from_db()
        self.assertFalse(self.play.is_active)

    def test_reader_cannot_deactivate_play(self):
        self.client.force_login(self.reader)
        url = reverse(
            "plays:deactivate",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.play.refresh_from_db()
        self.assertTrue(self.play.is_active)


class TestPlayListPositiveVotes(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="PosVotes Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
            are_phase1_reviews_visible=False,
        )
        cls.reader = User.objects.create_user(username="pv_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="PosVotes Play",
            author_email="pvs@a.com",
            is_active=True,
        )
        Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
        )

    def test_reader_sees_positive_vote_count(self):
        self.client.force_login(self.reader)
        url = reverse("plays:list", kwargs={"competition_slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["number_positive_votes"], 1)
