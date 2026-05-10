from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from apps.users.models import User
from apps.competitions.models import Competition, CompetitionRole
from apps.plays.models import Play
from apps.reviews.models import Review
from apps.reviews.services import (
    assign_play,
    submit,
    save_draft,
    mark_public,
    mark_hidden,
    mark_obsolete,
    restore,
    auto_assign_phase2,
)


class TestPlayAssignmentAndPhases(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Test Competition",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )

        cls.readers = []
        for i in range(4):
            user = User.objects.create_user(username=f"reader{i}", password="pwd")
            CompetitionRole.objects.create(
                user=user, competition=cls.competition, role="reader"
            )
            cls.readers.append(user)

        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Test Play",
            author_email="author@test.com",
            is_active=True,
        )

    def test_assign_play_fails_if_competition_not_in_phase_1(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        result = assign_play(self.readers[0], self.competition)
        self.assertFalse(result.success)

    def test_assign_play_respects_max_readers_per_play(self):
        for i in range(3):
            assign_play(self.readers[i], self.competition)

        result_4 = assign_play(self.readers[3], self.competition)
        self.assertFalse(result_4.success)
        self.assertEqual(Review.objects.filter(play=self.play).count(), 3)

    def test_play_excluded_after_two_positive_verdicts(self):
        assign_play(self.readers[0], self.competition)
        submit(
            Review.objects.get(reader=self.readers[0]), verdict=True, comment="Great"
        )

        assign_play(self.readers[1], self.competition)
        submit(
            Review.objects.get(reader=self.readers[1]), verdict=True, comment="Awesome"
        )

        result = assign_play(self.readers[2], self.competition)
        self.assertFalse(result.success)


class TestReviewLifecycle(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Lifecycle Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
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
            title="Lifecycle Play",
            author_email="a@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )

    def setUp(self):
        self.client = Client()

    def test_save_draft_retains_status(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:save_draft",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )

        self.client.post(url, {"verdict": "True", "comment": "Draft comment"})
        self.review.refresh_from_db()

        self.assertEqual(self.review.status, Review.Status.DRAFT)
        self.assertEqual(self.review.comment, "Draft comment")

    def test_moderator_can_mark_obsolete(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:mark_obsolete",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )

        self.client.post(url)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_obsolete)


class TestPhaseGuards(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.readers = []
        for i in range(3):
            cls.readers.append(
                User.objects.create_user(username=f"pg_reader{i}", password="pwd")
            )

    def _make_comp_and_play(self, status=Competition.Status.PHASE_1):
        comp = Competition.objects.create(
            title=f"PG Comp {self.id()}", date=date(2026, 1, 1), status=status
        )
        for r in self.readers:
            CompetitionRole.objects.create(user=r, competition=comp, role="reader")
        play = Play.objects.create(
            competition=comp,
            title="PG Play",
            author_email="pg@a.com",
            is_active=True,
        )
        return comp, play

    def test_can_save_draft_in_phase_1(self):
        comp, play = self._make_comp_and_play(Competition.Status.PHASE_1)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = save_draft(review, True, "draft")
        self.assertTrue(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.DRAFT)

    def test_can_submit_in_phase_1(self):
        comp, play = self._make_comp_and_play(Competition.Status.PHASE_1)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, True, "final comment")
        self.assertTrue(result.success)

    def test_cannot_save_draft_in_setup(self):
        comp, play = self._make_comp_and_play(Competition.Status.SETUP)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = save_draft(review, True, "draft")
        self.assertFalse(result.success)

    def test_cannot_submit_in_setup(self):
        comp, play = self._make_comp_and_play(Competition.Status.SETUP)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, True, "comment")
        self.assertFalse(result.success)

    def test_cannot_submit_phase1_review_when_competition_in_phase2(self):
        comp, play = self._make_comp_and_play(Competition.Status.PHASE_2)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, True, "comment")
        self.assertFalse(result.success)

    def test_cannot_save_draft_phase1_review_when_competition_in_phase2(self):
        comp, play = self._make_comp_and_play(Competition.Status.PHASE_2)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = save_draft(review, True, "draft")
        self.assertFalse(result.success)

    def test_can_submit_phase2_review_when_competition_in_phase2(self):
        comp, play = self._make_comp_and_play(Competition.Status.PHASE_2)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_2,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, True, "comment")
        self.assertTrue(result.success)

    def test_can_save_draft_phase2_review_when_competition_in_phase2(self):
        comp, play = self._make_comp_and_play(Competition.Status.PHASE_2)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_2,
            status=Review.Status.ASSIGNED,
        )
        result = save_draft(review, True, "draft")
        self.assertTrue(result.success)

    def test_cannot_submit_in_finished(self):
        comp, play = self._make_comp_and_play(Competition.Status.FINISHED)
        review = Review.objects.create(
            reader=self.readers[0],
            play=play,
            phase=Review.Phase.PHASE_2,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, True, "comment")
        self.assertFalse(result.success)


