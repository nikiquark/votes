import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import Choice, Poll, PollUser, Question
from core.tests.helpers import create_org_user


class PollLifecycleIntegrationTests(TestCase):
    """
    Сквозной сценарий использования приложения:
    создание опроса -> редактирование вопросов и участников ->
    запуск голосования -> голосование участников ->
    завершение -> подсчёт результатов.
    """

    def setUp(self):
        self.org_user = create_org_user(username="creator", email="creator@example.com")
        self.user = self.org_user.user
        self.client.login(username=self.user.username, password="testpass123")

    # ── 1. Создание опроса ──────────────────────────────────────────────────

    def _create_poll(self):
        questions = [
            {
                "question": "Любимый цвет?",
                "type": "question",
                "min": 1,
                "max": 1,
                "choices": ["Красный", "Синий"],
            },
            {
                "question": "Какие фрукты нравятся?",
                "type": "multiple",
                "min": 1,
                "max": 2,
                "choices": ["Яблоко", "Банан", "Груша"],
            },
        ]
        participants = [
            {"name": "Алексей", "email": "alex@example.com"},
            {"name": "Мария", "email": "maria@example.com"},
        ]
        response = self.client.post(
            reverse("core:create"),
            {
                "title": "Опрос про предпочтения",
                "questions_data": json.dumps(questions),
                "participants_data": json.dumps(participants),
            },
        )
        poll = Poll.objects.get(title="Опрос про предпочтения")
        self.assertRedirects(response, reverse("core:history_detail", kwargs={"pk": poll.pk}))
        return poll

    def test_full_poll_lifecycle(self):
        # 1. Создание опроса с вопросами и участниками
        poll = self._create_poll()
        self.assertEqual(poll.status, "WAITING")
        self.assertEqual(Question.objects.filter(poll=poll).count(), 2)
        self.assertEqual(PollUser.objects.filter(poll=poll).count(), 2)

        single_question = poll.questions.get(type="question")
        multiple_question = poll.questions.get(type="multiple")

        # 2. Редактирование участников: добавление, изменение, удаление
        add_url = reverse("core:add_participant", kwargs={"pk": poll.pk})
        add_response = self.client.post(
            add_url,
            data=json.dumps({"name": "Олег", "email": "oleg@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(add_response.status_code, 200)
        oleg_id = add_response.json()["id"]
        self.assertEqual(PollUser.objects.filter(poll=poll).count(), 3)

        detail_url = reverse("core:participant_detail", kwargs={"pk": poll.pk, "participant_id": oleg_id})
        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"name": "Олег Петров", "email": "oleg.petrov@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200)
        oleg = PollUser.objects.get(pk=oleg_id)
        self.assertEqual(oleg.name, "Олег Петров")
        self.assertEqual(oleg.email, "oleg.petrov@example.com")

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(PollUser.objects.filter(poll=poll).count(), 2)

        # 3. Редактирование вопросов: изменение и добавление
        question_list_url = reverse("core:question_list", kwargs={"pk": poll.pk})
        question_detail_url = reverse(
            "core:question_detail", kwargs={"pk": poll.pk, "question_id": single_question.pk}
        )
        edit_response = self.client.patch(
            question_detail_url,
            data=json.dumps(
                {
                    "question": "Любимый цвет неба?",
                    "type": "question",
                    "choices": ["Голубой", "Серый", "Розовый"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(edit_response.status_code, 200)
        single_question.refresh_from_db()
        self.assertEqual(single_question.text, "Любимый цвет неба?")
        self.assertEqual(single_question.choices.count(), 3)

        new_question_response = self.client.post(
            question_list_url,
            data=json.dumps(
                {
                    "question": "Любимое время года?",
                    "type": "question",
                    "choices": ["Лето", "Зима"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(new_question_response.status_code, 200)
        self.assertEqual(Question.objects.filter(poll=poll).count(), 3)

        season_question = Question.objects.get(poll=poll, text="Любимое время года?")
        delete_question_url = reverse(
            "core:question_detail", kwargs={"pk": poll.pk, "question_id": season_question.pk}
        )
        delete_question_response = self.client.delete(delete_question_url)
        self.assertEqual(delete_question_response.status_code, 200)
        self.assertEqual(Question.objects.filter(poll=poll).count(), 2)

        # 4. Запуск голосования — рассылаются письма участникам
        with patch("core.views.send_to_user") as mocked_send:
            start_response = self.client.post(
                reverse("core:start_poll", kwargs={"pk": poll.pk}),
                content_type="application/json",
            )
        self.assertEqual(start_response.status_code, 200)
        poll.refresh_from_db()
        self.assertIsNotNone(poll.time_start)
        self.assertEqual(poll.status, "PENDING")
        self.assertEqual(mocked_send.call_count, PollUser.objects.filter(poll=poll).count())

        # После старта изменение вопросов и участников запрещено
        forbidden_question_response = self.client.delete(question_detail_url)
        self.assertEqual(forbidden_question_response.status_code, 400)
        forbidden_participant_response = self.client.post(
            add_url,
            data=json.dumps({"name": "Поздний участник", "email": "late@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(forbidden_participant_response.status_code, 400)

        # 5. Голосование участников
        sky_question = single_question
        blue_choice = sky_question.choices.get(choice="Голубой")
        grey_choice = sky_question.choices.get(choice="Серый")
        apple_choice = multiple_question.choices.get(choice="Яблоко")
        banana_choice = multiple_question.choices.get(choice="Банан")

        alex = poll.members.get(email="alex@example.com")
        maria = poll.members.get(email="maria@example.com")

        self._vote(poll, alex, {sky_question: blue_choice, multiple_question: [apple_choice, banana_choice]})
        self._vote(poll, maria, {sky_question: blue_choice, multiple_question: [apple_choice]})

        alex.refresh_from_db()
        maria.refresh_from_db()
        self.assertTrue(alex.is_voted)
        self.assertTrue(maria.is_voted)

        # Повторное голосование запрещено
        repeat_response = self._vote(
            poll, alex, {sky_question: grey_choice, multiple_question: [banana_choice]}, follow=True
        )
        self.assertContains(repeat_response, "Вы уже проголосовали.")
        self.assertEqual(blue_choice.count, 2)  # счётчик не изменился

        # 6. Завершение голосования
        end_response = self.client.post(
            reverse("core:end_poll", kwargs={"pk": poll.pk}),
            content_type="application/json",
        )
        self.assertEqual(end_response.status_code, 200)
        poll.refresh_from_db()
        self.assertIsNotNone(poll.time_end)
        self.assertEqual(poll.status, "FINISHED")

        # Повторное завершение запрещено
        repeat_end_response = self.client.post(
            reverse("core:end_poll", kwargs={"pk": poll.pk}),
            content_type="application/json",
        )
        self.assertEqual(repeat_end_response.status_code, 400)

        # 7. Подсчёт результатов
        detail_page = self.client.get(reverse("core:history_detail", kwargs={"pk": poll.pk}))
        self.assertEqual(detail_page.status_code, 200)
        results = detail_page.context["questions_with_results"]

        sky_results = next(r for r in results if r["question"].pk == sky_question.pk)["choices"]
        blue_result = next(c for c in sky_results if c["choice"].pk == blue_choice.pk)
        grey_result = next(c for c in sky_results if c["choice"].pk == grey_choice.pk)
        self.assertEqual(blue_result["vote_count"], 2)
        self.assertEqual(blue_result["percentage"], 100.0)
        self.assertEqual(grey_result["vote_count"], 0)
        # Отсортировано по убыванию голосов
        self.assertEqual(sky_results[0]["choice"].pk, blue_choice.pk)

        fruit_results = next(r for r in results if r["question"].pk == multiple_question.pk)["choices"]
        apple_result = next(c for c in fruit_results if c["choice"].pk == apple_choice.pk)
        banana_result = next(c for c in fruit_results if c["choice"].pk == banana_choice.pk)
        self.assertEqual(apple_result["vote_count"], 2)
        self.assertEqual(banana_result["vote_count"], 1)
        self.assertEqual(apple_result["percentage"], 100.0)
        self.assertEqual(banana_result["percentage"], 50.0)

    def _vote(self, poll, poll_user, answers, follow=False):
        """Отправляет голос участника. answers: {question: choice или [choices]}."""
        data = {}
        for question, choice in answers.items():
            field = f"question_{question.id}"
            if isinstance(choice, list):
                data[field] = [c.id for c in choice]
            else:
                data[field] = choice.id

        url = reverse("core:vote", kwargs={"poll_url": poll.url, "user_url": poll_user.url})
        # Голосование выполняется анонимным участником — выходим из аккаунта администратора
        self.client.logout()
        response = self.client.post(url, data=data, follow=follow)
        self.client.login(username=self.user.username, password="testpass123")
        return response


class PollEditingRestrictionsTests(TestCase):
    """Изменение вопросов/участников запрещено после старта голосования."""

    def setUp(self):
        self.org_user = create_org_user(username="creator2", email="creator2@example.com")
        self.user = self.org_user.user
        self.client.login(username=self.user.username, password="testpass123")
        self.poll = Poll.objects.create(title="Опрос", creator=self.org_user)
        self.question = Question.objects.create(poll=self.poll, text="Вопрос?", type="question")
        Choice.objects.create(question=self.question, choice="A")
        Choice.objects.create(question=self.question, choice="B")
        self.participant = PollUser.objects.create(poll=self.poll, email="p@example.com", name="P")

    def _start(self):
        with patch("core.views.send_to_user"):
            self.client.post(reverse("core:start_poll", kwargs={"pk": self.poll.pk}))
        self.poll.refresh_from_db()

    def test_title_can_be_edited_before_start_and_blocked_after(self):
        title_url = reverse("core:poll_title", kwargs={"pk": self.poll.pk})

        ok_response = self.client.patch(
            title_url,
            data=json.dumps({"title": "Новое название"}),
            content_type="application/json",
        )
        self.assertEqual(ok_response.status_code, 200)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.title, "Новое название")

        empty_response = self.client.patch(
            title_url,
            data=json.dumps({"title": "   "}),
            content_type="application/json",
        )
        self.assertEqual(empty_response.status_code, 400)

        self._start()
        blocked_response = self.client.patch(
            title_url,
            data=json.dumps({"title": "Опять новое"}),
            content_type="application/json",
        )
        self.assertEqual(blocked_response.status_code, 400)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.title, "Новое название")

    def test_question_crud_blocked_after_start(self):
        self._start()
        question_list_url = reverse("core:question_list", kwargs={"pk": self.poll.pk})
        question_detail_url = reverse(
            "core:question_detail", kwargs={"pk": self.poll.pk, "question_id": self.question.pk}
        )

        post_resp = self.client.post(
            question_list_url,
            data=json.dumps({"question": "Новый?", "type": "question", "choices": ["A", "B"]}),
            content_type="application/json",
        )
        self.assertEqual(post_resp.status_code, 400)

        patch_resp = self.client.patch(
            question_detail_url,
            data=json.dumps({"question": "Изменённый?", "type": "question", "choices": ["A", "B"]}),
            content_type="application/json",
        )
        self.assertEqual(patch_resp.status_code, 400)

        delete_resp = self.client.delete(question_detail_url)
        self.assertEqual(delete_resp.status_code, 400)

    def test_participant_crud_blocked_after_start(self):
        self._start()
        add_url = reverse("core:add_participant", kwargs={"pk": self.poll.pk})
        detail_url = reverse(
            "core:participant_detail", kwargs={"pk": self.poll.pk, "participant_id": self.participant.pk}
        )

        post_resp = self.client.post(
            add_url,
            data=json.dumps({"name": "Новый", "email": "new@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(post_resp.status_code, 400)

        patch_resp = self.client.patch(
            detail_url,
            data=json.dumps({"name": "Изменён", "email": "changed@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(patch_resp.status_code, 400)

        delete_resp = self.client.delete(detail_url)
        self.assertEqual(delete_resp.status_code, 400)

    def test_start_poll_twice_returns_error(self):
        self._start()
        with patch("core.views.send_to_user"):
            second_start = self.client.post(reverse("core:start_poll", kwargs={"pk": self.poll.pk}))
        self.assertEqual(second_start.status_code, 400)


class OrganizationIsolationTests(TestCase):
    """Пользователь не может управлять опросами чужой организации."""

    def setUp(self):
        self.owner = create_org_user(username="owner", email="owner@example.com")
        self.intruder = create_org_user(username="intruder", email="intruder@example.com")
        self.poll = Poll.objects.create(title="Чужой опрос", creator=self.owner)

    def test_intruder_cannot_view_foreign_poll(self):
        self.client.login(username=self.intruder.user.username, password="testpass123")
        response = self.client.get(reverse("core:history_detail", kwargs={"pk": self.poll.pk}))
        self.assertEqual(response.status_code, 404)

    def test_intruder_cannot_start_foreign_poll(self):
        self.client.login(username=self.intruder.user.username, password="testpass123")
        response = self.client.post(reverse("core:start_poll", kwargs={"pk": self.poll.pk}))
        self.assertEqual(response.status_code, 404)

    def test_foreign_poll_not_in_history_list(self):
        self.client.login(username=self.intruder.user.username, password="testpass123")
        response = self.client.get(reverse("core:history"))
        self.assertNotContains(response, "Чужой опрос")
