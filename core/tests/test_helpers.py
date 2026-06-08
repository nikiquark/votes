from django.test import TestCase
from django.utils import timezone

from core.help import html_to_plain_text
from core.models import Choice, Poll, PollUser, Question, UserChoice
from core.tests.helpers import create_org_user
from core.views import calculate_poll_results


class CalculatePollResultsTests(TestCase):
    def setUp(self):
        self.org_user = create_org_user()
        self.poll = Poll.objects.create(title="Опрос", creator=self.org_user)
        self.question = Question.objects.create(poll=self.poll, text="Любимый цвет?", type="question")
        self.red = Choice.objects.create(question=self.question, choice="Красный")
        self.blue = Choice.objects.create(question=self.question, choice="Синий")
        self.green = Choice.objects.create(question=self.question, choice="Зелёный")

    def _vote(self, choice, n):
        for i in range(n):
            user = PollUser.objects.create(
                poll=self.poll, email=f"{choice.choice}-{i}@example.com", name="У", is_voted=True
            )
            UserChoice.objects.create(choice=choice, user=user)

    def test_returns_none_when_poll_not_finished(self):
        self.assertIsNone(calculate_poll_results(self.poll))

        self.poll.time_start = timezone.now()
        self.poll.save()
        self.assertIsNone(calculate_poll_results(self.poll))

    def test_results_sorted_by_vote_count_desc_with_percentage(self):
        self._vote(self.red, 3)
        self._vote(self.blue, 1)
        # green gets 0 votes

        self.poll.time_start = timezone.now()
        self.poll.time_end = timezone.now()
        self.poll.save()

        results = calculate_poll_results(self.poll)
        self.assertEqual(len(results), 1)
        choices = results[0]["choices"]

        # Отсортировано по убыванию количества голосов
        self.assertEqual([c["choice"] for c in choices], [self.red, self.blue, self.green])
        self.assertEqual([c["vote_count"] for c in choices], [3, 1, 0])

        # voted_count = 4 (только is_voted=True участники)
        self.assertEqual(choices[0]["percentage"], 75.0)
        self.assertEqual(choices[1]["percentage"], 25.0)
        self.assertEqual(choices[2]["percentage"], 0)

    def test_percentage_is_zero_when_nobody_voted(self):
        self.poll.time_start = timezone.now()
        self.poll.time_end = timezone.now()
        self.poll.save()

        results = calculate_poll_results(self.poll)
        for choice_data in results[0]["choices"]:
            self.assertEqual(choice_data["vote_count"], 0)
            self.assertEqual(choice_data["percentage"], 0)


class HtmlToPlainTextTests(TestCase):
    def test_br_tags_become_newlines(self):
        self.assertEqual(html_to_plain_text("Привет<br/>Мир"), "Привет\nМир")
        self.assertEqual(html_to_plain_text("Привет<br>Мир"), "Привет\nМир")

    def test_links_are_converted_to_text_with_url(self):
        result = html_to_plain_text('Перейдите по <a target="_blank" href="http://example.com">ссылке</a>')
        self.assertEqual(result, "Перейдите по ссылке (http://example.com)")

    def test_other_tags_are_stripped(self):
        self.assertEqual(html_to_plain_text("<b>Жирный</b> текст"), "Жирный текст")

    def test_html_entities_are_decoded(self):
        result = html_to_plain_text("Tom&nbsp;&amp;&nbsp;Jerry &lt;3 &quot;friends&quot; &gt; enemies")
        self.assertEqual(result, 'Tom & Jerry <3 "friends" > enemies')

    def test_extra_blank_lines_collapsed_and_trimmed(self):
        result = html_to_plain_text("<br/><br/>Строка1<br/><br/><br/>Строка2<br/>")
        self.assertEqual(result, "Строка1\n\nСтрока2")
