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
            are_phase1_reviews_visible=False
        )
        
        cls.reader = User.objects.create_user(email="reader@test.com", password="pwd")
        cls.mod = User.objects.create_user(email="mod@test.com", password="pwd")
        CompetitionRole.objects.create(user=cls.reader, competition=cls.competition, role='reader')
        CompetitionRole.objects.create(user=cls.mod, competition=cls.competition, role='moderator')
        
        cls.play = Play.objects.create(competition=cls.competition, title="Hidden Play", author_email="a@a.com", is_active=True)

    def setUp(self):
        self.client = Client()

    def test_reader_cannot_see_unassigned_play_in_list(self):
        self.client.force_login(self.reader)
        url = reverse('plays:list', kwargs={'competition_slug': self.competition.slug})
        response = self.client.get(url)
        self.assertNotIn(self.play, response.context['object_list'])

    def test_moderator_sees_all_plays_in_list(self):
        self.client.force_login(self.mod)
        url = reverse('plays:list', kwargs={'competition_slug': self.competition.slug})
        response = self.client.get(url)
        self.assertIn(self.play, response.context['object_list'])

    def test_reader_cannot_activate_play(self):
        self.client.force_login(self.reader)
        url = reverse('plays:activate', kwargs={'competition_slug': self.competition.slug, 'pk': self.play.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_moderator_can_deactivate_play(self):
        self.client.force_login(self.mod)
        url = reverse('plays:deactivate', kwargs={'competition_slug': self.competition.slug, 'pk': self.play.pk})
        self.client.post(url)
        self.play.refresh_from_db()
        self.assertFalse(self.play.is_active)
