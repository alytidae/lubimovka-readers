import json
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from apps.users.models import User
from apps.competitions.models import Competition, CompetitionRole
from apps.plays.models import Play
from apps.competitions.services import sync_plays_from_google_sheet
from apps.reviews.models import Review
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import IntegrityError


class TestCompetitionIsolation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.comp_a = Competition.objects.create(title="Comp A", date=date(2026, 1, 1))
        cls.comp_b = Competition.objects.create(title="Comp B", date=date(2026, 2, 1))

        cls.user = User.objects.create_user(username="user", password="pwd")
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
            google_credentials=json.dumps({"type": "service_account"}),
            play_title_sheet_column_name="Title",
            play_url_sheet_column_name="Link",
            play_author_email_sheet_column_name="Email",
            play_author_first_name_sheet_column_name="Name",
            play_author_last_name_sheet_column_name="Surname",
            play_author_year_of_birth_sheet_column_name="Year",
        )

    @patch("apps.competitions.services.gspread.service_account_from_dict")
    def test_sync_creates_new_plays_and_skips_invalid(
        self, mock_service_account_from_dict
    ):
        mock_gc = mock_service_account_from_dict.return_value
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
            username="trans_admin", password="pwd", is_superuser=True
        )
        cls.competition = Competition.objects.create(
            title="Trans Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.readers = []
        for i in range(2):
            user = User.objects.create_user(username=f"trans_r{i}", password="pwd")
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
        extra1 = User.objects.create_user(username="trans_e1", password="pwd")
        extra2 = User.objects.create_user(username="trans_e2", password="pwd")
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


class TestForcePhase2Transition(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            username="fp2t_admin", password="pwd", is_superuser=True
        )
        cls.competition = Competition.objects.create(
            title="Force P2 Trans Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.readers = []
        for i in range(2):
            user = User.objects.create_user(username=f"fp2t_r{i}", password="pwd")
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

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_forced_play_gets_phase2_reviews_on_transition(self):
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
            play=self.forced_play, phase=Review.Phase.PHASE_2
        )
        self.assertEqual(phase2_reviews.count(), 2)
        for reader in self.readers:
            self.assertTrue(phase2_reviews.filter(reader=reader).exists())


class TestRoleAdminCanUpdateCompetition(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Role Admin Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.role_admin = User.objects.create_user(username="role_admin", password="pwd")
        CompetitionRole.objects.create(
            user=cls.role_admin,
            competition=cls.competition,
            role="admin",
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.role_admin)

    def test_role_admin_can_update_competition(self):
        url = reverse("competitions:update", kwargs={"slug": self.competition.slug})
        response = self.client.post(
            url,
            {
                "title": "Updated Title",
                "date": self.competition.date.strftime("%Y-%m-%d"),
                "status": Competition.Status.PHASE_1,
                "are_phase1_reviews_visible": True,
                "are_phase2_reviews_visible": False,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.title, "Updated Title")

    def test_reader_cannot_update_competition(self):
        reader = User.objects.create_user(username="ra_reader", password="pwd")
        CompetitionRole.objects.create(
            user=reader, competition=self.competition, role="reader"
        )
        self.client.force_login(reader)
        url = reverse("competitions:update", kwargs={"slug": self.competition.slug})
        response = self.client.post(
            url,
            {
                "title": "Hacked",
                "date": self.competition.date.strftime("%Y-%m-%d"),
                "status": Competition.Status.PHASE_1,
                "are_phase1_reviews_visible": False,
                "are_phase2_reviews_visible": False,
            },
        )
        self.assertEqual(response.status_code, 403)


class TestCompetitionSlugGeneration(TestCase):
    def test_slug_auto_generated_on_save(self):
        comp = Competition.objects.create(
            title="My Competition",
            date=date(2026, 3, 15),
            play_title_sheet_column_name="Title",
            play_url_sheet_column_name="Link",
            play_author_email_sheet_column_name="Email",
            play_author_first_name_sheet_column_name="Name",
        )
        self.assertTrue(comp.slug)
        self.assertIn("my-competition", comp.slug)


class TestCompetitionSyncView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            username="sync_admin", password="pwd", is_superuser=True
        )
        cls.competition = Competition.objects.create(
            title="SyncView Comp",
            date=date(2026, 1, 1),
            google_sheet_url="http://fake-url.com",
            google_credentials=json.dumps({"type": "service_account"}),
            play_title_sheet_column_name="Title",
            play_url_sheet_column_name="Link",
            play_author_email_sheet_column_name="Email",
            play_author_first_name_sheet_column_name="Name",
            play_author_last_name_sheet_column_name="Surname",
            play_author_year_of_birth_sheet_column_name="Year",
        )
        cls.reader = User.objects.create_user(username="sync_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )

    def setUp(self):
        self.client = Client()

    @patch("apps.competitions.views.sync_plays_from_google_sheet")
    def test_admin_can_trigger_sync(self, mock_sync):
        mock_sync.return_value = 3
        self.client.force_login(self.admin_user)
        url = reverse(
            "competitions:sync",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        mock_sync.assert_called_once()

    def test_reader_cannot_trigger_sync(self):
        self.client.force_login(self.reader)
        url = reverse(
            "competitions:sync",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)


class TestCompetitionAnalyticsView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Analytics Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.admin_user = User.objects.create_user(
            username="an_admin", password="pwd", is_superuser=True
        )
        cls.mod = User.objects.create_user(username="an_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="an_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Analytics Play",
            author_email="an@a.com",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    def test_admin_can_access_analytics(self):
        self.client.force_login(self.admin_user)
        url = reverse("competitions:analytics", kwargs={"slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("top_readers", response.context)
        self.assertIn("plays_overview", response.context)
        self.assertIn("controversial_plays", response.context)
        self.assertIn("total_yes", response.context)
        self.assertIn("total_no", response.context)
        self.assertIn("eta_days", response.context)
        self.assertIn("velocity_per_day", response.context)
        self.assertIn("progress_percent", response.context)
        self.assertIn("selected_phase", response.context)

    def test_moderator_can_access_analytics(self):
        self.client.force_login(self.mod)
        url = reverse("competitions:analytics", kwargs={"slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_reader_cannot_access_analytics(self):
        self.client.force_login(self.reader)
        url = reverse("competitions:analytics", kwargs={"slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_analytics_default_phase_matches_competition_status(self):
        self.client.force_login(self.admin_user)
        url = reverse("competitions:analytics", kwargs={"slug": self.competition.slug})
        response = self.client.get(url)
        self.assertEqual(response.context["selected_phase"], "phase_1")

    def test_analytics_phase_filter(self):
        self.client.force_login(self.admin_user)
        url = reverse("competitions:analytics", kwargs={"slug": self.competition.slug})
        response = self.client.get(url + "?phase=phase_2")
        self.assertEqual(response.context["selected_phase"], "phase_2")


class TestCompetitionExportExcelView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="Export Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_1,
        )
        cls.admin_user = User.objects.create_user(
            username="ex_admin", password="pwd", is_superuser=True
        )
        cls.mod = User.objects.create_user(username="ex_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.reader = User.objects.create_user(username="ex_reader", password="pwd")
        CompetitionRole.objects.create(
            user=cls.reader, competition=cls.competition, role="reader"
        )
        cls.play = Play.objects.create(
            competition=cls.competition,
            title="Export Play",
            author_email="ex@a.com",
            author_first_name="John",
            is_active=True,
        )
        Review.objects.create(
            reader=cls.reader,
            play=cls.play,
            phase=Review.Phase.PHASE_1,
            status=Review.Status.SUBMITTED,
            verdict=True,
            comment="Good",
        )

    def setUp(self):
        self.client = Client()

    def test_admin_can_export_excel(self):
        self.client.force_login(self.admin_user)
        url = reverse(
            "competitions:export",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(
            f'filename="{self.competition.slug}_full_export.xlsx"',
            response["Content-Disposition"],
        )

    def test_moderator_can_export_excel(self):
        self.client.force_login(self.mod)
        url = reverse(
            "competitions:export",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_reader_cannot_export_excel(self):
        self.client.force_login(self.reader)
        url = reverse(
            "competitions:export",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class TestCompetitionGoogleCredentialsEncryption(TestCase):
    def test_credentials_encrypted_on_first_save(self):
        comp = Competition.objects.create(
            title="Encrypt Comp",
            date=date(2026, 1, 1),
            google_credentials='{"type": "service_account"}',
            play_title_sheet_column_name="Title",
            play_url_sheet_column_name="Link",
            play_author_email_sheet_column_name="Email",
            play_author_first_name_sheet_column_name="Name",
        )
        comp.refresh_from_db()
        self.assertNotEqual(comp.google_credentials, '{"type": "service_account"}')
        f = Fernet(settings.FERNET_KEY.encode("utf-8"))
        decrypted = f.decrypt(comp.google_credentials.encode("utf-8")).decode("utf-8")
        self.assertEqual(decrypted, '{"type": "service_account"}')

    def test_credentials_not_re_encrypted_on_subsequent_save(self):
        comp = Competition.objects.create(
            title="ReEncrypt Comp",
            date=date(2026, 1, 1),
            google_credentials='{"type": "service_account"}',
            play_title_sheet_column_name="Title",
            play_url_sheet_column_name="Link",
            play_author_email_sheet_column_name="Email",
            play_author_first_name_sheet_column_name="Name",
        )
        comp.refresh_from_db()
        encrypted_value = comp.google_credentials
        comp.title = "ReEncrypt Comp Updated"
        comp.save()
        comp.refresh_from_db()
        self.assertEqual(comp.google_credentials, encrypted_value)


class TestCompetitionListViewSuperuser(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.comp_a = Competition.objects.create(title="SList A", date=date(2026, 1, 1))
        cls.comp_b = Competition.objects.create(title="SList B", date=date(2026, 2, 1))
        cls.superuser = User.objects.create_user(
            username="slist_admin", password="pwd", is_superuser=True
        )

    def test_superuser_sees_all_competitions(self):
        client = Client()
        client.force_login(self.superuser)
        url = reverse("competitions:list")
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        competitions = list(response.context["competitions"])
        self.assertIn(self.comp_a, competitions)
        self.assertIn(self.comp_b, competitions)


class TestCompetitionDetailViewSuperuser(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="SuperDetail Comp", date=date(2026, 1, 1)
        )
        cls.superuser = User.objects.create_user(
            username="sd_admin", password="pwd", is_superuser=True
        )

    def test_superuser_can_access_competition_detail(self):
        client = Client()
        client.force_login(self.superuser)
        url = reverse("competitions:detail", kwargs={"slug": self.competition.slug})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)


class TestCompetitionSyncViewModeratorAndAdmin(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="SyncPerm Comp",
            date=date(2026, 1, 1),
            google_sheet_url="http://fake-url.com",
            google_credentials=json.dumps({"type": "service_account"}),
            play_title_sheet_column_name="Title",
            play_url_sheet_column_name="Link",
            play_author_email_sheet_column_name="Email",
            play_author_first_name_sheet_column_name="Name",
            play_author_last_name_sheet_column_name="Surname",
            play_author_year_of_birth_sheet_column_name="Year",
        )
        cls.mod = User.objects.create_user(username="sp_mod", password="pwd")
        CompetitionRole.objects.create(
            user=cls.mod, competition=cls.competition, role="moderator"
        )
        cls.role_admin = User.objects.create_user(username="sp_radm", password="pwd")
        CompetitionRole.objects.create(
            user=cls.role_admin, competition=cls.competition, role="admin"
        )

    def setUp(self):
        self.client = Client()

    @patch("apps.competitions.views.sync_plays_from_google_sheet")
    def test_moderator_can_trigger_sync(self, mock_sync):
        mock_sync.return_value = 1
        self.client.force_login(self.mod)
        url = reverse(
            "competitions:sync",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        mock_sync.assert_called_once()

    @patch("apps.competitions.views.sync_plays_from_google_sheet")
    def test_role_admin_can_trigger_sync(self, mock_sync):
        mock_sync.return_value = 1
        self.client.force_login(self.role_admin)
        url = reverse(
            "competitions:sync",
            kwargs={"competition_slug": self.competition.slug},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        mock_sync.assert_called_once()


class TestCompetitionPhaseReverseTransition(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            username="rev_admin", password="pwd", is_superuser=True
        )
        cls.competition = Competition.objects.create(
            title="RevTrans Comp",
            date=date(2026, 1, 1),
            status=Competition.Status.PHASE_2,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_update_from_phase2_to_phase1(self):
        url = reverse("competitions:update", kwargs={"slug": self.competition.slug})
        response = self.client.post(
            url,
            {
                "title": self.competition.title,
                "date": self.competition.date.strftime("%Y-%m-%d"),
                "status": Competition.Status.PHASE_1,
                "are_phase1_reviews_visible": False,
                "are_phase2_reviews_visible": False,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.status, Competition.Status.PHASE_1)


class TestCompetitionRoleUniqueConstraint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.competition = Competition.objects.create(
            title="RoleUniq Comp", date=date(2026, 1, 1)
        )

    def test_duplicate_competition_role_raises_integrity_error(self):
        user = User.objects.create_user(username="ru_user", password="pwd")
        CompetitionRole.objects.create(
            user=user, competition=self.competition, role="reader"
        )
        with self.assertRaises(IntegrityError):
            CompetitionRole.objects.create(
                user=user, competition=self.competition, role="moderator"
            )
