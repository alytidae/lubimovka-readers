from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.db import IntegrityError
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
from apps.reviews.services import MAX_ACTIVE_REVIEWS_PER_READER


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


class TestForcePhase2Service(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Force P2 Service Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.readers = []
        for i in range(3):
            user = User.objects.create_user(username=f"fp2sv_r{i}", password="pwd")
            CompetitionRole.objects.create(
                user=user, competition=cls.competition, role="reader"
            )
            cls.readers.append(user)

        cls.forced_play = Play.objects.create(
            competition=cls.competition,
            title="Forced Play",
            author_email="forced@test.com",
            is_active=True,
            force_phase_2=True,
        )
        cls.normal_play = Play.objects.create(
            competition=cls.competition,
            title="Normal Play",
            author_email="normal@test.com",
            is_active=True,
        )

    def test_forced_play_excluded_from_phase1_assignment(self):
        result = assign_play(self.readers[0], self.competition)
        self.assertTrue(result.success)
        self.assertEqual(result.play, self.normal_play)

    def test_auto_assign_phase2_includes_forced_play(self):
        self.competition.status = Competition.Status.PHASE_2
        self.competition.save()
        count = auto_assign_phase2(self.competition)
        self.assertEqual(count, 3)
        phase2_reviews = Review.objects.filter(
            play=self.forced_play, phase=Review.Phase.PHASE_2
        )
        self.assertEqual(phase2_reviews.count(), 3)

    def test_forced_play_overrides_negative_verdicts(self):
        comp = Competition.objects.create(
            title="Force P2 Override Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_2,
        )
        readers = []
        for i in range(2):
            user = User.objects.create_user(username=f"fp2ov_r{i}", password="pwd")
            CompetitionRole.objects.create(user=user, competition=comp, role="reader")
            readers.append(user)

        play = Play.objects.create(
            competition=comp,
            title="Override Play",
            author_email="override@test.com",
            is_active=True,
            force_phase_2=True,
        )
        extra1 = User.objects.create_user(username="fp2ov_e1", password="pwd")
        extra2 = User.objects.create_user(username="fp2ov_e2", password="pwd")
        Review.objects.create(
            reader=extra1,
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
        )
        Review.objects.create(
            reader=extra2,
            play=play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
        )

        count = auto_assign_phase2(comp)
        self.assertEqual(count, 2)
        phase2_reviews = Review.objects.filter(play=play, phase=Review.Phase.PHASE_2)
        self.assertEqual(phase2_reviews.count(), 2)


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

    def test_reader_gets_404_when_only_rejected_review_exists(self):
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
        self.review.is_hidden = False
        self.review.save()
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
        self.review.is_hidden = False
        self.review.save()
        self.client.force_login(self.admin)
        url = reverse(
            "reviews:mark_hidden",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        self.client.post(url)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)


class TestAssignPlayMaxActiveReviews(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Max Active Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="max_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        for i in range(MAX_ACTIVE_REVIEWS_PER_READER):
            play = Play.objects.create(
                competition=cls.competition,
                title=f"MaxPlay{i}",
                author_email=f"mp{i}@a.com",
                is_active=True,
            )
            Review.objects.create(
                reader=cls.reader,
                play=play,
                phase=Review.Phase.PHASE_1,
                status=Review.Status.ASSIGNED,
            )

    def test_reader_at_max_active_reviews_cannot_get_more(self):
        result = assign_play(self.reader, self.competition)
        self.assertFalse(result.success)


class TestSubmitService(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Submit Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="sub_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Submit Play",
            author_email="s@a.com",
            is_active=True,
        )

    def test_submit_already_submitted_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Done",
        )
        result = submit(review, verdict=True, comment="Again")
        self.assertFalse(result.success)

    def test_submit_without_verdict_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, verdict=None, comment="Some comment")
        self.assertFalse(result.success)

    def test_submit_without_comment_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, verdict=True, comment="")
        self.assertFalse(result.success)

    def test_submit_sets_submitted_at(self):
        play2 = Play.objects.create(
            competition=self.competition,
            title="Submit Play 2",
            author_email="s2@a.com",
            is_active=True,
        )
        review = Review.objects.create(
            reader=self.reader,
            play=play2,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, verdict=True, comment="Good")
        self.assertTrue(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.SUBMITTED)
        self.assertIsNotNone(review.submitted_at)


class TestRejectServiceEdgeCases(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Reject Edge Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="rej_edge_r", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Reject Edge Play",
            author_email="re@a.com",
            is_active=True,
        )

    def test_reject_draft_review_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.DRAFT,
        )
        result = reject(review)
        self.assertFalse(result.success)

    def test_reject_submitted_review_fails(self):
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


