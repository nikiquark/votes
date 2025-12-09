import json
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import FormView, TemplateView, ListView, DetailView
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

from .forms import OrganizationAuthenticationForm, PollCreationForm, CustomPasswordChangeForm, VoteForm
from .models import Choice, Poll, PollUser, Question, OrganizationUser, UserChoice
from .help import send_to_user


def calculate_poll_results(poll):
    """
    Вычисляет результаты голосования для опроса.
    Возвращает список словарей с вопросами и вариантами ответов с количеством голосов.
    """
    if not poll or not poll.time_end:
        return None
    
    questions_with_results = []
    for question in poll.questions.all().prefetch_related('choices'):
        choices_with_counts = []
        for choice in question.choices.all():
            vote_count = UserChoice.objects.filter(choice=choice).count()
            choices_with_counts.append({
                'choice': choice,
                'vote_count': vote_count
            })
        questions_with_results.append({
            'question': question,
            'choices': choices_with_counts
        })
    return questions_with_results


class LandingView(TemplateView):
    template_name = "core/landing.html"


class OrganizationLoginView(LoginView):
    template_name = "core/login.html"
    authentication_form = OrganizationAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        # Если есть параметр next, перенаправляем туда, иначе на my
        # LoginRequiredMixin добавляет параметр next в URL при редиректе на страницу входа
        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url:
            return next_url
        return reverse_lazy("core:my")


class MyProfileView(LoginRequiredMixin, TemplateView):
    template_name = "core/my.html"
    login_url = reverse_lazy("core:login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_user_qs = OrganizationUser.objects.select_related("organization").filter(
            user=self.request.user
        )
        current_org_id = self.request.session.get("current_org_id")

        org_user = None
        if current_org_id:
            org_user = org_user_qs.filter(organization_id=current_org_id).first()

        if not org_user:
            org_user = org_user_qs.first()

        if not org_user:
            logout(self.request)
            raise PermissionDenied("Организация для пользователя не найдена")

        context["organization_user"] = org_user
        context["organization"] = org_user.organization
        context["current_organization"] = org_user.organization
        return context


class CreatePlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = "core/create.html"
    login_url = reverse_lazy("core:login")


class CreatePollView(LoginRequiredMixin, FormView):
    template_name = "core/create.html"
    form_class = PollCreationForm
    login_url = reverse_lazy("core:login")
    success_url = reverse_lazy("core:create")

    def dispatch(self, request, *args, **kwargs):
        # LoginRequiredMixin проверяет авторизацию и возвращает редирект для неавторизованных
        # Проверяем авторизацию вручную перед использованием request.user в запросах
        if not request.user.is_authenticated:
            # Если не авторизован, LoginRequiredMixin обработает редирект
            return super().dispatch(request, *args, **kwargs)
        
        # После проверки авторизации можем безопасно использовать request.user
        self.org_user_qs = OrganizationUser.objects.select_related("organization").filter(
            user=request.user
        )
        if not self.org_user_qs.exists():
            logout(request)
            raise PermissionDenied("Организация для пользователя не найдена")
        current_org_id = request.session.get("current_org_id")
        self.organization_user = (
            self.org_user_qs.filter(organization_id=current_org_id).first()
            or self.org_user_qs.first()
        )
        if not self.organization_user.organization.is_active:
            raise PermissionDenied("Срок действия организации истек.")
        if not self.organization_user.email:
            raise PermissionDenied("У пользователя не указан email. Укажите email в профиле.")
        
        # Теперь вызываем super().dispatch() для обработки запроса
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Allow JSON payloads sent via fetch (application/json)
        if self.request.content_type and self.request.content_type.startswith(
            "application/json"
        ):
            try:
                payload = json.loads(self.request.body.decode("utf-8"))
            except Exception:
                payload = {}
            kwargs["data"] = payload
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["organization_user"] = self.organization_user
        context["organization"] = self.organization_user.organization
        context["current_organization"] = self.organization_user.organization
        context["user_organizations"] = [ou.organization for ou in self.org_user_qs]
        return context

    def form_valid(self, form):
        with transaction.atomic():
            poll = Poll.objects.create(
                title=form.cleaned_data["title"],
                creator=self.organization_user,
            )

            # Persist questions and choices
            for question_data in form.cleaned_data["questions"]:
                question = Question.objects.create(
                    poll=poll,
                    text=question_data["text"],
                    type=question_data["type"],
                    min=question_data["min"],
                    max=question_data["max"],
                )
                Choice.objects.bulk_create(
                    [
                        Choice(question=question, choice=choice_text)
                        for choice_text in question_data["choices"]
                    ]
                )

            participants = form.cleaned_data["participants"]
            # Deduplicate participants by email
            existing_emails = set()
            poll_users = []
            for participant in participants:
                email = participant["email"].strip().lower()
                if email in existing_emails:
                    continue
                existing_emails.add(email)
                poll_users.append(
                    PollUser(
                        poll=poll,
                        email=email,
                        name=participant["name"],
                    )
                )
            if poll_users:
                PollUser.objects.bulk_create(poll_users)

        messages.success(
            self.request,
            "Опрос создан",
        )
        return redirect("core:history_detail", pk=poll.pk)


