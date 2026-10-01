from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from users.models import Department
from .models import Lecture, PracticeFile, PracticeSubmission, Section


class PracticeTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        users = get_user_model()
        self.admin = users.objects.create_user(username='admin', role='admin')
        self.department = Department.objects.create(name='Геологи')
        self.member = users.objects.create_user(username='member', full_name='Иван Иванов', department=self.department)
        self.peer = users.objects.create_user(username='peer', department=self.department)
        self.outsider = users.objects.create_user(username='outsider')
        self.section = Section.objects.create(title='Раздел')
        self.lecture = Lecture.objects.create(
            section=self.section, title='Практическая лекция', has_practice=True,
            practice_task='Подготовьте отчёт.\nПрикрепите файл.', is_public=False,
        )
        self.lecture.departments.add(self.department)
        self.page = reverse('player:lecture', args=[self.lecture.pk])
        self.upload_url = reverse('player:api_practice_upload', args=[self.lecture.pk])
        self.submit_url = reverse('player:api_practice_submit', args=[self.lecture.pk])
        self.withdraw_url = reverse('player:api_practice_withdraw', args=[self.lecture.pk])
        self.client.force_login(self.member)

    def upload(self, names=('отчёт.txt',)):
        return self.client.post(self.upload_url, {
            'files': [SimpleUploadedFile(name, b'report') for name in names],
        })

    def test_admin_can_create_edit_and_disable_practice_without_losing_work(self):
        self.upload()
        self.client.force_login(self.admin)
        created = self.client.post(reverse('player:api_lecture_create', args=[self.section.pk]), {
            'title': 'Новая лекция', 'has_practice': '1', 'practice_task': '  Задание  ',
        })
        self.assertEqual(created.status_code, 200)
        lecture = Lecture.objects.get(pk=created.json()['id'])
        self.assertTrue(lecture.has_practice)
        self.assertEqual(lecture.practice_task, 'Задание')
        endpoint = reverse('player:api_lecture_update', args=[self.lecture.pk])
        self.assertEqual(self.client.post(endpoint, {'title': 'Изменена'}).status_code, 200)
        self.lecture.refresh_from_db()
        self.assertTrue(self.lecture.has_practice)
        self.assertEqual(self.client.post(endpoint, {'has_practice': '0'}).status_code, 200)
        self.assertEqual(PracticeFile.objects.count(), 1)
        self.assertNotContains(self.client.get(self.page), 'lecture-practice-layout')
        self.assertEqual(self.client.post(endpoint, {'has_practice': '1', 'practice_task': 'Новое задание'}).status_code, 200)
        page = self.client.get(reverse('player:admin_panel'))
        self.assertContains(page, 'data-has-practice="1"')
        self.assertContains(page, 'data-practice-task="Новое задание"')
        self.assertContains(page, 'Практическая часть')

    def test_invalid_practice_never_saves_partial_lecture_changes(self):
        self.client.force_login(self.admin)
        for payload in [
            {'has_practice': '1', 'practice_task': '  '},
            {'has_practice': '1', 'practice_task': 'x' * 20001},
            {'has_practice': 'invalid'},
        ]:
            with self.subTest(payload=payload):
                data = dict(payload, title='Не сохранять', has_test='1', test_url='https://example.com/test')
                self.assertEqual(self.client.post(reverse('player:api_lecture_create', args=[self.section.pk]), data).status_code, 400)
                self.assertEqual(self.client.post(reverse('player:api_lecture_update', args=[self.lecture.pk]), data).status_code, 400)
        self.assertEqual(Lecture.objects.count(), 1)
        self.lecture.refresh_from_db()
        self.assertEqual(self.lecture.title, 'Практическая лекция')
        self.assertEqual(self.lecture.test_url, '')

    def test_upload_submit_lock_withdraw_replace_and_resubmit(self):
        self.assertEqual(self.client.post(self.submit_url).status_code, 400)
        self.assertEqual(self.upload(('отчёт.txt', 'схема.png')).status_code, 200)
        submission = PracticeSubmission.objects.get(user=self.member, lecture=self.lecture)
        self.assertIsNone(submission.submitted_at)
        self.assertEqual(submission.files.count(), 2)
        self.assertContains(self.client.get(self.page), 'отчёт.txt')
        self.assertEqual(self.client.post(self.submit_url).status_code, 200)
        submission.refresh_from_db()
        submitted_at = submission.submitted_at
        self.assertIsNotNone(submitted_at)
        self.assertEqual(self.client.post(self.submit_url).status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.submitted_at, submitted_at)
        file = submission.files.first()
        delete_url = reverse('player:api_practice_file_delete', args=[file.pk])
        self.assertEqual(self.upload().status_code, 409)
        self.assertEqual(self.client.post(delete_url).status_code, 409)
        self.assertContains(self.client.get(self.page), 'Вернуть в черновик')
        self.assertEqual(self.client.post(self.withdraw_url).status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(delete_url).status_code, 200)
        self.assertFalse(Path(file.file.path).exists())
        self.assertEqual(self.upload(('новый.txt',)).status_code, 200)
        self.assertEqual(self.client.post(self.submit_url).status_code, 200)
        self.assertEqual(PracticeSubmission.objects.count(), 1)

    def test_private_files_and_legacy_media_urls_obey_ownership_and_submission_state(self):
        self.upload(('работа.html',))
        file = PracticeFile.objects.get()
        urls = [reverse('player:serve_practice_file', args=[file.pk]), file.file.url]
        for user in [self.peer, self.outsider, self.admin, None]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 404 if user else 302)
        self.client.force_login(self.member)
        self.client.post(self.submit_url)
        for user in [self.member, self.admin]:
            self.client.force_login(user)
            for url in urls:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
                self.assertEqual(response['Content-Type'], 'application/octet-stream')
                self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(b''.join(response.streaming_content), b'report')
                response.close()
        self.client.force_login(self.peer)
        self.assertNotContains(self.client.get(self.page), 'работа.html')
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.member)
        self.client.post(self.withdraw_url)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(urls[0]).status_code, 404)

    def test_admin_sees_only_submitted_work_and_user_sees_only_own_files(self):
        self.upload(('личный-отчёт.txt',))
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(self.page), 'личный-отчёт.txt')
        self.client.force_login(self.member)
        self.client.post(self.submit_url)
        self.client.force_login(self.admin)
        page = self.client.get(self.page)
        self.assertContains(page, 'Сданные работы')
        self.assertContains(page, 'Иван Иванов')
        self.assertContains(page, 'личный-отчёт.txt')
        self.assertNotContains(page, 'id="practice-upload"')
        self.client.force_login(self.peer)
        self.upload(('другой-отчёт.txt',))
        self.assertNotContains(self.client.get(self.page), 'личный-отчёт.txt')

    def test_mutations_require_lecture_access_owner_post_and_csrf(self):
        self.upload()
        file = PracticeFile.objects.get()
        delete_url = reverse('player:api_practice_file_delete', args=[file.pk])
        self.client.force_login(self.peer)
        self.assertEqual(self.client.post(delete_url).status_code, 404)
        self.client.force_login(self.outsider)
        self.assertEqual(self.upload().status_code, 404)
        for url in [self.submit_url, self.withdraw_url, delete_url]:
            self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.member)
        for url in [self.upload_url, self.submit_url, self.withdraw_url, delete_url]:
            self.assertEqual(self.client.get(url).status_code, 405)
        secure_client = Client(enforce_csrf_checks=True)
        secure_client.force_login(self.member)
        self.assertEqual(secure_client.post(self.submit_url).status_code, 403)
        secure_client.get(self.page)
        token = secure_client.cookies['csrftoken'].value
        self.assertEqual(secure_client.post(self.submit_url, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.client.logout()
        self.assertEqual(self.upload().status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.upload().status_code, 403)

    def test_file_count_size_and_empty_upload_validation_is_atomic(self):
        self.assertEqual(self.client.post(self.upload_url).status_code, 400)
        for content in [b'', b'x' * 5]:
            with patch('player.views.PRACTICE_MAX_FILE_SIZE', 4):
                response = self.client.post(self.upload_url, {'files': [
                    SimpleUploadedFile('valid.txt', b'ok'), SimpleUploadedFile('invalid.txt', content),
                ]})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(PracticeSubmission.objects.exists())
        self.assertFalse(list(Path(self.media.name).rglob('*')))
        self.assertEqual(self.upload(tuple(f'{i}.txt' for i in range(11))).status_code, 400)
        self.assertEqual(self.upload(tuple(f'{i}.txt' for i in range(10))).status_code, 200)
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(PracticeFile.objects.count(), 10)

    def test_storage_is_cleaned_after_failed_upload_or_cascade_deletion(self):
        with patch.object(PracticeFile, 'save', side_effect=RuntimeError('storage test')):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertFalse(PracticeSubmission.objects.exists())
        self.assertFalse([path for path in Path(self.media.name).rglob('*') if path.is_file()])
        self.upload()
        file = PracticeFile.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            self.lecture.delete()
        self.assertFalse(Path(file.file.path).exists())
        self.assertFalse(PracticeSubmission.objects.exists())

    def test_disabled_practice_hides_panel_and_denies_upload_and_file_access(self):
        self.upload()
        file = PracticeFile.objects.get()
        self.lecture.has_practice = False
        self.lecture.save()
        page = self.client.get(self.page)
        self.assertContains(page, 'max-w-5xl mx-auto')
        self.assertNotContains(page, 'lecture-practice-layout')
        self.assertNotContains(page, 'Ваша работа')
        self.assertEqual(self.upload().status_code, 404)
        self.assertEqual(self.client.get(file.file.url).status_code, 404)
        self.assertEqual(PracticeFile.objects.count(), 1)