class TestAutoAssignPhase2EdgeCases(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="P2 Edge Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )

    def test_auto_assign_phase2_returns_zero_when_not_phase2(self):
        count = auto_assign_phase2(self.competition)
        self.assertEqual(count, 0)


class TestPhaseValidation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Phase Valid Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_2,
        )
        cls.reader = User.objects.create_user(username="pv_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Phase Valid Play",
            author_email="pv@a.com",
            is_active=True,
        )

    def test_save_draft_wrong_phase_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = save_draft(review, verdict=True, comment="Draft")
        self.assertFalse(result.success)

    def test_submit_wrong_phase_fails(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = submit(review, verdict=True, comment="Submit")
        self.assertFalse(result.success)


class TestMarkPublicHiddenService(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="PublicHidden Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader1 = User.objects.create_user(username="ph_r1", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader1, competition=cls.competition, role="reader"
        )
        cls.reader2 = User.objects.create_user(username="ph_r2", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader2, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="PublicHidden Play",
            author_email="ph@a.com",
            is_active=True,
        )
        cls.hidden_review = Review.objects.create(
            reader=cls.reader1,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
            is_hidden=True,
        )
        cls.visible_review = Review.objects.create(
            reader=cls.reader2,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
            is_hidden=False,
        )

    def test_mark_public_sets_is_hidden_false(self):
        result = mark_public(self.hidden_review)
        self.assertTrue(result.success)
        self.hidden_review.refresh_from_db()
        self.assertFalse(self.hidden_review.is_hidden)

    def test_mark_public_already_public_fails(self):
        result = mark_public(self.visible_review)
        self.assertFalse(result.success)

    def test_mark_hidden_sets_is_hidden_true(self):
        result = mark_hidden(self.visible_review)
        self.assertTrue(result.success)
        self.visible_review.refresh_from_db()
        self.assertTrue(self.visible_review.is_hidden)

    def test_mark_hidden_already_hidden_fails(self):
        result = mark_hidden(self.hidden_review)
        self.assertFalse(result.success)


class TestRestoreService(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Restore Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="rest_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Restore Play",
            author_email="rest@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
            is_obsolete=True,
        )

    def test_restore_sets_is_obsolete_false(self):
        result = restore(self.review)
        self.assertTrue(result.success)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_obsolete)

    def test_restore_already_active_fails(self):
        self.review.is_obsolete = False
        self.review.save()
        result = restore(self.review)
        self.assertFalse(result.success)


class TestMarkObsoleteService(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Obs Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="obs_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Obs Play",
            author_email="obs@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
            is_obsolete=False,
        )

    def test_mark_obsolete_already_obsolete_fails(self):
        self.review.is_obsolete = True
        self.review.save()
        result = mark_obsolete(self.review)
        self.assertFalse(result.success)

    def test_mark_obsolete_success(self):
        result = mark_obsolete(self.review)
        self.assertTrue(result.success)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_obsolete)


