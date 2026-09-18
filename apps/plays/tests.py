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


class TestExcludePhase2Views(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Exclude Phase 2",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.admin = User.objects.create_user(username="exclude_admin", password="pwd")
        cls.superuser = User.objects.create_user(
            username="exclude_superuser",
            password="pwd",
            is_superuser=True,
        )
        cls.moderator = User.objects.create_user(username="exclude_mod", password="pwd")
        cls.reader = User.objects.create_user(username="exclude_reader", password="pwd")
        cls.second_reader = User.objects.create_user(
            username="exclude_reader2", password="pwd"
        )
        for user, role in [
            (cls.admin, "admin"),
            (cls.moderator, "moderator"),
            (cls.reader, "reader"),
            (cls.second_reader, "reader"),
        ]:
            CompetitionRole.objects.create(
                user=user, competition=cls.competition, role=role
            )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Approved play",
            author_email="exclude@test.com",
            is_active=True,
            internal_comment="Existing organiser comment",
        )
        for reader in [cls.reader, cls.second_reader]:
            Review.objects.create(
                play=cls.play,
                reader=reader,
                phase=Review.Phase.PHASE_1,
                status=Review.Status.SUBMITTED,
                verdict=True,
                comment="Original yes",
            )
        cls.reason = "Both readers withdrew their yes after rereading."

    def exclude(self, user, comment):
        self.client.force_login(user)
        return self.client.post(
            reverse(
                "plays:exclude-phase-2",
                kwargs={
                    "competition_slug": self.competition.slug,
                    "pk": self.play.pk,
                },
            ),
            {"comment": comment},
        )

    def test_admin_can_exclude_with_reason_without_changing_reviews(self):
        original_reviews = list(self.play.reviews.order_by("pk").values())
        response = self.exclude(self.admin, self.reason)
        self.assertRedirects(response, self.play.get_absolute_url())
        self.play.refresh_from_db()
        self.assertTrue(self.play.exclude_phase_2)
        self.assertEqual(self.play.phase_2_exclusion_comment, self.reason)
        self.assertTrue(self.play.is_active)
        self.assertEqual(self.play.internal_comment, "Existing organiser comment")
        self.assertEqual(
            list(self.play.reviews.order_by("pk").values()), original_reviews
        )

    def test_superuser_can_exclude(self):
        response = self.exclude(self.superuser, self.reason)
        self.assertRedirects(response, self.play.get_absolute_url())
        self.play.refresh_from_db()
        self.assertTrue(self.play.exclude_phase_2)

    def test_empty_or_whitespace_reason_does_not_exclude(self):
        for comment in ["", "   \n\t"]:
            with self.subTest(comment=comment):
                self.exclude(self.admin, comment)
                self.play.refresh_from_db()
                self.assertFalse(self.play.exclude_phase_2)
                self.assertFalse(self.play.phase_2_exclusion_comment)

    def test_missing_reason_does_not_exclude(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse(
                "plays:exclude-phase-2",
                kwargs={
                    "competition_slug": self.competition.slug,
                    "pk": self.play.pk,
                },
            )
        )
        self.play.refresh_from_db()
        self.assertFalse(self.play.exclude_phase_2)

    def test_reader_and_moderator_cannot_exclude(self):
        for user in [self.reader, self.moderator]:
            with self.subTest(user=user.username):
                response = self.exclude(user, self.reason)
                self.assertEqual(response.status_code, 403)
                self.play.refresh_from_db()
                self.assertFalse(self.play.exclude_phase_2)

    def test_admin_of_another_competition_cannot_exclude(self):
        other = Competition.objects.create(
            title="Other exclusion", date=date(2026, 1, 1)
        )
        user = User.objects.create_user(username="other_exclude_admin", password="pwd")
        CompetitionRole.objects.create(user=user, competition=other, role="admin")
        response = self.exclude(user, self.reason)
        self.assertEqual(response.status_code, 403)
        self.play.refresh_from_db()
        self.assertFalse(self.play.exclude_phase_2)

    def test_cannot_exclude_outside_phase_1(self):
        for status in [
            Competition.Status.SETUP,
            Competition.Status.PHASE_2,
            Competition.Status.FINISHED,
        ]:
            with self.subTest(status=status):
                self.competition.status = status
                self.competition.save()
                self.exclude(self.admin, self.reason)
                self.play.refresh_from_db()
                self.assertFalse(self.play.exclude_phase_2)
                self.assertFalse(self.play.phase_2_exclusion_comment)

    def test_get_does_not_exclude(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse(
                "plays:exclude-phase-2",
                kwargs={
                    "competition_slug": self.competition.slug,
                    "pk": self.play.pk,
                },
            )
        )
        self.assertEqual(response.status_code, 405)
        self.play.refresh_from_db()
        self.assertFalse(self.play.exclude_phase_2)

    def test_admin_sees_exclusion_form_but_reader_and_moderator_do_not(self):
        for user, visible in [
            (self.admin, True),
            (self.reader, False),
            (self.moderator, False),
        ]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.play.get_absolute_url())
                if visible:
                    self.assertContains(response, 'id="exclude-phase2-dialog"')
                    self.assertContains(response, 'name="comment" rows="6" required')
                else:
                    self.assertNotContains(response, 'id="exclude-phase2-dialog"')

    def test_excluded_play_shows_reason_and_hides_advancement_actions(self):
        self.exclude(self.admin, self.reason)
        response = self.client.get(self.play.get_absolute_url())
        self.assertContains(response, self.reason)
        self.assertNotContains(response, 'id="exclude-phase2-dialog"')
        self.assertNotContains(
            response, "document.getElementById('force-phase2-dialog').showModal()"
        )

    def test_repeated_exclusion_preserves_original_reason(self):
        self.exclude(self.admin, self.reason)
        self.exclude(self.admin, "A replacement reason")
        self.play.refresh_from_db()
        self.assertTrue(self.play.exclude_phase_2)
        self.assertEqual(self.play.phase_2_exclusion_comment, self.reason)