class TestPhase2AutoAssignment(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="P2 Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.readers = []
        for i in range(3):
            user = User.objects.create_user(username=f"p2_reader{i}", password="pwd")
            CompetitionRole.objects.create(
                user=user, competition=cls.competition, role="reader"
            )
            cls.readers.append(user)

        cls.play_yes = Play.objects.create(
            competition=cls.competition,
            title="Approved Play",
            author_email="yes@a.com",
            is_active=True,
        )
        cls.play_no = Play.objects.create(
            competition=cls.competition,
            title="Rejected Play",
            author_email="no@a.com",
            is_active=True,
        )
        cls.play_inactive = Play.objects.create(
            competition=cls.competition,
            title="Inactive Play",
            author_email="inactive@a.com",
            is_active=False,
        )

        extra_reader_1 = User.objects.create_user(username="extra1", password="pwd")
        extra_reader_2 = User.objects.create_user(username="extra2", password="pwd")
        Review.objects.create(
            reader=extra_reader_1,
            play=cls.play_yes,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
        )
        Review.objects.create(
            reader=extra_reader_2,
            play=cls.play_yes,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
        )

        Review.objects.create(
            reader=extra_reader_1,
            play=cls.play_no,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
        )
        Review.objects.create(
            reader=extra_reader_2,
            play=cls.play_no,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
        )

    def test_assigns_phase2_reviews_for_plays_with_2_yes_votes(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        count = auto_assign_phase2(self.competition)

        self.assertEqual(count, 3)
        phase2_reviews = Review.objects.filter(
            play=self.play_yes, phase=Review.Phase.PHASE_2
        )
        self.assertEqual(phase2_reviews.count(), 3)

    def test_does_not_assign_for_plays_with_2_no_votes(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        auto_assign_phase2(self.competition)

        phase2_reviews = Review.objects.filter(
            play=self.play_no, phase=Review.Phase.PHASE_2
        )
        self.assertEqual(phase2_reviews.count(), 0)

    def test_does_not_assign_for_inactive_plays(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        auto_assign_phase2(self.competition)

        phase2_reviews = Review.objects.filter(
            play=self.play_inactive, phase=Review.Phase.PHASE_2
        )
        self.assertEqual(phase2_reviews.count(), 0)

    def test_does_not_create_duplicates_on_second_call(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        auto_assign_phase2(self.competition)
        count = auto_assign_phase2(self.competition)

        self.assertEqual(count, 0)

    def test_returns_zero_if_not_phase_2(self):
        self.competition.status = Competition.Status.PHASE_1
        self.competition.save()
        count = auto_assign_phase2(self.competition)
        self.assertEqual(count, 0)

    def test_excludes_inactive_readers(self):
        inactive_reader = User.objects.create_user(
            username="inactive_reader", password="pwd"
        )
        role = CompetitionRole.objects.create(
            user=inactive_reader,
            competition=self.competition,
            role="reader",
            is_active=False,
        )
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        auto_assign_phase2(self.competition)

        self.assertFalse(
            Review.objects.filter(
                reader=inactive_reader, play=self.play_yes, phase=Review.Phase.PHASE_2
            ).exists()
        )

    def test_phase1_reviewers_still_get_phase2_assignment(self):
        reviewer_who_voted_yes = User.objects.create_user(
            username="voted_yes", password="pwd"
        )
        CompetitionRole.objects.create(
            user=reviewer_who_voted_yes,
            competition=self.competition,
            role="reader",
        )
        Review.objects.create(
            reader=reviewer_who_voted_yes,
            play=self.play_yes,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Voted yes in phase 1",
        )

        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        auto_assign_phase2(self.competition)

        self.assertTrue(
            Review.objects.filter(
                reader=reviewer_who_voted_yes,
                play=self.play_yes,
                phase=Review.Phase.PHASE_2,
            ).exists()
        )


class TestReviewSubmitViaView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Submit Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="sub", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Submit Play",
            author_email="s@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.reader)

    def test_submit_review_via_post(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        url = reverse(
            "reviews:submit",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url, {"verdict": "True", "comment": "Great play"})
        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.SUBMITTED)
        self.assertTrue(review.verdict)
        self.assertIsNotNone(review.submitted_at)

    def test_submit_without_verdict_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        url = reverse(
            "reviews:submit",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        self.client.post(url, {"comment": "No verdict"})
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.ASSIGNED)

    def test_submit_without_comment_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        url = reverse(
            "reviews:submit",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        self.client.post(url, {"verdict": "True"})
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.ASSIGNED)

    def test_cannot_submit_twice(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        url = reverse(
            "reviews:submit",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        self.client.post(url, {"verdict": "True", "comment": "First"})
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.SUBMITTED)

        response = self.client.post(url, {"verdict": "False", "comment": "Second"})
        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.assertTrue(review.verdict)
        self.assertEqual(review.comment, "First")

    def test_save_draft_via_post(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        url = reverse(
            "reviews:save_draft",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url, {"verdict": "False", "comment": "Draft"})
        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.DRAFT)
        self.assertFalse(review.verdict)
        self.assertEqual(review.comment, "Draft")


class TestReviewModerationViaView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Mod Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="mod_r", password="pwd")
        cls.mod = User.objects.create_user(username="mod_m", password="pwd")
        cls.admin = User.objects.create_user(
            username="mod_a", password="pwd", is_superuser=True
        )

        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )

        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Mod Play",
            author_email="m@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Good",
        )

    def setUp(self):
        self.client = Client()

    def test_mark_public(self):
        self.review.is_hidden = True
        self.review.save()
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:mark_public",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        self.client.post(url)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_hidden)

    def test_mark_hidden(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:mark_hidden",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        self.client.post(url)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)

    def test_mark_obsolete(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:mark_obsolete",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        self.client.post(url)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_obsolete)

    def test_restore(self):
        self.review.is_obsolete = True
        self.review.save()
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:restore",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        self.client.post(url)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_obsolete)

    def test_reader_cannot_mark_hidden(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:mark_hidden",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_mark_hidden(self):
        self.client.force_login(self.admin)
        url = reverse(
            "reviews:mark_hidden",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        self.client.post(url)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)
