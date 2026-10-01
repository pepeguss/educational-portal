from django.db import models, transaction
from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver
from uuid import uuid4
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import re

class Section(models.Model):
    title = models.CharField('Название раздела', max_length=200)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Раздел'
        verbose_name_plural = 'Разделы'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

class LectureQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not user.is_authenticated:
            return self.none()
        if user.role == 'admin':
            return self
        access = models.Q(is_public=True)
        if user.department_id:
            access |= models.Q(departments=user.department_id)
        return self.filter(access).distinct()


class Lecture(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='lectures', verbose_name='Раздел')
    title = models.CharField('Название лекции', max_length=200)
    description = models.TextField('Описание', blank=True)
    test_url = models.URLField('Ссылка на тест для оценки знаний', max_length=2000, blank=True)
    has_practice = models.BooleanField('Практическая часть', default=False)
    practice_task = models.TextField('Задание для практики', blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    is_public = models.BooleanField('Доступна всем пользователям', default=True)
    departments = models.ManyToManyField(
        'users.Department', blank=True, related_name='lectures', verbose_name='Доступна отделам',
    )

    objects = LectureQuerySet.as_manager()

    class Meta:
        verbose_name = 'Лекция'
        verbose_name_plural = 'Лекции'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

    @property
    def test_embed(self):
        if not self.test_url:
            return None
        parts = urlsplit(self.test_url)
        form = re.fullmatch(r'/(?:cloud/)?u/([a-zA-Z0-9_-]+)/?', parts.path)
        if parts.hostname in ('forms.yandex.ru', 'forms.yandex.com') and form:
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                     if key != 'iframe']
            query.append(('iframe', '1'))
            return {
                'url': urlunsplit(('https', parts.hostname, parts.path, urlencode(query), parts.fragment)),
                'name': f'ya-form-{form.group(1)}',
                'script': f'https://{parts.hostname}/_static/embed.js',
            }
        return {'url': self.test_url, 'name': f'lecture-test-{self.pk}'}

class LectureFile(models.Model):
    TYPE_CHOICES = (
        ('pdf',  'PDF'),
        ('docx', 'DOCX'),
        ('mp4',  'MP4'),
        ('mp3',  'MP3'),
    )
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='files', verbose_name='Лекция')
    name = models.CharField('Имя файла', max_length=255)
    file = models.FileField('Файл', upload_to='lectures/%Y/%m/')
    type = models.CharField('Тип', max_length=5, choices=TYPE_CHOICES)

    class Meta:
        verbose_name = 'Файл лекции'
        verbose_name_plural = 'Файлы лекций'

    def __str__(self):
        return self.name


class PracticeSubmission(models.Model):
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='submissions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='practice_submissions')
    submitted_at = models.DateTimeField('Сдано', null=True, blank=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lecture', 'user'], name='unique_lecture_submission')]
        ordering = ['-submitted_at', '-id']


def practice_upload_path(instance, filename):
    return f'practice/{instance.submission.lecture_id}/{instance.submission.user_id}/{uuid4().hex}'


class PracticeFile(models.Model):
    submission = models.ForeignKey(PracticeSubmission, on_delete=models.CASCADE, related_name='files')
    name = models.CharField('Имя файла', max_length=255)
    file = models.FileField('Файл работы', upload_to=practice_upload_path)
    size = models.PositiveBigIntegerField('Размер файла')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']


@receiver(post_delete, sender=PracticeFile)
def delete_practice_file_from_storage(sender, instance, **kwargs):
    if instance.file:
        storage, name = instance.file.storage, instance.file.name
        transaction.on_commit(lambda: storage.delete(name))
