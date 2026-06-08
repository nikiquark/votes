from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.tests.helpers import create_org_user


class AuthFlowTests(TestCase):
    def setUp(self):
        self.org_user = create_org_user(username="john", email="john@example.com")
        self.user = self.org_user.user

    def test_landing_page_available(self):
        response = self.client.get(reverse("core:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сервис для голосования")

    def test_login_allowed_for_organization_user(self):
        response = self.client.post(
            reverse("core:login"),
            {"username": self.user.username, "password": "testpass123"},
        )
        self.assertRedirects(response, reverse("core:my"))

        profile_response = self.client.get(reverse("core:my"))
        expected_name = f"{self.user.last_name} {self.user.first_name}"
        self.assertContains(profile_response, expected_name)
        self.assertContains(profile_response, self.org_user.organization.name)

    def test_login_blocked_without_organization(self):
        User.objects.create_user(username="jane", password="password123")
        response = self.client.post(
            reverse("core:login"),
            {"username": "jane", "password": "password123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "У вас нет доступа к организации.")

    def test_login_with_wrong_password_rejected(self):
        response = self.client.post(
            reverse("core:login"),
            {"username": self.user.username, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_my_profile_requires_login(self):
        response = self.client.get(reverse("core:my"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response.url)
