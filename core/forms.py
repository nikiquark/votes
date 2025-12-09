import json

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import OrganizationUser, Question, Choice


class OrganizationAuthenticationForm(AuthenticationForm):
    """
    Authentication form that allows login only for users bound to an organization.
    """

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not OrganizationUser.objects.filter(user=user).exists():
            raise forms.ValidationError(
                _("У вас нет доступа к организации."), code="no_organization"
            )


class PollCreationForm(forms.Form):
    """
    Plain form that accepts JSON payloads for dynamic questions/participants
    assembled on the client. Validation here keeps the view thin and the
    persistence logic straightforward.
    """

    title = forms.CharField(label="Тема опроса", max_length=400)
    questions_data = forms.CharField(widget=forms.HiddenInput)
    participants_data = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean_questions_data(self):
        raw_value = self.cleaned_data.get("questions_data") or "[]"
        try:
            questions = json.loads(raw_value)
        except Exception:
            raise ValidationError(_("Не удалось обработать вопросы."), code="invalid_json")

        if not isinstance(questions, list) or not questions:
            raise ValidationError(_("Добавьте хотя бы один вопрос."), code="empty")

        normalized_questions = []
        for idx, question in enumerate(questions):
            text = (question or {}).get("question", "").strip()
            q_type = (question or {}).get("type", "question")
            choices_raw = (question or {}).get("choices", []) or []
            min_value = (question or {}).get("min", 1)
            max_value = (question or {}).get("max", 1)

            if not text:
                raise ValidationError(_(f"Вопрос №{idx + 1} не заполнен."), code="empty_question")

            choices = [c.strip() for c in choices_raw if str(c).strip()]
            if len(choices) < 2:
                raise ValidationError(
                    _(f"Для вопроса №{idx + 1} добавьте минимум два варианта ответа."),
                    code="not_enough_choices",
                )

            if q_type not in ("question", "multiple"):
                raise ValidationError(_(f"Неверный тип вопроса №{idx + 1}."), code="invalid_type")

            # Normalize min/max for single-choice questions
            if q_type == "question":
                min_value = 1
                max_value = 1
            else:
                try:
                    min_value = int(min_value)
                    max_value = int(max_value)
                except (TypeError, ValueError):
                    raise ValidationError(
                        _(f"Мин/макс для вопроса №{idx + 1} должны быть числами."),
                        code="invalid_min_max",
                    )
                if min_value < 0 or max_value < 1 or min_value > max_value:
                    raise ValidationError(
                        _(f"Проверьте диапазон мультивыбора в вопросе №{idx + 1}."),
                        code="invalid_range",
                    )
                if max_value > len(choices):
                    raise ValidationError(
                        _(
                            f"Максимум ответов в вопросе №{idx + 1} "
                            "не может превышать количество вариантов."
                        ),
                        code="invalid_max",
                    )

            normalized_questions.append(
                {
                    "text": text,
                    "type": q_type,
                    "min": min_value,
                    "max": max_value,
                    "choices": choices,
                }
            )

        return normalized_questions

    def clean_participants_data(self):
        raw_value = self.cleaned_data.get("participants_data") or "[]"
        try:
            participants = json.loads(raw_value)
        except Exception:
            raise ValidationError(_("Не удалось обработать список участников."), code="invalid_json")

        if not isinstance(participants, list):
            raise ValidationError(_("Неверный формат участников."), code="invalid_format")

        normalized = []
        seen_emails = set()
        for participant in participants:
            email = (participant or {}).get("email", "").strip().lower()
            name = (participant or {}).get("name", "").strip()
            if not email and not name:
                continue
            if not email:
                raise ValidationError(_("Укажите email для каждого участника."), code="email_required")
            if email in seen_emails:
                # Skip silently to avoid UniqueConstraint violations; we keep first occurrence.
                continue
            seen_emails.add(email)
            normalized.append({"email": email, "name": name or _("Участник")})

        return normalized

    def clean(self):
        cleaned_data = super().clean()
        questions = cleaned_data.get("questions_data")
        participants = cleaned_data.get("participants_data")

        # If field-level cleaning already produced normalized lists, reuse them.
        if not isinstance(questions, list):
            questions = self.clean_questions_data()
        if not isinstance(participants, list):
            participants = self.clean_participants_data()

        cleaned_data["questions"] = questions
        cleaned_data["participants"] = participants
        return cleaned_data


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    Custom password change form with Russian labels and help text.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = _("Текущий пароль")
        self.fields["old_password"].widget.attrs.update(
            {"class": "form-control", "autofocus": True}
        )
        self.fields["new_password1"].label = _("Новый пароль")
        self.fields["new_password1"].widget.attrs.update({"class": "form-control"})
        self.fields["new_password2"].label = _("Подтверждение нового пароля")
        self.fields["new_password2"].widget.attrs.update({"class": "form-control"})


class VoteForm(forms.Form):
    """
    Dynamic form for voting on poll questions.
    Fields are created dynamically based on questions.
    """

    def __init__(self, questions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = questions
        
        for question in questions:
            choices = question.choices.all()
            choices_list = [(choice.id, choice.choice) for choice in choices]
            
            if question.type == "question":
                # Single choice - radio buttons
                self.fields[f"question_{question.id}"] = forms.ChoiceField(
                    label=question.text,
                    choices=choices_list,
                    widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
                    required=True,
                )
            else:
                # Multiple choice - checkboxes
                # Allow required=False if min is 0 (user can select 0 options)
                self.fields[f"question_{question.id}"] = forms.MultipleChoiceField(
                    label=question.text,
                    choices=choices_list,
                    widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
                    required=(question.min > 0),
                )
                # Store min/max for validation
                self.fields[f"question_{question.id}"].question_min = question.min
                self.fields[f"question_{question.id}"].question_max = question.max

    def clean(self):
        cleaned_data = super().clean()
        
        for question in self.questions:
            field_name = f"question_{question.id}"
            value = cleaned_data.get(field_name)
            
            if question.type == "multiple":
                # Validate min/max for multiple choice questions
                # If min is 0, empty selection is allowed
                selected_count = len(value) if value else 0
                
                if question.min > 0 and selected_count < question.min:
                    raise ValidationError(
                        _(f"Выберите минимум {question.min} вариант(ов) для вопроса: {question.text}"),
                        code="min_choices",
                    )
                if selected_count > question.max:
                    raise ValidationError(
                        _(f"Выберите максимум {question.max} вариант(ов) для вопроса: {question.text}"),
                        code="max_choices",
                    )
        
        return cleaned_data

