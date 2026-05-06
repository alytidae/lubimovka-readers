from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from apps.users.models import User
from apps.competitions.models import Competition, CompetitionRole
from apps.plays.models import Play
from apps.competitions.services import sync_plays_from_google_sheet
from apps.reviews.models import Review


class TestCompetitionIsolation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.comp_a = Competition.objects.create(title="Comp A", date=date(2026, 1, 1))
        cls.comp_b = Competition.objects.create(title="Comp B", date=date(2026, 2, 1))

        cls.user = User.objects.create_user(email="user@test.com", password="pwd")
        # User is only reader in Comp A, no access to Comp B
        CompetitionRole.objects.create(
            user=cls.user, competition=cls.comp_a, role="reader"
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_user_sees_only_assigned_competitions(self):
        url = reverse("competitions:list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.comp_a, response.context["competitions"])
        self.assertNotIn(self.comp_b, response.context["competitions"])

    def test_user_cannot_access_unassigned_competition_detail(self):
        url = reverse("competitions:detail", kwargs={"slug": self.comp_b.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # Forbidden


class TestGoogleSheetSync(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Sync Comp",
            date=date(2026, 1, 1),
            google_sheet_url="http://fake-url.com",
            play_title_sheet_column_name="Title",
            play_url_sheet_column_name="Link",
            play_author_email_sheet_column_name="Email",
            play_author_first_name_sheet_column_name="Name",
            play_author_last_name_sheet_column_name="Surname",
            play_author_year_of_birth_sheet_column_name="Year",
        )

    @patch("apps.competitions.services.gspread.service_account")
    def test_sync_creates_new_plays_and_skips_invalid(self, mock_service_account):
        # Mocking the Google Sheets API response
        mock_gc = mock_service_account.return_value
        mock_sh = mock_gc.open_by_url.return_value
        mock_ws = mock_sh.get_worksheet.return_value

        mock_ws.get_all_records.return_value = [
            {
                "Email": "valid@test.com",
                "Title": "Good Play",
                "Link": "http://url",
                "Name": "John",
                "Surname": "Doe",
                "Year": "1990",
            },
            {"Email": "", "Title": "No Email Play"},  # Should be skipped
            {"Email": "update@test.com", "Title": "Old Title", "Link": "http://old"},
        ]

        # First sync
        count = sync_plays_from_google_sheet(self.competition)
        self.assertEqual(count, 2)
        self.assertEqual(Play.objects.filter(competition=self.competition).count(), 2)

        # Second sync with updated data for the same play
        mock_ws.get_all_records.return_value = [
            {"Email": "update@test.com", "Title": "Old Title", "Link": "http://NEW"}
        ]
        sync_plays_from_google_sheet(self.competition)

        # Check that it updated the existing play instead of creating a duplicate
        self.assertEqual(Play.objects.filter(competition=self.competition).count(), 2)
        updated_play = Play.objects.get(author_email="update@test.com")
        self.assertEqual(updated_play.url, "http://NEW")


class TestCompetitionStatusTransition(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            email="trans_admin@test.com", password="pwd", is_superuser=True
        )
        cls.competition = Competition.objects.create(
            title="Trans Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.readers = []
        for i in range(2):
            user = User.objects.create_user(
                email=f"trans_r{i}@test.com", password="pwd"
            )
            CompetitionRole.objects.create(
                user=user, competition=cls.competition, role="reader"
            )
            cls.readers.append(user)

        cls.play_approved = Play.objects.create(
            competition=cls.competition,
            title="Approved",
            author_email="approved@test.com",
            is_active=True,
        )
        extra1 = User.objects.create_user(email="trans_e1@test.com", password="pwd")
        extra2 = User.objects.create_user(email="trans_e2@test.com", password="pwd")
        Review.objects.create(
            reader=extra1,
            play=cls.play_approved,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
        )
        Review.objects.create(
            reader=extra2,
            play=cls.play_approved,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Yes",
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_update_to_phase2_triggers_auto_assignment(self):
        url = reverse("competitions:update", kwargs={"slug": self.competition.slug})
        response = self.client.post(
            url,
            {
                "title": self.competition.title,
                "date": self.competition.date.strftime("%Y-%m-%d"),
                "status": Competition.Status.PHASE_2,
                "are_phase1_reviews_visible": False,
                "are_phase2_reviews_visible": False,
            },
        )
        self.assertEqual(response.status_code, 302)

        phase2_reviews = Review.objects.filter(
            play=self.play_approved, phase=Review.Phase.PHASE_2
        )
        self.assertEqual(phase2_reviews.count(), 2)
        for reader in self.readers:
            self.assertTrue(phase2_reviews.filter(reader=reader).exists())

    def test_update_without_phase_change_does_not_assign(self):
        url = reverse("competitions:update", kwargs={"slug": self.competition.slug})
        self.client.post(
            url,
            {
                "title": self.competition.title,
                "date": self.competition.date.strftime("%Y-%m-%d"),
                "status": Competition.Status.PHASE_1,
                "are_phase1_reviews_visible": True,
                "are_phase2_reviews_visible": False,
            },
        )

        phase2_reviews = Review.objects.filter(
            play=self.play_approved, phase=Review.Phase.PHASE_2
        )
        self.assertEqual(phase2_reviews.count(), 0)

    def test_non_admin_cannot_update_competition(self):
        reader = self.readers[0]
        self.client.force_login(reader)
        url = reverse("competitions:update", kwargs={"slug": self.competition.slug})
        response = self.client.post(
            url,
            {
                "title": self.competition.title,
                "date": self.competition.date.strftime("%Y-%m-%d"),
                "status": Competition.Status.PHASE_2,
                "are_phase1_reviews_visible": False,
                "are_phase2_reviews_visible": False,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_create_competition_superuser_only(self):
        url = reverse("competitions:create")
        response = self.client.post(
            url,
            {
                "title": "New Comp",
                "date": "2026-06-01",
                "google_sheet_url": "",
                "play_title_sheet_column_name": "Title",
                "play_url_sheet_column_name": "Link",
                "play_author_email_sheet_column_name": "Email",
                "play_author_first_name_sheet_column_name": "Name",
                "play_author_last_name_sheet_column_name": "",
                "play_author_year_of_birth_sheet_column_name": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Competition.objects.filter(title="New Comp").exists())

    def test_create_competition_non_superuser_forbidden(self):
        self.client.force_login(self.readers[0])
        url = reverse("competitions:create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
