from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Choice,
    Organization,
    OrganizationUser,
    Poll,
    PollUser,
    Question,
    UserChoice,
)
from core.tests.helpers import create_org_user


class OrganizationTests(TestCase):
    def test_is_active_true_when_paid_until_in_future(self):
        org = Organization.objects.create(
            name="Active Org", paid_until=timezone.localdate() + timedelta(days=1)
        )
        self.assertTrue(org.is_active)

    def test_is_active_true_when_paid_until_today(self):
        org = Organization.objects.create(name="Today Org", paid_until=timezone.localdate())
        self.assertTrue(org.is_active)

    def test_is_active_false_when_paid_until_in_past(self):
        org = Organization.objects.create(
            name="Expired Org", paid_until=timezone.localdate() - timedelta(days=1)
        )
        self.assertFalse(org.is_active)


class OrganizationUserTests(TestCase):
    def test_name_and_email_properties(self):
        org_user = create_org_user(
            username="alice", email="alice@example.com", first_name="Alice", last_name="Smith"
        )
        self.assertEqual(org_user.name, "Smith Alice")
        self.assertEqual(org_user.email, "alice@example.com")
        self.assertIn("Smith Alice", str(org_user))


class PollStatusTests(TestCase):
    def setUp(self):
        self.org_user = create_org_user()

    def _make_poll(self, **kwargs):
        return Poll.objects.create(title="Тестовый опрос", creator=self.org_user, **kwargs)

    def test_status_waiting_when_not_started(self):
        poll = self._make_poll()
        self.assertEqual(poll.status, "WAITING")

    def test_status_pending_when_started_but_not_finished(self):
        poll = self._make_poll(time_start=timezone.now())
        self.assertEqual(poll.status, "PENDING")

    def test_status_finished_when_started_and_finished(self):
        poll = self._make_poll(time_start=timezone.now(), time_end=timezone.now())
        self.assertEqual(poll.status, "FINISHED")


class PollUserConstraintTests(TestCase):
    def setUp(self):
        self.org_user = create_org_user()
        self.poll = Poll.objects.create(title="Опрос", creator=self.org_user)

    def test_duplicate_email_in_same_poll_raises(self):
        PollUser.objects.create(poll=self.poll, email="dup@example.com", name="Первый")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PollUser.objects.create(poll=self.poll, email="dup@example.com", name="Второй")

    def test_same_email_allowed_in_different_polls(self):
        other_poll = Poll.objects.create(title="Другой опрос", creator=self.org_user)
        PollUser.objects.create(poll=self.poll, email="shared@example.com", name="Участник")
        # Не должно бросать исключение
        PollUser.objects.create(poll=other_poll, email="shared@example.com", name="Участник")
        self.assertEqual(PollUser.objects.filter(email="shared@example.com").count(), 2)


class ChoiceCountTests(TestCase):
    def setUp(self):
        self.org_user = create_org_user()
        self.poll = Poll.objects.create(title="Опрос", creator=self.org_user)
        self.question = Question.objects.create(poll=self.poll, text="Вопрос?", type="question")
        self.choice_a = Choice.objects.create(question=self.question, choice="A")
        self.choice_b = Choice.objects.create(question=self.question, choice="B")

    def test_count_reflects_user_choices(self):
        user1 = PollUser.objects.create(poll=self.poll, email="u1@example.com", name="U1")
        user2 = PollUser.objects.create(poll=self.poll, email="u2@example.com", name="U2")

        self.assertEqual(self.choice_a.count, 0)

        UserChoice.objects.create(choice=self.choice_a, user=user1)
        UserChoice.objects.create(choice=self.choice_a, user=user2)
        UserChoice.objects.create(choice=self.choice_b, user=user2)

        self.assertEqual(self.choice_a.count, 2)
        self.assertEqual(self.choice_b.count, 1)

    def test_unique_choice_user_constraint(self):
        user = PollUser.objects.create(poll=self.poll, email="u@example.com", name="U")
        UserChoice.objects.create(choice=self.choice_a, user=user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserChoice.objects.create(choice=self.choice_a, user=user)