class HistoryView(LoginRequiredMixin, ListView):
    """
    Отображает список всех опросов текущего пользователя для выбранной организации.
    Сортировка по created_at от новых к старым, пагинация по 10 элементов.
    """
    template_name = "core/history.html"
    login_url = reverse_lazy("core:login")
    context_object_name = "polls"
    paginate_by = 10

    def get_organization_user(self):
        """Получает OrganizationUser для текущего пользователя и выбранной организации."""
        org_user_qs = OrganizationUser.objects.select_related("organization").filter(
            user=self.request.user
        )
        current_org_id = self.request.session.get("current_org_id")

        org_user = None
        if current_org_id:
            org_user = org_user_qs.filter(organization_id=current_org_id).first()

        if not org_user:
            org_user = org_user_qs.first()

        if not org_user:
            logout(self.request)
            raise PermissionDenied("Организация для пользователя не найдена")

        return org_user

    def get_queryset(self):
        """Возвращает queryset опросов текущего пользователя в выбранной организации."""
        organization_user = self.get_organization_user()
        return (
            Poll.objects.filter(creator=organization_user)
            .select_related("creator", "creator__organization")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        """Добавляет organization_user в контекст."""
        context = super().get_context_data(**kwargs)
        organization_user = self.get_organization_user()
        context["organization_user"] = organization_user
        context["organization"] = organization_user.organization
        context["current_organization"] = organization_user.organization
        return context


class HistoryDetailView(LoginRequiredMixin, DetailView):
    """
    Отображает детальную информацию об опросе.
    Доступ только к опросам текущего пользователя в выбранной организации.
    """
    template_name = "core/history_detail.html"
    login_url = reverse_lazy("core:login")
    context_object_name = "poll"
    model = Poll

    def get_organization_user(self):
        """Получает OrganizationUser для текущего пользователя и выбранной организации."""
        org_user_qs = OrganizationUser.objects.select_related("organization").filter(
            user=self.request.user
        )
        current_org_id = self.request.session.get("current_org_id")

        org_user = None
        if current_org_id:
            org_user = org_user_qs.filter(organization_id=current_org_id).first()

        if not org_user:
            org_user = org_user_qs.first()

        if not org_user:
            logout(self.request)
            raise PermissionDenied("Организация для пользователя не найдена")

        return org_user

    def get_queryset(self):
        """Ограничивает queryset опросами текущего пользователя в выбранной организации."""
        organization_user = self.get_organization_user()
        return Poll.objects.filter(creator=organization_user).select_related(
            "creator", "creator__organization"
        )

    def get_object(self, queryset=None):
        """Получает объект опроса и проверяет права доступа."""
        if queryset is None:
            queryset = self.get_queryset()
        pk = self.kwargs.get(self.pk_url_kwarg)
        poll = get_object_or_404(queryset, pk=pk)
        return poll

    def get_context_data(self, **kwargs):
        """Добавляет organization_user в контекст."""
        context = super().get_context_data(**kwargs)
        organization_user = self.get_organization_user()
        context["organization_user"] = organization_user
        context["organization"] = organization_user.organization
        context["current_organization"] = organization_user.organization
        
        # Форматируем даты начала и конца опроса с учетом timezone организации
        poll = context.get("poll")
        try:
            org_timezone = ZoneInfo(organization_user.organization.timezone)
        except Exception:
            # Если timezone невалидный, используем UTC
            org_timezone = ZoneInfo("UTC")
        
        if poll and poll.time_start:
            try:
                # Убеждаемся, что datetime aware (имеет timezone)
                if timezone.is_naive(poll.time_start):
                    # Если naive, предполагаем UTC
                    local_time_start = timezone.make_aware(poll.time_start, timezone.utc).astimezone(org_timezone)
                else:
                    local_time_start = poll.time_start.astimezone(org_timezone)
                context["formatted_time_start"] = local_time_start.strftime("%d.%m.%Y, %H:%M:%S")
            except Exception:
                context["formatted_time_start"] = None
        else:
            context["formatted_time_start"] = None
            
        if poll and poll.time_end:
            try:
                # Убеждаемся, что datetime aware (имеет timezone)
                if timezone.is_naive(poll.time_end):
                    # Если naive, предполагаем UTC
                    local_time_end = timezone.make_aware(poll.time_end, timezone.utc).astimezone(org_timezone)
                else:
                    local_time_end = poll.time_end.astimezone(org_timezone)
                context["formatted_time_end"] = local_time_end.strftime("%d.%m.%Y, %H:%M:%S")
            except Exception:
                context["formatted_time_end"] = None
        else:
            context["formatted_time_end"] = None
        
        # Подсчет результатов голосования, если опрос завершен
        if poll and poll.time_end:
            context['questions_with_results'] = calculate_poll_results(poll)
        
        return context


@method_decorator(require_POST, name="dispatch")
class SelectOrganizationView(LoginRequiredMixin, TemplateView):
    """
    Accepts POST with organization_id to set current organization in session.
    Used by the header organization picker.
    """

    def post(self, request, *args, **kwargs):
        org_id = request.POST.get("organization_id")
        if not org_id:
            return HttpResponseBadRequest("organization_id is required")

        if not OrganizationUser.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            return HttpResponseBadRequest("Организация недоступна")

        request.session["current_org_id"] = int(org_id)
        return JsonResponse({"ok": True, "organization_id": int(org_id)})


@method_decorator(require_POST, name="dispatch")
class StartPollView(LoginRequiredMixin, TemplateView):
    """
    Устанавливает time_start для опроса.
    Доступ только к опросам текущего пользователя в выбранной организации.
    """

    def get_organization_user(self):
        """Получает OrganizationUser для текущего пользователя и выбранной организации."""
        org_user_qs = OrganizationUser.objects.select_related("organization").filter(
            user=self.request.user
        )
        current_org_id = self.request.session.get("current_org_id")

        org_user = None
        if current_org_id:
            org_user = org_user_qs.filter(organization_id=current_org_id).first()

        if not org_user:
            org_user = org_user_qs.first()

        if not org_user:
            logout(self.request)
            raise PermissionDenied("Организация для пользователя не найдена")

        return org_user

    def post(self, request, *args, **kwargs):
        poll_id = kwargs.get("pk")
        organization_user = self.get_organization_user()
        
        poll = get_object_or_404(
            Poll.objects.filter(creator=organization_user),
            pk=poll_id
        )
        
        if poll.time_start is not None:
            return JsonResponse({"error": "Голосование уже начато"}, status=400)
        
        poll.time_start = timezone.now()
        poll.save()
        
        # Отправка писем всем участникам опроса
        poll_users = poll.members.all()
        for poll_user in poll_users:
            vote_url = request.build_absolute_uri(
                reverse("core:vote", kwargs={
                    "poll_url": poll.url,
                    "user_url": poll_user.url
                })
            )
            try:
                send_to_user(
                    to=poll_user.email,
                    name=poll_user.name,
                    title=poll.title,
                    url=vote_url
                )
            except Exception as e:
                # Логируем ошибку, но не прерываем процесс
                # В production можно использовать logging
                if settings.DEBUG:
                    print(f"Ошибка отправки письма участнику {poll_user.email}: {e}")
        
        messages.success(request, "Голосование успешно начато")
        
        return JsonResponse({
            "ok": True,
            "time_start": poll.time_start.isoformat()
        })


@method_decorator(require_POST, name="dispatch")
class EndPollView(LoginRequiredMixin, TemplateView):
    """
    Устанавливает time_end для опроса.
    Доступ только к опросам текущего пользователя в выбранной организации.
    """

    def get_organization_user(self):
        """Получает OrganizationUser для текущего пользователя и выбранной организации."""
        org_user_qs = OrganizationUser.objects.select_related("organization").filter(
            user=self.request.user
        )
        current_org_id = self.request.session.get("current_org_id")

        org_user = None
        if current_org_id:
            org_user = org_user_qs.filter(organization_id=current_org_id).first()

        if not org_user:
            org_user = org_user_qs.first()

        if not org_user:
            logout(self.request)
            raise PermissionDenied("Организация для пользователя не найдена")

        return org_user

    def post(self, request, *args, **kwargs):
        poll_id = kwargs.get("pk")
        organization_user = self.get_organization_user()
        
        poll = get_object_or_404(
            Poll.objects.filter(creator=organization_user),
            pk=poll_id
        )
        
        if poll.time_end is not None:
            return JsonResponse({"error": "Голосование уже завершено"}, status=400)
        
        poll.time_end = timezone.now()
        poll.save()
        
        messages.success(request, "Голосование успешно завершено")
        
        return JsonResponse({
            "ok": True,
            "time_end": poll.time_end.isoformat()
        })


def logout_view(request):
    logout(request)
    return redirect("core:landing")


class VoteView(FormView):
    """
    View for voting on a poll.
    URL: /<poll_url>/<user_url>
    """
    template_name = "core/vote.html"
    form_class = VoteForm

    def get_poll_and_user(self):
        """Get poll and PollUser objects from URL parameters."""
        poll_url = self.kwargs.get("poll_url")
        user_url = self.kwargs.get("user_url")
        
        poll = get_object_or_404(Poll, url=poll_url)
        poll_user = get_object_or_404(
            PollUser,
            url=user_url,
            poll=poll
        )
        
        return poll, poll_user

    def get_form_kwargs(self):
        """Pass questions to the form."""
        kwargs = super().get_form_kwargs()
        poll, _ = self.get_poll_and_user()
        questions = poll.questions.all().prefetch_related('choices')
        kwargs['questions'] = questions
        return kwargs

    def get_context_data(self, **kwargs):
        """Add poll, poll_user, and status to context."""
        context = super().get_context_data(**kwargs)
        poll, poll_user = self.get_poll_and_user()
        
        context['poll'] = poll
        context['poll_user'] = poll_user
        context['status'] = poll.status
        
        if poll.status == "PENDING" and not poll_user.is_voted:
            context['questions'] = poll.questions.all().prefetch_related('choices')
        
        # Подсчет результатов голосования, если опрос завершен
        if poll.status == "FINISHED":
            context['questions_with_results'] = calculate_poll_results(poll)
        
        return context

    def dispatch(self, request, *args, **kwargs):
        """Check poll status and user voting status before processing."""
        poll, poll_user = self.get_poll_and_user()
        
        # Block POST requests if already voted
        if request.method == "POST" and poll_user.is_voted:
            messages.error(request, "Вы уже проголосовали.")
            return redirect("core:vote", poll_url=poll.url, user_url=poll_user.url)
        
        # Block POST requests if poll is not PENDING
        if request.method == "POST" and poll.status != "PENDING":
            messages.error(request, "Опрос не активен для голосования.")
            return redirect("core:vote", poll_url=poll.url, user_url=poll_user.url)
        
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """Save user choices."""
        poll, poll_user = self.get_poll_and_user()
        
        # Double-check status and voting status
        if poll.status != "PENDING":
            messages.error(self.request, "Опрос не активен для голосования.")
            return redirect("core:vote", poll_url=poll.url, user_url=poll_user.url)
        
        if poll_user.is_voted:
            messages.error(self.request, "Вы уже проголосовали.")
            return redirect("core:vote", poll_url=poll.url, user_url=poll_user.url)
        
        # Save choices
        with transaction.atomic():
            user_choices = []
            for question in poll.questions.all():
                field_name = f"question_{question.id}"
                selected_choices = form.cleaned_data.get(field_name)
                
                if question.type == "question":
                    # Single choice - selected_choices is a single ID
                    if selected_choices:
                        user_choices.append(
                            UserChoice(
                                user=poll_user,
                                choice_id=selected_choices
                            )
                        )
                else:
                    # Multiple choice - selected_choices is a list of IDs
                    if selected_choices:
                        for choice_id in selected_choices:
                            user_choices.append(
                                UserChoice(
                                    user=poll_user,
                                    choice_id=choice_id
                                )
                            )
            
            # Check if all required questions have answers
            # For single-choice questions, answer is always required
            # For multiple-choice questions, answer is required only if min > 0
            all_required_answered = True
            for question in poll.questions.all():
                field_name = f"question_{question.id}"
                selected_choices = form.cleaned_data.get(field_name)
                
                if question.type == "question":
                    # Single choice - always required
                    if not selected_choices:
                        all_required_answered = False
                        break
                else:
                    # Multiple choice - required only if min > 0
                    if question.min > 0 and (not selected_choices or len(selected_choices) == 0):
                        all_required_answered = False
                        break
            
            if not all_required_answered:
                messages.error(self.request, "Необходимо выбрать ответы на все обязательные вопросы.")
                return self.form_invalid(form)
            
            # Save choices (can be empty if min=0 for multiple choice)
            if user_choices:
                UserChoice.objects.bulk_create(user_choices)
            
            poll_user.is_voted = True
            poll_user.save()
            messages.success(self.request, "Ваш голос успешно учтён!")
        
        return redirect("core:vote", poll_url=poll.url, user_url=poll_user.url)

    def get(self, request, *args, **kwargs):
        """Handle GET requests - show appropriate message or form."""
        poll, poll_user = self.get_poll_and_user()
        
        # If already voted, show message
        if poll_user.is_voted:
            return self.render_to_response(self.get_context_data(already_voted=True))
        
        # Check status and show appropriate content
        if poll.status == "WAITING":
            return self.render_to_response(self.get_context_data())
        elif poll.status == "FINISHED":
            return self.render_to_response(self.get_context_data())
        elif poll.status == "PENDING":
            # Show form
            return super().get(request, *args, **kwargs)
        
        return super().get(request, *args, **kwargs)


class PasswordChangeView(LoginRequiredMixin, FormView):
    """
    View for changing user password.
    Follows Django best practices by using update_session_auth_hash
    to keep the user logged in after password change.
    """
    template_name = "core/password_change.html"
    form_class = CustomPasswordChangeForm
    login_url = reverse_lazy("core:login")
    success_url = reverse_lazy("core:my")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        # Update session to prevent logout after password change
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Пароль успешно изменен.")
        return super().form_valid(form)