class TestReviewRequestPlayView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Request Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="req_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.mod = User.objects.create_user(username="req_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        Play.objects.create(
            competition=cls.competition,
            title="Request Play",
            author_email="rq@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_reader_can_request_play(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:request_play",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Review.objects.filter(
                reader=self.reader,
                play__competition=self.competition,
                phase=Review.Phase.PHASE_1,
            ).exists()
        )

    def test_moderator_cannot_request_play(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:request_play",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)


class TestReviewSubmitView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="SubView Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="sv_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="SubView Play",
            author_email="sv@a.com",
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

    def test_reader_can_submit_review(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:submit",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "True", "comment": "Great play"})
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.SUBMITTED)


class TestReviewRejectView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="RejView Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="rv_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="RejView Play",
            author_email="rv@a.com",
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

    def test_reader_can_reject_assigned_review(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.REJECTED)


class TestReviewMarkPublicView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="PubView Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.mod = User.objects.create_user(username="pvmod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="pvreader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="PubView Play",
            author_email="pv@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
            is_hidden=True,
        )

    def setUp(self):
        self.client = Client()

    def test_moderator_can_mark_public(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:mark_public",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_hidden)

    def test_reader_can_mark_public(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:mark_public",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_hidden)


class TestReviewMarkHiddenModerator(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="HidModView Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.mod = User.objects.create_user(username="hmv_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="hmv_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="HidModView Play",
            author_email="hmv@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
            is_hidden=False,
        )

    def setUp(self):
        self.client = Client()

    def test_moderator_can_mark_hidden(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:mark_hidden",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)


class TestReviewUpdateView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="EditView Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.admin = User.objects.create_user(
            username="ev_admin", password="pwd", is_superuser=True
        )
        cls.role_admin = User.objects.create_user(username="ev_radm", password="pwd")
        CompetitionRole.objects.create(
            user=cls.role_admin, competition=cls.competition, role="admin"
        )
        cls.mod = User.objects.create_user(username="ev_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="ev_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="EditView Play",
            author_email="ev@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Original",
        )

    def setUp(self):
        self.client = Client()

    def test_superuser_can_edit_review(self):
        self.client.force_login(self.admin)
        url = reverse(
            "reviews:edit",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(
            url, {"verdict": "False", "comment": "Changed mind"}
        )
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertFalse(self.review.verdict)
        self.assertEqual(self.review.comment, "Changed mind")

    def test_role_admin_can_edit_review(self):
        self.client.force_login(self.role_admin)
        url = reverse(
            "reviews:edit",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "True", "comment": "Admin edit"})
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.comment, "Admin edit")

    def test_moderator_cannot_edit_review(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:edit",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "False", "comment": "Hack"})
        self.assertEqual(response.status_code, 403)

    def test_reader_cannot_edit_review(self):
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:edit",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "False", "comment": "Hack"})
        self.assertEqual(response.status_code, 403)


class TestAssignPlayNegativeVerdicts(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="NegVerdict Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.readers = []
        for i in range(3):
            user = User.objects.create_user(username=f"nv_r{i}", password="pwd")
            CompetitionRole.objects.create(
                user=user, competition=cls.competition, role="reader"
            )
            cls.readers.append(user)
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="NegVerdict Play",
            author_email="nv@a.com",
            is_active=True,
        )
        extra1 = User.objects.create_user(username="nv_e1", password="pwd")
        extra2 = User.objects.create_user(username="nv_e2", password="pwd")
        Review.objects.create(
            reader=extra1,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
        )
        Review.objects.create(
            reader=extra2,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=False,
            comment="No",
        )

    def test_play_excluded_after_two_negative_verdicts(self):
        result = assign_play(self.readers[0], self.competition)
        self.assertFalse(result.success)


class TestAssignPlayAlreadyReviewed(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="AlreadyRev Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="ar_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="AlreadyRev Play",
            author_email="ar@a.com",
            is_active=True,
        )
        Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Done",
        )

    def test_reader_cannot_be_assigned_same_play_twice(self):
        result = assign_play(self.reader, self.competition)
        self.assertFalse(result.success)


class TestAssignPlayNoAvailablePlays(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="NoPlays Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="np_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )

    def test_no_plays_available_returns_failure(self):
        result = assign_play(self.reader, self.competition)
        self.assertFalse(result.success)
        self.assertIsNone(result.play)


class TestSaveDraftService(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="DraftSvc Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="ds_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="DraftSvc Play",
            author_email="ds@a.com",
            is_active=True,
        )

    def test_save_draft_with_correct_phase_succeeds(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        result = save_draft(review, verdict=True, comment="Draft notes")
        self.assertTrue(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.DRAFT)
        self.assertTrue(review.verdict)
        self.assertEqual(review.comment, "Draft notes")


class TestReviewRemainingTime(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Remaining Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="rem_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Remaining Play",
            author_email="rem@a.com",
            is_active=True,
        )

    def test_overdue_review(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        review.created_at = timezone.now() - timezone.timedelta(days=15)
        review.save()
        self.assertIn(review.remaining_time, ["Overdue", "Просрочено"])

    def test_review_within_deadline(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        remaining = review.remaining_time
        self.assertNotEqual(remaining, "Overdue")
        self.assertTrue(len(remaining) > 0)


class TestAutoAssignPhase2NoQualifyingPlays(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="NoQual Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_2,
        )
        cls.reader = User.objects.create_user(username="nq_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="NoQual Play",
            author_email="nq@a.com",
            is_active=True,
        )

    def test_no_qualifying_plays_returns_zero(self):
        count = auto_assign_phase2(self.competition)
        self.assertEqual(count, 0)


class TestAutoAssignPhase2NoActiveReaders(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="NoReaders Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_2,
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="NoReaders Play",
            author_email="nr@a.com",
            is_active=True,
        )
        reader1 = User.objects.create_user(username="nr_r1", password="pwd")
        reader2 = User.objects.create_user(username="nr_r2", password="pwd")
        Review.objects.create(
            reader=reader1,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
        )
        Review.objects.create(
            reader=reader2,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
        )

    def test_no_active_readers_returns_zero(self):
        count = auto_assign_phase2(self.competition)
        self.assertEqual(count, 0)


class TestReaderCannotSaveDraftForAnotherReader(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="DraftOther Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader1 = User.objects.create_user(username="do_r1", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader1, competition=cls.competition, role="reader"
        )
        cls.reader2 = User.objects.create_user(username="do_r2", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader2, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="DraftOther Play",
            author_email="do@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader1,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )

    def setUp(self):
        self.client = Client()

    def test_reader_cannot_save_draft_for_another_reader(self):
        self.client.force_login(self.reader2)
        url = reverse(
            "reviews:save_draft",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "True", "comment": "Hack"})
        self.assertEqual(response.status_code, 403)


class TestReaderCannotSubmitAnotherReaderReview(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="SubOther Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader1 = User.objects.create_user(username="so_r1", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader1, competition=cls.competition, role="reader"
        )
        cls.reader2 = User.objects.create_user(username="so_r2", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader2, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="SubOther Play",
            author_email="so@a.com",
            is_active=True,
        )
        cls.review = Review.objects.create(
            reader=cls.reader1,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )

    def setUp(self):
        self.client = Client()

    def test_reader_cannot_submit_another_readers_review(self):
        self.client.force_login(self.reader2)
        url = reverse(
            "reviews:submit",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "True", "comment": "Hack"})
        self.assertEqual(response.status_code, 403)


class TestRejectWrongPhase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="RejPhase Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_2,
        )
        cls.reader = User.objects.create_user(username="rp_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="RejPhase Play",
            author_email="rp@a.com",
            is_active=True,
        )

    def test_reject_phase1_review_in_phase2_fails(self):
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


class TestReviewUniqueConstraint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="RevUniq Comp", date=date(2026, 1, 1)
        )
        cls.reader = User.objects.create_user(username="ru_reader", password="pwd")
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="RevUniq Play",
            author_email="ru@a.com",
            is_active=True,
        )

    def test_duplicate_review_raises_integrity_error(self):
        Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                reader=self.reader,
                play=self.play,
                phase=Review.Phase.PHASE_1,
                status=Review.Status.ASSIGNED,
            )

    def test_same_reader_different_phase_ok(self):
        Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.ASSIGNED,
        )
        review2 = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_2,
            status=Review.Status.ASSIGNED,
        )
        self.assertIsNotNone(review2.pk)


