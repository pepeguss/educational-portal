from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    name = models.CharField('Название отдела', max_length=200, unique=True)

    class Meta:
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'
        ordering = ['name', 'id']

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = (
        ('user', 'Пользователь'),
        ('admin', 'Администратор'),
    )
    full_name = models.CharField('ФИО', max_length=200)
    role = models.CharField('Роль', max_length=10, choices=ROLE_CHOICES, default='user')
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='users', verbose_name='Отдел',
    )

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"
