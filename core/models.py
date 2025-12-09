from uuid import uuid4

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        abstract = True

class Organization(TimeStampedModel):
    name = models.CharField(max_length=255, verbose_name='Название организации')
    paid_until = models.DateField(verbose_name='Доступ до')
    timezone = models.CharField(
        max_length=50,
        verbose_name='Часовой пояс',
        default='Asia/Novosibirsk'
    )

    @property
    def is_active(self):
        return self.paid_until >= timezone.localdate()

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = 'Организация'
        verbose_name_plural = 'Организации'


class OrganizationUser(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profiles')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users')
    is_admin = models.BooleanField(default=False, verbose_name='Администратор')

    @property
    def name(self):
        return f'{self.user.last_name} {self.user.first_name}'

    @property
    def email(self):
        return self.user.email

    def __str__(self) -> str:
        return f'{self.name} ({self.organization})'


class Poll(TimeStampedModel):
    title = models.CharField(max_length=400)
    url = models.UUIDField(default=uuid4, unique=True, editable=False)
    creator = models.ForeignKey(OrganizationUser, on_delete=models.CASCADE, related_name='polls')

    time_start = models.DateTimeField(default=None, null=True)
    time_end = models.DateTimeField(default=None, null=True)

    @property
    def status(self):
        """Возвращает статус опроса: WAITING, PENDING или FINISHED"""
        if not self.time_start:
            return "WAITING"
        elif not self.time_end:
            return "PENDING"
        else:
            return "FINISHED"

    def __str__(self) -> str:
        return self.title


class PollUser(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='members')
    email = models.CharField(max_length=150, db_index=True)
    name = models.CharField(max_length=150)
    url = models.UUIDField(default=uuid4, unique=True, editable=False)
    is_voted = models.BooleanField(default=False)

    def __str__(self) -> str:
        return str(self.poll) + ' ' + self.email

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('poll', 'email'), name='uniq_poll_email'),
        ]
        ordering = ('poll_id', 'email')

class Question(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='questions')
    text = models.CharField(max_length=400)
    type = models.CharField(max_length=50, null=True)
    min = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    max = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    def __str__(self) -> str:
        return str(self.poll) + ' ' + self.text

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(max__gte=F('min')), name='max_gte_min'),
        ]


class Choice(models.Model):
    choice = models.CharField(max_length=400)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')

    def __str__(self) -> str:
        return str(self.question) + ' ' + self.choice
    
    @property
    def count(self):
        return UserChoice.objects.filter(choice=self).count()

class UserChoice(models.Model):
    choice = models.ForeignKey(Choice, on_delete=models.CASCADE, related_name='user_choices')
    user = models.ForeignKey(PollUser, on_delete=models.CASCADE, related_name='user_choices')

    def __str__(self) -> str:
        return str(self.user) + str(self.choice)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('choice', 'user'), name='uniq_choice_user'),
        ]