class TestExcludePhase2Selection(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Excluded selection",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.admin = User.objects.create_user(
            username="selection_admin",
            password="pwd",
            is_superuser=True,
        )
        cls.readers = []
        for i in range(3):
            reader = User.objects.create_user(
                username=f"selection_reader{i}", password="pwd"
            )
            CompetitionRole.objects.create(
                user=reader, competition=cls.competition, role="reader"
            )
            cls.readers.append(reader)
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Excluded approved play",
            author_email="selection@test.com",
            is_active=True,
        )
        for reader in cls.readers[:2]:
            Review.objects.create(
                play=cls.play,
                reader=reader,
                phase=Review.Phase.PHASE_1,
                status=Review.Status.SUBMITTED,
                verdict=True,
                comment="Yes",
            )

    def mark_excluded(self):
        # Persist the future model contract: an in-memory attribute would not
        # exercise the database queries that select plays for either phase.
        self.play.exclude_phase_2 = True
        self.play.phase_2_exclusion_comment = "Both readers withdrew their yes."
        self.play.save(update_fields=["exclude_phase_2", "phase_2_exclusion_comment"])

    def test_exclusion_overrides_two_yes_votes(self):
        from apps.reviews.services import auto_assign_phase2

        self.mark_excluded()
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        self.assertEqual(auto_assign_phase2(self.competition), 0)
        self.assertFalse(self.play.reviews.filter(phase=Review.Phase.PHASE_2).exists())

    def test_exclusion_overrides_forced_phase_2(self):
        from apps.reviews.services import auto_assign_phase2

        self.play.force_phase_2 = True
        self.play.save(update_fields=["force_phase_2"])
        self.mark_excluded()
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        self.assertEqual(auto_assign_phase2(self.competition), 0)
        self.assertFalse(self.play.reviews.filter(phase=Review.Phase.PHASE_2).exists())

    def test_excluded_tie_does_not_return_to_phase_1_pool(self):
        from apps.reviews.services import assign_play

        self.play.reviews.filter(reader=self.readers[0]).update(verdict=False)
        self.mark_excluded()
        result = assign_play(self.readers[2], self.competition)
        self.assertFalse(result.success)
        self.assertFalse(self.play.reviews.filter(reader=self.readers[2]).exists())

    def test_non_excluded_approved_play_still_gets_phase_2_assignments(self):
        from apps.reviews.services import auto_assign_phase2

        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        self.assertEqual(auto_assign_phase2(self.competition), 3)
        self.assertEqual(
            self.play.reviews.filter(phase=Review.Phase.PHASE_2).count(), 3
        )

    def test_excluded_play_is_absent_from_phase_2_analytics(self):
        self.mark_excluded()
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("competitions:analytics", kwargs={"slug": self.competition.slug}),
            {"phase": "phase_2"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            self.play.pk, [play.pk for play in response.context["plays_overview"]]
        )
        self.assertEqual(response.context["remaining_reviews"], 0)
        self.assertEqual(response.context["plays_0_votes_count"], 0)


