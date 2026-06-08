"""
Браузерные интеграционные тесты (Selenium + headless Chrome).

Проверяют, что кнопки и модальные окна на страницах приложения
действительно выполняют свою задачу: запускают/завершают голосование,
редактируют участников и вопросы, копируют ссылку, отправляют голос и т.д.
"""
import json
from unittest.mock import patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.models import Choice, Poll, PollUser, Question
from core.tests.helpers import create_org_user


class SeleniumTestCase(StaticLiveServerTestCase):
    """Базовый класс: поднимает headless Chrome поверх живого тестового сервера."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,1024")
        cls.driver = webdriver.Chrome(options=options)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        super().tearDownClass()

    def wait(self, timeout=10):
        return WebDriverWait(self.driver, timeout)

    def login_as(self, user):
        """Авторизует браузер как `user`, переиспользуя сессию Django test client."""
        self.client.force_login(user)
        self.driver.get(self.live_server_url + "/")
        cookie = self.client.cookies["sessionid"]
        self.driver.add_cookie({"name": "sessionid", "value": cookie.value, "path": "/"})
        self.driver.refresh()

    def open(self, url_name, **kwargs):
        self.driver.get(self.live_server_url + reverse(url_name, **kwargs))


class LoginPageTests(SeleniumTestCase):
    def setUp(self):
        self.org_user = create_org_user(username="frontend_user", email="fe@example.com")
        self.user = self.org_user.user

    def test_login_form_logs_user_in_and_redirects_to_profile(self):
        self.driver.get(self.live_server_url + reverse("core:login"))

        self.driver.find_element(By.NAME, "username").send_keys(self.user.username)
        self.driver.find_element(By.NAME, "password").send_keys("testpass123")
        self.driver.find_element(By.CSS_SELECTOR, "button[type=submit]").click()

        self.wait().until(EC.url_contains(reverse("core:my")))
        self.assertIn(self.org_user.organization.name, self.driver.page_source)

    def test_login_form_shows_error_for_wrong_password(self):
        self.driver.get(self.live_server_url + reverse("core:login"))

        self.driver.find_element(By.NAME, "username").send_keys(self.user.username)
        self.driver.find_element(By.NAME, "password").send_keys("wrong-password")
        self.driver.find_element(By.CSS_SELECTOR, "button[type=submit]").click()

        self.wait().until(lambda d: "Сервис для голосования" not in d.title or True)
        self.assertIn(reverse("core:login"), self.driver.current_url)


class PollAdminButtonsTests(SeleniumTestCase):
    """Кнопки администрирования опроса на странице history_detail."""

    def setUp(self):
        self.org_user = create_org_user(username="admin_user", email="admin@example.com")
        self.user = self.org_user.user
        self.poll = Poll.objects.create(title="Опрос про кнопки", creator=self.org_user)
        self.question = Question.objects.create(poll=self.poll, text="Любимый цвет?", type="question")
        self.choice_a = Choice.objects.create(question=self.question, choice="Красный")
        self.choice_b = Choice.objects.create(question=self.question, choice="Синий")
        self.participant = PollUser.objects.create(poll=self.poll, name="Алексей", email="alex@example.com")
        self.login_as(self.user)

    def _open_detail(self):
        self.open("core:history_detail", kwargs={"pk": self.poll.pk})

    # ── Редактирование названия опроса ──────────────────────────────────────

    def test_edit_poll_title_via_ui(self):
        self._open_detail()
        self.wait().until(EC.element_to_be_clickable((By.ID, "editTitleBtn"))).click()

        title_input = self.wait().until(EC.visibility_of_element_located((By.ID, "pollTitleInput")))
        title_input.clear()
        title_input.send_keys("Обновлённое название опроса")
        self.driver.find_element(By.ID, "saveTitleBtn").click()

        self.wait().until(lambda d: "Обновлённое название опроса" in d.find_element(By.ID, "pollTitleText").text)
        self.assertTrue(self.driver.find_element(By.ID, "pollTitleEdit").get_attribute("class").find("d-none") != -1)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.title, "Обновлённое название опроса")

    def test_edit_poll_title_empty_shows_error(self):
        self._open_detail()
        self.wait().until(EC.element_to_be_clickable((By.ID, "editTitleBtn"))).click()

        title_input = self.wait().until(EC.visibility_of_element_located((By.ID, "pollTitleInput")))
        title_input.clear()
        self.driver.find_element(By.ID, "saveTitleBtn").click()

        error = self.wait().until(EC.visibility_of_element_located((By.ID, "pollTitleError")))
        self.assertIn("обязательно", error.text)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.title, "Опрос про кнопки")

    def test_edit_poll_title_cancel_keeps_original(self):
        self._open_detail()
        self.wait().until(EC.element_to_be_clickable((By.ID, "editTitleBtn"))).click()

        title_input = self.wait().until(EC.visibility_of_element_located((By.ID, "pollTitleInput")))
        title_input.clear()
        title_input.send_keys("Это название не сохранится")
        self.driver.find_element(By.ID, "cancelTitleBtn").click()

        self.wait().until(EC.invisibility_of_element_located((By.ID, "pollTitleEdit")))
        self.assertEqual(self.driver.find_element(By.ID, "pollTitleText").text, "Опрос про кнопки")
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.title, "Опрос про кнопки")

    # ── Старт / окончание голосования ───────────────────────────────────────

    def test_start_voting_button_opens_modal_and_starts_poll(self):
        self._open_detail()
        start_btn = self.wait().until(EC.element_to_be_clickable((By.ID, "startVotingBtn")))
        start_btn.click()

        self.wait().until(EC.visibility_of_element_located((By.ID, "startVotingModal")))
        confirm_btn = self.driver.find_element(By.ID, "confirmStartBtn")

        with patch("core.views.send_to_user") as mocked_send:
            confirm_btn.click()
            # Страница перезагружается после успешного запуска -> кнопка "Начать" блокируется
            self.wait(15).until(
                lambda d: d.find_element(By.ID, "startVotingBtn").get_attribute("disabled") is not None
            )
            self.wait().until(lambda d: mocked_send.called or True)

        self.poll.refresh_from_db()
        self.assertIsNotNone(self.poll.time_start)
        self.assertEqual(mocked_send.call_count, 1)

        end_btn = self.driver.find_element(By.ID, "endVotingBtn")
        self.assertIsNone(end_btn.get_attribute("disabled"))

    def test_end_voting_button_finishes_poll(self):
        self.poll.time_start = timezone.now()
        self.poll.save()
        self._open_detail()

        end_btn = self.wait().until(EC.element_to_be_clickable((By.ID, "endVotingBtn")))
        self.assertIsNone(end_btn.get_attribute("disabled"))
        end_btn.click()

        self.wait().until(EC.visibility_of_element_located((By.ID, "endVotingModal")))
        self.driver.find_element(By.ID, "confirmEndBtn").click()

        self.wait(15).until(
            lambda d: d.find_element(By.ID, "endVotingBtn").get_attribute("disabled") is not None
        )
        self.poll.refresh_from_db()
        self.assertIsNotNone(self.poll.time_end)
        self.assertEqual(self.poll.status, "FINISHED")

    # ── Копирование ссылки участника ────────────────────────────────────────

    def test_copy_link_button_shows_copied_feedback(self):
        self._open_detail()
        copy_btn = self.wait().until(EC.element_to_be_clickable((By.CLASS_NAME, "copy-link-btn")))
        copy_btn.click()
        self.wait().until(lambda d: "Скопировано" in copy_btn.text)

    # ── CRUD участников ──────────────────────────────────────────────────────

    def test_add_edit_delete_participant_via_ui(self):
        self._open_detail()

        # Добавление
        self.wait().until(EC.element_to_be_clickable((By.ID, "addParticipantBtn"))).click()
        table = self.driver.find_element(By.ID, "participantsTable")
        new_row = self.wait().until(
            lambda d: table.find_element(By.CSS_SELECTOR, 'tr[data-participant-id=""]')
        )
        name_input = new_row.find_element(By.CSS_SELECTOR, ".cell-name input")
        email_input = new_row.find_element(By.CSS_SELECTOR, ".cell-email input")
        name_input.clear()
        name_input.send_keys("Новый участник")
        email_input.clear()
        email_input.send_keys("new.participant@example.com")
        new_row.find_element(By.CSS_SELECTOR, ".btn-save").click()

        self.wait().until(lambda d: new_row.find_elements(By.CSS_SELECTOR, ".copy-link-btn"))
        self.assertEqual(PollUser.objects.filter(poll=self.poll, email="new.participant@example.com").count(), 1)
        new_id = str(PollUser.objects.get(email="new.participant@example.com").pk)
        self.assertEqual(new_row.get_attribute("data-participant-id"), new_id)

        # Редактирование
        new_row.find_element(By.CSS_SELECTOR, ".btn-edit").click()
        email_input = self.wait().until(lambda d: new_row.find_element(By.CSS_SELECTOR, ".cell-email input"))
        email_input.clear()
        email_input.send_keys("changed.participant@example.com")
        new_row.find_element(By.CSS_SELECTOR, ".btn-save").click()

        self.wait().until(lambda d: "changed.participant@example.com" in new_row.text)
        self.assertTrue(
            PollUser.objects.filter(poll=self.poll, email="changed.participant@example.com").exists()
        )

        # Удаление через модальное подтверждение
        new_row.find_element(By.CSS_SELECTOR, ".btn-delete").click()
        self.wait().until(EC.visibility_of_element_located((By.ID, "confirmModal")))
        self.assertIn("Удалить участника", self.driver.find_element(By.ID, "confirmModalBody").text)
        self.driver.find_element(By.ID, "confirmModalOkBtn").click()

        self.wait().until(
            lambda d: not d.find_elements(By.CSS_SELECTOR, f'tr[data-participant-id="{new_id}"]')
        )
        self.assertFalse(PollUser.objects.filter(pk=new_id).exists())

    def test_delete_participant_cancel_keeps_row(self):
        self._open_detail()
        row = self.wait().until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f'tr[data-participant-id="{self.participant.pk}"]'))
        )
        row.find_element(By.CSS_SELECTOR, ".btn-delete").click()
        self.wait().until(EC.visibility_of_element_located((By.ID, "confirmModal")))

        # Кнопка "Нет" просто закрывает модалку, ничего не удаляя
        self.driver.find_element(By.ID, "confirmModal").find_element(
            By.CSS_SELECTOR, ".btn-secondary[data-bs-dismiss='modal']"
        ).click()
        self.wait().until_not(EC.visibility_of_element_located((By.ID, "confirmModal")))
        self.assertTrue(PollUser.objects.filter(pk=self.participant.pk).exists())

    # ── CRUD вопросов ────────────────────────────────────────────────────────

    def test_add_edit_delete_question_via_ui(self):
        self._open_detail()

        # Добавление вопроса
        self.wait().until(EC.element_to_be_clickable((By.ID, "addQuestionBtn"))).click()
        self.wait().until(EC.visibility_of_element_located((By.ID, "questionModal")))

        text_input = self.driver.find_element(By.ID, "qEditorText")
        text_input.send_keys("Любимое время года?")
        choice_inputs = self.driver.find_elements(By.CSS_SELECTOR, "#questionEditorContainer input[type=text]")[1:]
        choice_inputs[0].send_keys("Лето")
        choice_inputs[1].send_keys("Зима")
        self.driver.find_element(By.ID, "questionModalSaveBtn").click()

        self.wait().until_not(EC.visibility_of_element_located((By.ID, "questionModal")))
        self.wait().until(lambda d: "Любимое время года?" in d.page_source)
        new_question = Question.objects.get(poll=self.poll, text="Любимое время года?")
        self.assertEqual(new_question.choices.count(), 2)

        new_card = self.driver.find_element(By.CSS_SELECTOR, f'.question-card[data-question-id="{new_question.pk}"]')

        # Редактирование вопроса
        new_card.find_element(By.CSS_SELECTOR, ".btn-edit-question").click()
        self.wait().until(EC.visibility_of_element_located((By.ID, "questionModal")))
        text_input = self.wait().until(lambda d: d.find_element(By.ID, "qEditorText"))
        self.assertEqual(text_input.get_attribute("value"), "Любимое время года?")
        text_input.clear()
        text_input.send_keys("Какое время года нравится больше всего?")
        self.driver.find_element(By.ID, "questionModalSaveBtn").click()

        self.wait().until_not(EC.visibility_of_element_located((By.ID, "questionModal")))
        self.wait().until(lambda d: "Какое время года нравится больше всего?" in d.page_source)
        new_question.refresh_from_db()
        self.assertEqual(new_question.text, "Какое время года нравится больше всего?")

        # Удаление вопроса через модальное подтверждение
        new_card = self.driver.find_element(By.CSS_SELECTOR, f'.question-card[data-question-id="{new_question.pk}"]')
        new_card.find_element(By.CSS_SELECTOR, ".btn-delete-question").click()
        self.wait().until(EC.visibility_of_element_located((By.ID, "confirmModal")))
        self.assertIn("Удалить вопрос", self.driver.find_element(By.ID, "confirmModalBody").text)
        self.driver.find_element(By.ID, "confirmModalOkBtn").click()

        self.wait().until(
            lambda d: not d.find_elements(By.CSS_SELECTOR, f'.question-card[data-question-id="{new_question.pk}"]')
        )
        self.assertFalse(Question.objects.filter(pk=new_question.pk).exists())

    def test_question_editor_rejects_single_choice(self):
        self._open_detail()
        self.wait().until(EC.element_to_be_clickable((By.ID, "addQuestionBtn"))).click()
        self.wait().until(EC.visibility_of_element_located((By.ID, "questionModal")))

        self.driver.find_element(By.ID, "qEditorText").send_keys("Вопрос без вариантов")
        choice_inputs = self.driver.find_elements(By.CSS_SELECTOR, "#questionEditorContainer input[type=text]")[1:]
        choice_inputs[0].send_keys("Единственный вариант")
        # Второй вариант остаётся пустым -> сохранение должно показать ошибку и не закрыть модалку
        self.driver.find_element(By.ID, "questionModalSaveBtn").click()

        error = self.wait().until(EC.visibility_of_element_located((By.ID, "questionModalError")))
        self.assertIn("минимум 2 варианта", error.text)
        self.assertTrue(self.driver.find_element(By.ID, "questionModal").is_displayed())
        self.assertFalse(Question.objects.filter(poll=self.poll, text="Вопрос без вариантов").exists())


class VotePageTests(SeleniumTestCase):
    """Форма голосования: выбор вариантов, валидация мультивыбора, отправка."""

    def setUp(self):
        self.org_user = create_org_user(username="vote_admin", email="vote_admin@example.com")
        self.poll = Poll.objects.create(title="Опрос про фрукты", creator=self.org_user)

        self.single_question = Question.objects.create(poll=self.poll, text="Любимый цвет?", type="question")
        self.red = Choice.objects.create(question=self.single_question, choice="Красный")
        self.blue = Choice.objects.create(question=self.single_question, choice="Синий")

        self.multi_question = Question.objects.create(
            poll=self.poll, text="Какие фрукты нравятся?", type="multiple", min=1, max=2
        )
        self.apple = Choice.objects.create(question=self.multi_question, choice="Яблоко")
        self.banana = Choice.objects.create(question=self.multi_question, choice="Банан")
        self.pear = Choice.objects.create(question=self.multi_question, choice="Груша")

        self.poll_user = PollUser.objects.create(poll=self.poll, name="Голосующий", email="voter@example.com")

        self.poll.time_start = timezone.now()
        self.poll.save()

    def _open_vote_page(self):
        self.driver.get(
            self.live_server_url
            + reverse("core:vote", kwargs={"poll_url": self.poll.url, "user_url": self.poll_user.url})
        )

    def test_checkbox_disables_unchecked_when_max_reached(self):
        self._open_vote_page()
        self.wait().until(EC.presence_of_element_located((By.ID, "voteForm")))

        apple_box = self.driver.find_element(By.ID, f"choice_{self.apple.pk}")
        banana_box = self.driver.find_element(By.ID, f"choice_{self.banana.pk}")
        pear_box = self.driver.find_element(By.ID, f"choice_{self.pear.pk}")

        apple_box.click()
        banana_box.click()  # max = 2 -> остальные чекбоксы должны заблокироваться

        self.wait().until(lambda d: pear_box.get_attribute("disabled") is not None)
        self.assertIsNone(apple_box.get_attribute("disabled"))
        self.assertIsNone(banana_box.get_attribute("disabled"))

        # Снимаем один выбор -> блокировка снимается
        banana_box.click()
        self.wait().until(lambda d: pear_box.get_attribute("disabled") is None)

    def test_submitting_without_selecting_minimum_shows_validation_error(self):
        self._open_vote_page()
        self.wait().until(EC.presence_of_element_located((By.ID, "voteForm")))

        # Выбираем только обязательный одиночный вопрос, мультивыбор не трогаем (min=1)
        self.driver.find_element(By.ID, f"choice_{self.red.pk}").click()
        self.driver.find_element(By.CSS_SELECTOR, "button[type=submit]").click()

        error = self.wait().until(
            EC.visibility_of_element_located((By.ID, f"error_{self.multi_question.pk}"))
        )
        self.assertIn("Выберите минимум 1", error.text)
        # Форма не отправлена -> голос не засчитан
        self.poll_user.refresh_from_db()
        self.assertFalse(self.poll_user.is_voted)

    def test_full_vote_submission_marks_user_as_voted_and_blocks_repeat(self):
        self._open_vote_page()
        self.wait().until(EC.presence_of_element_located((By.ID, "voteForm")))

        self.driver.find_element(By.ID, f"choice_{self.blue.pk}").click()
        self.driver.find_element(By.ID, f"choice_{self.apple.pk}").click()
        self.driver.find_element(By.ID, f"choice_{self.banana.pk}").click()
        self.driver.find_element(By.CSS_SELECTOR, "button[type=submit]").click()

        self.wait().until(lambda d: "Вы уже проголосовали" in d.page_source)

        self.poll_user.refresh_from_db()
        self.assertTrue(self.poll_user.is_voted)
        self.assertEqual(self.blue.count, 1)
        self.assertEqual(self.apple.count, 1)
        self.assertEqual(self.banana.count, 1)

        # Повторное открытие страницы показывает то же сообщение, форма недоступна
        self._open_vote_page()
        self.wait().until(lambda d: "Вы уже проголосовали" in d.page_source)
        self.assertFalse(self.driver.find_elements(By.ID, "voteForm"))