class TestSaveDraftUpdateExisting(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="DraftUpd Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="du_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="DraftUpd Play",
            author_email="du@a.com",
            is_active=True,
        )

    def test_save_draft_updates_existing_draft(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.DRAFT,
            verdict=True,
            comment="First draft",
        )
        result = save_draft(review, verdict=False, comment="Updated draft")
        self.assertTrue(result.success)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.DRAFT)
        self.assertFalse(review.verdict)
        self.assertEqual(review.comment, "Updated draft")


class TestReviewRejectNonAssignedView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="RejNonAssgn Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.reader = User.objects.create_user(username="rna_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="RejNonAssgn Play",
            author_email="rna@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_reject_submitted_review_returns_404(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Done",
        )
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_reject_draft_review_returns_404(self):
        review = Review.objects.create(
            reader=self.reader,
            play=self.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.DRAFT,
            verdict=True,
            comment="Draft",
        )
        self.client.force_login(self.reader)
        url = reverse(
            "reviews:reject",
            kwargs={"competition_slug": self.competition.slug, "pk": review.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)


class TestModeratorCannotSaveDraftOrSubmit(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="ModNoAct Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.mod = User.objects.create_user(username="mna_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="mna_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="ModNoAct Play",
            author_email="mna@a.com",
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

    def test_moderator_cannot_save_draft(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:save_draft",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "True", "comment": "Hack"})
        self.assertEqual(response.status_code, 403)

    def test_moderator_cannot_submit(self):
        self.client.force_login(self.mod)
        url = reverse(
            "reviews:submit",
            kwargs={"competition_slug": self.competition.slug, "pk": self.review.pk},
        )
        response = self.client.post(url, {"verdict": "True", "comment": "Hack"})
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_request_play(self):
        admin = User.objects.create_user(username="mna_admin", password="pwd")
        CompetitionRole.objects.create(
            user=admin, competition=self.competition, role="admin"
        )
        self.client.force_login(admin)
        url = reverse(
            "reviews:request_play",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_cannot_request_play(self):
        superuser = User.objects.create_user(
            username="mna_super", password="pwd", is_superuser=True
        )
        self.client.force_login(superuser)
        url = reverse(
            "reviews:request_play",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
