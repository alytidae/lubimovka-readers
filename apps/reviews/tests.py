from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from apps.users.models import User
from apps.competitions.models import Competition, CompetitionRole
from apps.plays.models import Play
from apps.reviews.models import Review
from apps.reviews.services import assign_play, submit


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
            user = User.objects.create_user(email=f"reader{i}@test.com", password="pwd")
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
            title="Lifecycle Comp", date=date(2026, 1, 1)
        )
        cls.reader = User.objects.create_user(email="reader@test.com", password="pwd")
        cls.mod = User.objects.create_user(email="mod@test.com", password="pwd")

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
