import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Organization, OrganizationUser, Poll, PollUser, Question


class AuthFlowTests(TestCase):
    def setUp(self):
        self.password = "testpass123"
        self.user = User.objects.create_user(
            username="john",
            password=self.password,
            first_name="John",
            last_name="Doe",
        )
        self.organization = Organization.objects.create(
            name="Test Org",
            paid_until=timezone.localdate(),
        )
        OrganizationUser.objects.create(user=self.user, organization=self.organization)

    def test_landing_page_available(self):
        response = self.client.get(reverse("core:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "landing")

    def test_login_allowed_for_organization_user(self):
        response = self.client.post(
            reverse("core:login"),
            {"username": self.user.username, "password": self.password},
        )
        self.assertRedirects(response, reverse("core:my"))

        profile_response = self.client.get(reverse("core:my"))
        expected_name = f"{self.user.last_name} {self.user.first_name}"
        self.assertContains(profile_response, expected_name)
        self.assertContains(profile_response, self.organization.name)

    def test_login_blocked_without_organization(self):
        user_without_org = User.objects.create_user(
            username="jane", password="password123"
        )
        response = self.client.post(
            reverse("core:login"),
            {"username": user_without_org.username, "password": "password123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "У вас нет доступа к организации.")


class CreatePollTests(TestCase):
    def setUp(self):
        self.password = "testpass123"
        self.user = User.objects.create_user(
            username="john",
            password=self.password,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )
        self.organization = Organization.objects.create(
            name="Test Org", paid_until=timezone.localdate()
        )
        self.org_user = OrganizationUser.objects.create(
            user=self.user, organization=self.organization
        )
        self.client.login(username=self.user.username, password=self.password)

    def test_create_poll_flow(self):
        questions = [
            {
                "question": "Ваш любимый цвет?",
                "choices": ["Красный", "Синий"],
                "type": "question",
                "min": 1,
                "max": 1,
            }
        ]
        participants = [
            {"name": "Алексей", "email": "alex@example.com"},
            {"name": "Мария", "email": "maria@example.com"},
        ]

        response = self.client.post(
            reverse("core:create"),
            {
                "title": "Тестовый опрос",
                "questions_data": json.dumps(questions),
                "participants_data": json.dumps(participants),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Poll.objects.count(), 1)
        poll = Poll.objects.first()
        self.assertEqual(poll.title, "Тестовый опрос")
        self.assertEqual(poll.creator, self.org_user)
        self.assertEqual(PollUser.objects.filter(poll=poll).count(), 2)  # только участники
        # Проверяем, что admin_user не создан
        admin_user = PollUser.objects.filter(poll=poll, email=self.user.email).first()
        self.assertIsNone(admin_user)
        self.assertEqual(Question.objects.filter(poll=poll).count(), 1)
