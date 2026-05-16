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
    reject,
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
        self.competition.refresh_from_db()
        for i in range(3):
            assign_play(self.readers[i], self.competition)

        result_4 = assign_play(self.readers[3], self.competition)
        self.assertFalse(result_4.success)
        self.assertEqual(Review.objects.filter(play=self.play).count(), 3)

    def test_play_excluded_after_two_positive_verdicts(self):
        self.competition.refresh_from_db()
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


class TestRejectReviewService(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Reject Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="rej_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Reject Play",
            author_email="r@a.com",
            is_active=True,
        )

    def test_reject_assigned_review(self):
        self.competition.refresh_from_db()
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = reject(review)
        self.assertTrue(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.REJECTED)
        self.assertTrue(review.is_obsolete)

    def test_cannot_reject_draft_review(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.DRAFT,
        )
        result = reject(review)
        self.assertFalse(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.DRAFT)
        self.assertFalse(review.is_obsolete)

    def test_cannot_reject_submitted_review(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Done",
        )
        result = reject(review)
        self.assertFalse(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.SUBMITTED)
        self.assertFalse(review.is_obsolete)

    def test_cannot_reject_in_wrong_phase(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = reject(review)
        self.assertFalse(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.ASSIGNED)
        self.assertFalse(review.is_obsolete)

    def test_cannot_reject_in_setup(self):
        self.competition.status = Competition.Status.SETUP
        self.competition.save()
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = reject(review)
        self.assertFalse(result.success)


class TestRejectReviewViaView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Reject View Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="rv_reader", password="pwd")
        cls.other_reader = User.objects.create_user(username="rv_other", password="pwd")
        cls.mod = User.objects.create_user(username="rv_mod", password="pwd")

        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        CompetitionRole.objects.create(
            user=cls.other_reader, competition=cls.competition, role="reader"
        )
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )

        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Reject View Play",
            author_email="rv@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_reader_can_reject_assigned_review(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("plays:list", kwargs={"competition_slug": self.competition.slug}),
        )
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.REJECTED)
        self.assertTrue(review.is_obsolete)

    def test_redirects_to_list_after_reject(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("plays:list", kwargs={"competition_slug": self.competition.slug}),
        )

    def test_cannot_reject_draft_via_view(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.DRAFT,
        )
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_other_reader_cannot_reject(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        self.client.force_login(self.other_reader)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_moderator_cannot_reject_reader_review(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)


class TestRejectPlayReturnToPool(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Pool Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader1 = User.objects.create_user(username="pool_r1", password="pwd")
        cls.reader2 = User.objects.create_user(username="pool_r2", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader1, competition=cls.competition, role="reader"
        )
        CompetitionRole.objects.create(
            user=cls.reader2, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Pool Play",
            author_email="p@a.com",
            is_active=True,
        )

    def test_rejected_review_returns_play_to_pool(self):
        result1 = assign_play(self.reader1, self.competition)
        self.assertTrue(result1.success)

        review = Review.objects.get(reader=self.reader1, play=self.play)
        reject(review)

        result2 = assign_play(self.reader2, self.competition)
        self.assertTrue(result2.success)

    def test_rejected_review_not_counted_towards_max_per_play(self):
        for i in range(3):
            user = User.objects.create_user(username=f"pool_extra{i}", password="pwd")
            CompetitionRole.objects.create(
                user=user, competition=self.competition, role="reader"
            )
            assign_play(user, self.competition)

        review = Review.objects.filter(play=self.play).first()
        reject(review)

        result = assign_play(self.reader1, self.competition)
        self.assertTrue(result.success)


class TestAdminSeesRejectedAndRevotedReviews(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Admin View Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="av_reader", password="pwd")
        cls.mod = User.objects.create_user(username="av_mod", password="pwd")
        cls.admin = User.objects.create_user(
            username="av_admin", password="pwd", is_superuser=True
        )
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Admin View Play",
            author_email="av@a.com",
            is_active=True,
        )
        cls.review_play = Play.objects.create(
            competition=cls.competition,
            title="Review Test Play",
            author_email="rvtest@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.review_play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )

    def setUp(self):
        self.client = Client()

    def test_admin_sees_rejected_review_in_play_detail(self):
        Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.REJECTED,
            is_obsolete=True,
        )
        self.client.force_login(self.admin)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        own_reviews = list(response.context["own_reviews"])
        self.assertEqual(len(own_reviews), 1)
        self.assertEqual(own_reviews[0].status, Review.Status.REJECTED)

    def test_admin_sees_revoted_review_in_play_detail(self):
        Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Good",
            is_obsolete=True,
        )
        self.client.force_login(self.admin)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        own_reviews = list(response.context["own_reviews"])
        self.assertEqual(len(own_reviews), 1)
        self.assertTrue(own_reviews[0].is_obsolete)

    def test_admin_sees_both_rejected_and_submitted(self):
        Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.REJECTED,
            is_obsolete=True,
        )
        reader2 = User.objects.create_user(username="av_r2", password="pwd")
        CompetitionRole.objects.create(
            user=reader2, competition=self.competition, role="reader"
        )
        Review.objects.create(
            reader=reader2,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Nice",
        )
        self.client.force_login(self.admin)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        own_reviews = list(response.context["own_reviews"])
        self.assertEqual(len(own_reviews), 2)

    def test_moderator_sees_rejected_review(self):
        Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.REJECTED,
            is_obsolete=True,
        )
        self.client.force_login(self.mod)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        own_reviews = list(response.context["own_reviews"])
        self.assertEqual(len(own_reviews), 1)

    def test_reader_does_not_see_rejected_review(self):
        Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.REJECTED,
            is_obsolete=True,
        )
        self.client.force_login(self.reader)
        url = reverse(
            "plays:detail",
            kwargs={"competition_slug": self.competition.slug, "pk": self.play.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

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

    def test_reader_can_mark_hidden(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:mark_hidden",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)

    def test_admin_can_mark_hidden(self):
        self.client.force_login(self.admin)
        url = reverse(
            "reviews:mark_hidden",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        self.client.post(url)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)
