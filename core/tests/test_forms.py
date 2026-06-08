import json

from django.test import TestCase

from core.forms import PollCreationForm


def _form(questions=None, participants=None, title="Опрос"):
    if questions is None:
        questions = [
            {
                "question": "Любимый цвет?",
                "type": "question",
                "min": 1,
                "max": 1,
                "choices": ["Красный", "Синий"],
            }
        ]
    if participants is None:
        participants = [{"name": "Алексей", "email": "alex@example.com"}]
    return PollCreationForm(
        data={
            "title": title,
            "questions_data": json.dumps(questions),
            "participants_data": json.dumps(participants),
        }
    )


class PollCreationFormQuestionsTests(TestCase):
    def test_valid_form(self):
        form = _form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.cleaned_data["questions"]), 1)
        self.assertEqual(form.cleaned_data["questions"][0]["choices"], ["Красный", "Синий"])

    def test_requires_at_least_one_question(self):
        form = _form(questions=[])
        self.assertFalse(form.is_valid())
        self.assertIn("questions_data", form.errors)

    def test_question_text_required(self):
        form = _form(questions=[{"question": "  ", "type": "question", "choices": ["A", "B"]}])
        self.assertFalse(form.is_valid())

    def test_question_requires_at_least_two_choices(self):
        form = _form(questions=[{"question": "Вопрос?", "type": "question", "choices": ["Один"]}])
        self.assertFalse(form.is_valid())

    def test_invalid_question_type_rejected(self):
        form = _form(
            questions=[{"question": "Вопрос?", "type": "weird", "choices": ["A", "B"]}]
        )
        self.assertFalse(form.is_valid())

    def test_single_choice_question_normalizes_min_max_to_one(self):
        form = _form(
            questions=[
                {"question": "Вопрос?", "type": "question", "min": 5, "max": 9, "choices": ["A", "B"]}
            ]
        )
        self.assertTrue(form.is_valid(), form.errors)
        question = form.cleaned_data["questions"][0]
        self.assertEqual(question["min"], 1)
        self.assertEqual(question["max"], 1)

    def test_multiple_choice_min_greater_than_max_rejected(self):
        form = _form(
            questions=[
                {
                    "question": "Несколько?",
                    "type": "multiple",
                    "min": 3,
                    "max": 1,
                    "choices": ["A", "B", "C"],
                }
            ]
        )
        self.assertFalse(form.is_valid())

    def test_multiple_choice_max_cannot_exceed_choice_count(self):
        form = _form(
            questions=[
                {
                    "question": "Несколько?",
                    "type": "multiple",
                    "min": 0,
                    "max": 5,
                    "choices": ["A", "B"],
                }
            ]
        )
        self.assertFalse(form.is_valid())

    def test_multiple_choice_valid_range_accepted(self):
        form = _form(
            questions=[
                {
                    "question": "Несколько?",
                    "type": "multiple",
                    "min": 1,
                    "max": 2,
                    "choices": ["A", "B", "C"],
                }
            ]
        )
        self.assertTrue(form.is_valid(), form.errors)


class PollCreationFormParticipantsTests(TestCase):
    def test_participants_are_normalized(self):
        form = _form(participants=[{"name": "  Маша  ", "email": "  MASHA@Example.com "}])
        self.assertTrue(form.is_valid(), form.errors)
        participant = form.cleaned_data["participants"][0]
        self.assertEqual(participant["email"], "masha@example.com")
        self.assertEqual(participant["name"], "Маша")

    def test_duplicate_emails_are_deduplicated(self):
        form = _form(
            participants=[
                {"name": "Первый", "email": "dup@example.com"},
                {"name": "Второй", "email": "DUP@example.com"},
            ]
        )
        self.assertTrue(form.is_valid(), form.errors)
        emails = [p["email"] for p in form.cleaned_data["participants"]]
        self.assertEqual(emails, ["dup@example.com"])

    def test_participant_without_email_rejected(self):
        form = _form(participants=[{"name": "Без почты", "email": ""}])
        self.assertFalse(form.is_valid())

    def test_empty_participants_allowed(self):
        form = _form(participants=[])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["participants"], [])