class TestUnexcludePhase2Views(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Cancel Phase 2 exclusion",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.admin = User.objects.create_user(username="restore_admin", password="pwd")
        cls.superuser = User.objects.create_user(
            username="restore_superuser",
            password="pwd",
            is_superuser=True,
        )
        cls.moderator = User.objects.create_user(username="restore_mod", password="pwd")
        cls.readers = []
        CompetitionRole.objects.create(
            user=cls.admin, competition=cls.competition, role="admin"
        )
        CompetitionRole.objects.create(
            user=cls.moderator, competition=cls.competition, role="moderator"
        )
        for i in range(3):
            reader = User.objects.create_user(
                username=f"restore_reader{i}", password="pwd"
            )
            CompetitionRole.objects.create(
                user=reader, competition=cls.competition, role="reader"
            )
            cls.readers.append(reader)
        cls.reason = "Both readers withdrew their yes after rereading."
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Excluded play to restore",
            author_email="restore@test.com",
            is_active=True,
            exclude_phase_2=True,
            phase_2_exclusion_comment=cls.reason,
            internal_comment="Original comment",
        )
        for reader in cls.readers[:2]:
            Review.objects.create(
                play=cls.play,
                reader=reader,
                phase=Review.Phase.PHASE_1,
                status=Review.Status.SUBMITTED,
                verdict=True,
                comment="Original yes",
            )

    def unexclude_url(self):
        return reverse(
            "plays:unexclude-phase-2",
            kwargs={
                "competition_slug": self.competition.slug,
                "pk": self.play.pk,
            },
        )

    def unexclude(self, user=None):
        self.client.force_login(user or self.admin)
        return self.client.post(self.unexclude_url())

    def test_cancel_clears_reason_but_preserves_reviews_and_other_play_data(self):
        original_reviews = list(self.play.reviews.order_by("pk").values())
        for user in [self.admin, self.superuser]:
            with self.subTest(user=user.username):
                self.play.exclude_phase_2 = True
                self.play.phase_2_exclusion_comment = self.reason
                self.play.save(
                    update_fields=["exclude_phase_2", "phase_2_exclusion_comment"]
                )
                response = self.unexclude(user)
                self.assertRedirects(response, self.play.get_absolute_url())
                self.play.refresh_from_db()
                self.assertFalse(self.play.exclude_phase_2)
                self.assertEqual(self.play.phase_2_exclusion_comment, "")
                self.assertNotContains(
                    self.client.get(self.play.get_absolute_url()), self.reason
                )
                self.assertEqual(self.play.internal_comment, "Original comment")
                self.assertTrue(self.play.is_active)
                self.assertFalse(self.play.force_phase_2)
                self.assertEqual(
                    list(self.play.reviews.order_by("pk").values()), original_reviews
                )

    def test_unauthorized_users_cannot_cancel(self):
        other = Competition.objects.create(title="Other restore", date=date(2026, 1, 1))
        other_admin = User.objects.create_user(
            username="other_restore_admin", password="pwd"
        )
        CompetitionRole.objects.create(
            user=other_admin, competition=other, role="admin"
        )
        for user in [self.readers[0], self.moderator, other_admin, None]:
            with self.subTest(user=str(user)):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                response = self.client.post(self.unexclude_url())
                self.assertEqual(response.status_code, 403 if user else 302)
                if not user:
                    self.assertTrue(response.url.startswith(reverse("login")))
                self.play.refresh_from_db()
                self.assertTrue(self.play.exclude_phase_2)
                self.assertEqual(self.play.phase_2_exclusion_comment, self.reason)

    def test_cancel_requires_post_and_phase_1(self):
        self.client.force_login(self.admin)
        with self.subTest(method="GET"):
            response = self.client.get(self.unexclude_url())
            self.assertEqual(response.status_code, 405)
            self.play.refresh_from_db()
            self.assertTrue(self.play.exclude_phase_2)
        for status in [
            Competition.Status.SETUP,
            Competition.Status.PHASE_2,
            Competition.Status.FINISHED,
        ]:
            with self.subTest(status=status):
                self.competition.status = status
                self.competition.save()
                self.unexclude()
                self.play.refresh_from_db()
                self.assertTrue(self.play.exclude_phase_2)
                self.assertEqual(self.play.phase_2_exclusion_comment, self.reason)

    def test_cancel_restores_advancement_rules_and_analytics(self):
        from django.db import transaction
        from apps.reviews.services import auto_assign_phase2

        for verdict, forced, qualifies in [
            (True, False, True),
            (False, True, True),
            (False, False, False),
        ]:
            with self.subTest(verdict=verdict, forced=forced), transaction.atomic():
                self.play.force_phase_2 = forced
                self.play.save(update_fields=["force_phase_2"])
                self.play.reviews.update(verdict=verdict)
                self.unexclude()
                self.play.refresh_from_db()
                self.assertFalse(self.play.exclude_phase_2)
                self.assertEqual(self.play.force_phase_2, forced)
                response = self.client.get(
                    reverse(
                        "competitions:analytics", kwargs={"slug": self.competition.slug}
                    ),
                    {"phase": "phase_2"},
                )
                self.assertEqual(response.status_code, 200)
                ids = [play.pk for play in response.context["plays_overview"]]
                self.assertEqual(self.play.pk in ids, qualifies)
                self.assertEqual(
                    response.context["remaining_reviews"], 3 if qualifies else 0
                )
                self.assertEqual(
                    response.context["plays_0_votes_count"], 1 if qualifies else 0
                )
                self.competition.status = Competition.Status.PHASE_2
                self.competition.save()
                self.assertEqual(
                    auto_assign_phase2(self.competition), 3 if qualifies else 0
                )
                self.assertEqual(
                    self.play.reviews.filter(phase=Review.Phase.PHASE_2).count(),
                    3 if qualifies else 0,
                )
                transaction.set_rollback(True)

    def test_cancel_returns_tie_to_phase_1_pool(self):
        from apps.reviews.services import assign_play

        self.play.reviews.filter(reader=self.readers[0]).update(verdict=False)
        self.unexclude()
        result = assign_play(self.readers[2], self.competition)
        self.assertTrue(result.success)
        self.assertEqual(result.play, self.play)

    def test_cancel_button_is_only_visible_to_admins_for_excluded_play_in_phase_1(self):
        for user, excluded, status, visible in [
            (self.admin, True, Competition.Status.PHASE_1, True),
            (self.superuser, True, Competition.Status.PHASE_1, True),
            (self.moderator, True, Competition.Status.PHASE_1, False),
            (self.readers[0], True, Competition.Status.PHASE_1, False),
            (self.admin, False, Competition.Status.PHASE_1, False),
            (self.admin, True, Competition.Status.PHASE_2, False),
        ]:
            with self.subTest(user=user.username, excluded=excluded, status=status):
                self.play.exclude_phase_2 = excluded
                self.play.save(update_fields=["exclude_phase_2"])
                self.competition.status = status
                self.competition.save()
                self.client.force_login(user)
                response = self.client.get(
                    self.play.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en"
                )
                if visible:
                    self.assertContains(response, ">Cancel Phase 2 exclusion</button>")
                else:
                    self.assertNotContains(
                        response, ">Cancel Phase 2 exclusion</button>"
                    )
