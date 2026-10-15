import json
import io
import subprocess
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import Department
from .models import Lecture, LectureFile, Section
from .presentations import presentation_pdf


class MediaSeekingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='listener')
        self.client.force_login(self.user)
        self.lecture = Lecture.objects.create(section=Section.objects.create(title='Media'), title='Media')
        self.content = bytes(range(256)) * 1024
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.files = [LectureFile.objects.create(
            lecture=self.lecture, name=f'Материал.{kind}', type=kind,
            file=SimpleUploadedFile(f'material.{kind}', self.content),
        ) for kind in ('mp3', 'mp4')]

    def test_full_file_and_head_advertise_seeking(self):
        for obj in self.files:
            url = reverse('player:serve_file', args=[obj.pk])
            for method in ('get', 'head'):
                with self.subTest(kind=obj.type, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response['Accept-Ranges'], 'bytes')
                    self.assertEqual(int(response['Content-Length']), len(self.content))
                    self.assertEqual(response['Content-Type'], 'audio/mpeg' if obj.type == 'mp3' else 'video/mp4')
                    if method == 'get':
                        self.assertEqual(b''.join(response.streaming_content), self.content)
                    else:
                        self.assertEqual(response.content, b'')
                    response.close()

    def test_seek_forward_backward_open_ended_and_suffix_ranges(self):
        for obj in self.files:
            for url in (reverse('player:serve_file', args=[obj.pk]), obj.file.url):
                for value, start, end in [
                    ('bytes=180000-190000', 180000, 190000),
                    ('bytes=0-1', 0, 1),
                    ('bytes=1024-', 1024, len(self.content) - 1),
                    ('bytes=-128', len(self.content) - 128, len(self.content) - 1),
                    ('bytes=262140-999999999', 262140, len(self.content) - 1),
                    ('bytes=-999999999', 0, len(self.content) - 1),
                ]:
                    with self.subTest(kind=obj.type, url=url, value=value):
                        response = self.client.get(url, HTTP_RANGE=value)
                        self.assertEqual(response.status_code, 206)
                        self.assertEqual(response['Content-Range'], f'bytes {start}-{end}/{len(self.content)}')
                        self.assertEqual(int(response['Content-Length']), end - start + 1)
                        self.assertEqual(b''.join(response.streaming_content), self.content[start:end + 1])
                        response.close()

    def test_unsatisfiable_ranges(self):
        url = reverse('player:serve_file', args=[self.files[0].pk])
        for value in ['bytes=262144-', 'bytes=9-2', 'bytes=-0', 'bytes=' + '9' * 5000 + '-']:
            with self.subTest(value=value[:40]):
                response = self.client.get(url, HTTP_RANGE=value)
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response['Content-Range'], f'bytes */{len(self.content)}')
                self.assertEqual(response.content, b'')

    def test_unsupported_or_conditional_ranges_fall_back_to_full_response(self):
        url = reverse('player:serve_file', args=[self.files[0].pk])
        for headers in [
            {'HTTP_RANGE': 'invalid'}, {'HTTP_RANGE': 'bytes=-'},
            {'HTTP_RANGE': 'bytes=0-1,8-9'}, {'HTTP_RANGE': 'items=0-1'},
            {'HTTP_RANGE': 'bytes=0-1', 'HTTP_IF_RANGE': '"old-etag"'},
        ]:
            response = self.client.get(url, **headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), self.content)
            response.close()

    def test_ranges_do_not_bypass_lecture_access(self):
        self.lecture.is_public = False
        self.lecture.save()
        for obj in self.files:
            for url in (reverse('player:serve_file', args=[obj.pk]), obj.file.url):
                self.assertEqual(self.client.get(url, HTTP_RANGE='bytes=0-1').status_code, 404)
                self.assertEqual(self.client.head(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('player:serve_file', args=[self.files[0].pk]), HTTP_RANGE='bytes=0-1').status_code, 302)

    def test_empty_media_has_no_satisfiable_range(self):
        obj = LectureFile.objects.create(
            lecture=self.lecture, name='empty.mp3', type='mp3',
            file=SimpleUploadedFile('empty.mp3', b''),
        )
        response = self.client.get(reverse('player:serve_file', args=[obj.pk]), HTTP_RANGE='bytes=0-')
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response['Content-Range'], 'bytes */0')

    def test_partial_response_closes_file_even_before_iteration(self):
        obj = self.files[0]
        url = reverse('player:serve_file', args=[obj.pk])
        with patch('django.core.files.storage.FileSystemStorage._open', wraps=obj.file.storage._open) as opened:
            response = self.client.get(url, HTTP_RANGE='bytes=0-1')
            opened.assert_called_once()
            response.close()
        # Windows also refuses TemporaryDirectory cleanup if a handle is leaked.


class AccountDeletionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin', role='admin')
        self.member = get_user_model().objects.create_user(username='member')
        self.url = reverse('player:api_user_delete', args=[self.member.pk])

    def test_only_admin_can_delete_and_only_with_post(self):
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertTrue(get_user_model().objects.filter(pk=self.member.pk).exists())
        self.assertEqual(self.client.post(self.url).status_code, 200)
        self.assertFalse(get_user_model().objects.filter(pk=self.member.pk).exists())
        self.assertEqual(self.client.post(self.url).status_code, 404)

    def test_self_deletion_is_blocked_and_deleted_session_loses_access(self):
        from django.test import Client
        member_client = Client()
        member_client.force_login(self.member)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('player:api_user_delete', args=[self.admin.pk])).status_code, 400)
        self.client.post(self.url)
        self.assertEqual(member_client.get(reverse('player:index')).status_code, 302)


class PresentationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin', role='admin')
        self.member = get_user_model().objects.create_user(username='member')
        self.section = Section.objects.create(title='Раздел')
        self.lecture = Lecture.objects.create(section=self.section, title='Слайды')
        self.url = reverse('player:api_file_upload', args=[self.lecture.pk])
        self.client.force_login(self.admin)
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def upload(self):
        data = io.BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('ppt/presentation.xml', '<presentation/>')
        return SimpleUploadedFile('Презентация.PPTX', data.getvalue())

    @override_settings(LIBREOFFICE_BINARY='soffice-test')
    @patch('player.presentations.subprocess.run')
    def test_upload_conversion_private_preview_and_mobile_markup(self, run):
        def convert(command, **kwargs):
            source = Path(command[-1])
            self.assertTrue(source.read_bytes().startswith(b'PK'))
            source.with_suffix('.pdf').write_bytes(b'%PDF-1.4 slides')
            self.assertEqual(kwargs['timeout'], 120)
        run.side_effect = convert
        response = self.client.post(self.url, {'file': self.upload()})
        self.assertEqual(response.status_code, 200)
        obj = LectureFile.objects.get(pk=response.json()['id'])
        self.assertEqual(obj.type, 'pptx')
        self.assertTrue(obj.preview)
        self.assertTrue(obj.file.read().startswith(b'PK'))
        obj.file.close()
        page = self.client.get(reverse('player:lecture', args=[self.lecture.pk]))
        self.assertContains(page, 'data-file-type="pptx"')
        self.assertContains(page, 'name="viewport"')
        self.client.force_login(self.member)
        preview = self.client.get(response.json()['url'])
        self.assertEqual(preview['Content-Type'], 'application/pdf')
        self.assertEqual(b''.join(preview.streaming_content), b'%PDF-1.4 slides')
        preview.close()
        self.lecture.is_public = False
        self.lecture.save()
        self.assertEqual(self.client.get(response.json()['url']).status_code, 404)
        self.assertEqual(self.client.get(obj.preview.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'file': self.upload()}).status_code, 403)

    @override_settings(LIBREOFFICE_BINARY='soffice-test')
    @patch('player.presentations.subprocess.run')
    def test_bad_file_timeout_and_missing_output_leave_no_record(self, run):
        response = self.client.post(self.url, {'file': SimpleUploadedFile('bad.pptx', b'not a zip')})
        self.assertEqual(response.status_code, 400)
        run.assert_not_called()
        for error in [subprocess.TimeoutExpired('soffice', 120), OSError('missing binary'), None]:
            run.side_effect = error
            self.assertEqual(self.client.post(self.url, {'file': self.upload()}).status_code, 400)
        self.assertFalse(LectureFile.objects.exists())
        self.assertFalse(list(Path(self.media.name).rglob('*')))

    def test_missing_converter_and_upload_size(self):
        from django.core.exceptions import ValidationError
        with patch('player.presentations.shutil.which', return_value=None):
            self.assertEqual(self.client.post(self.url, {'file': self.upload()}).status_code, 400)
        upload = self.upload()
        upload.size = 101 * 1024 * 1024
        with self.assertRaises(ValidationError):
            presentation_pdf(upload)

    @override_settings(OFFLINE_MODE=True)
    def test_offline_page_uses_local_assets_and_does_not_embed_remote_test(self):
        self.lecture.test_url = 'https://forms.yandex.ru/u/example'
        self.lecture.save()
        page = self.client.get(reverse('player:lecture', args=[self.lecture.pk]))
        self.assertContains(page, '/static/vendor/tailwind.css')
        self.assertContains(page, '/static/vendor/jszip.min.js')
        self.assertContains(page, '/static/vendor/docx-preview.min.js')
        self.assertContains(page, 'требует доступа в интернет')
        self.assertNotContains(page, '<iframe')
        self.assertNotContains(page, 'src="https://')


class LectureTestLinkTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin', role='admin')
        self.client.force_login(self.admin)
        self.section = Section.objects.create(title='Раздел')
        self.create_url = reverse('player:api_lecture_create', args=[self.section.pk])

    def test_create_and_display_test_below_player(self):
        url = 'https://forms.yandex.ru/u/abc123?one=1&two=2'
        response = self.client.post(self.create_url, {
            'title': 'Лекция', 'has_test': '1', 'test_url': url,
        })
        self.assertEqual(response.status_code, 200)
        lecture = Lecture.objects.get(pk=response.json()['id'])
        self.assertEqual(lecture.test_url, url)
        self.assertFalse(lecture.has_practice)
        self.assertEqual(lecture.practice_task, '')
        page = self.client.get(reverse('player:lecture', args=[lecture.pk]))
        self.assertContains(page, 'href="https://forms.yandex.ru/u/abc123?one=1&amp;two=2"')
        self.assertContains(page, '<iframe src="https://forms.yandex.ru/u/abc123?one=1&amp;two=2&amp;iframe=1"')
        html = page.content.decode()
        self.assertLess(html.index('id="viewer"'), html.index('Тест для оценки знаний'))

    def test_disabled_test_ignores_url_and_hides_link(self):
        response = self.client.post(self.create_url, {
            'title': 'Лекция', 'has_test': '0', 'test_url': 'https://forms.yandex.ru/u/abc123',
        })
        lecture = Lecture.objects.get(pk=response.json()['id'])
        self.assertEqual(lecture.test_url, '')
        page = self.client.get(reverse('player:lecture', args=[lecture.pk]))
        self.assertNotContains(page, 'Тест для оценки знаний')
        self.assertNotContains(page, '<iframe')

    def test_yandex_form_embed(self):
        form_id = '6ab3773384227cdc0ddbd671'
        lecture = Lecture.objects.create(
            section=self.section, title='Лекция',
            test_url=f'https://forms.yandex.ru/u/{form_id}?theme=light&iframe=0',
        )
        page = self.client.get(reverse('player:lecture', args=[lecture.pk]))
        self.assertContains(page, f'src="https://forms.yandex.ru/u/{form_id}?theme=light&amp;iframe=1"')
        self.assertContains(page, f'name="ya-form-{form_id}"')
        self.assertContains(page, 'src="https://forms.yandex.ru/_static/embed.js"', count=1)

    def test_yandex_form_url_variants(self):
        for url in ['https://forms.yandex.ru/u/abc123/',
                    'https://forms.yandex.com/cloud/u/abc123/?iframe=1&iframe=0']:
            with self.subTest(url=url):
                embed = Lecture(test_url=url).test_embed
                self.assertEqual(embed['name'], 'ya-form-abc123')
                self.assertEqual(embed['url'].count('iframe='), 1)
                self.assertTrue(embed['url'].endswith('iframe=1'))

    def test_other_host_does_not_load_yandex_script(self):
        url = 'https://forms.yandex.ru.example.com/u/abc123/'
        embed = Lecture(test_url=url).test_embed
        self.assertIsNone(embed)

    def test_invalid_test_does_not_create_lecture(self):
        for url in ['', 'not a url', 'javascript:alert(1)', 'ftp://example.com/test',
                    'https://example.com/' + 'a' * 2000,
                    'https://example.com/test', 'http://forms.yandex.ru/u/abc123',
                    'https://forms.yandex.ru.evil.test/u/abc123',
                    'https://forms.yandex.ru@evil.test/u/abc123',
                    'https://forms.yandex.ru/other/abc123',
                    'https://forms.yandex.ru:8443/u/abc123']:
            with self.subTest(url=url):
                response = self.client.post(self.create_url, {
                    'title': 'Лекция', 'has_test': '1', 'test_url': url,
                })
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Lecture.objects.exists())

    def test_edit_preserve_and_remove_test(self):
        lecture = Lecture.objects.create(section=self.section, title='Лекция')
        endpoint = reverse('player:api_lecture_update', args=[lecture.pk])
        url = 'https://forms.yandex.ru/u/abc123'
        self.assertEqual(self.client.post(endpoint, {
            'has_test': '1', 'test_url': url,
        }).status_code, 200)
        self.client.post(endpoint, {'title': 'Новое название'})
        lecture.refresh_from_db()
        self.assertEqual(lecture.test_url, url)
        self.assertEqual(self.client.post(endpoint, {
            'title': 'Не сохранять', 'has_test': '1', 'test_url': 'invalid',
        }).status_code, 400)
        lecture.refresh_from_db()
        self.assertEqual(lecture.title, 'Новое название')
        self.assertEqual(lecture.test_url, url)
        page = self.client.get(reverse('player:admin_panel'))
        self.assertContains(page, 'data-test-url="https://forms.yandex.ru/u/abc123"')
        self.client.post(endpoint, {'has_test': '0'})
        lecture.refresh_from_db()
        self.assertEqual(lecture.test_url, '')

    def test_regular_user_cannot_add_test(self):
        self.admin.role = 'user'
        self.admin.save()
        response = self.client.post(self.create_url, {
            'title': 'Лекция', 'has_test': '1', 'test_url': 'https://forms.yandex.ru/u/abc123',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Lecture.objects.exists())


class DepartmentAccessTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Производство')
        self.other_department = Department.objects.create(name='Бухгалтерия')
        users = get_user_model().objects
        self.admin = users.create_user(username='admin', role='admin')
        self.member = users.create_user(username='member', department=self.department)
        self.outsider = users.create_user(username='outsider', department=self.other_department)
        self.unassigned = users.create_user(username='unassigned')
        self.section = Section.objects.create(title='Общий раздел')
        self.public = Lecture.objects.create(section=self.section, title='Общая лекция')
        self.restricted = Lecture.objects.create(
            section=self.section, title='Закрытая лекция', is_public=False,
        )
        self.restricted.departments.add(self.department)
        self.hidden_section = Section.objects.create(title='Закрытый раздел')
        self.hidden = Lecture.objects.create(
            section=self.hidden_section, title='Скрытая лекция', is_public=False,
        )
        self.hidden.departments.add(self.department)
        self.client.force_login(self.admin)

    def test_admin_creates_departments_and_rejects_invalid_names(self):
        endpoint = reverse('player:api_department_create')
        response = self.client.post(endpoint, {'title': '  Отдел кадров  '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Department.objects.get(pk=response.json()['id']).name, 'Отдел кадров')
        for name in ['', '   ', 'а' * 201, 'Производство', 'производство']:
            with self.subTest(name=name):
                self.assertEqual(self.client.post(endpoint, {'title': name}).status_code, 400)

    def test_assign_move_and_remove_department(self):
        endpoint = reverse('player:api_user_department_update', args=[self.unassigned.pk])
        for department in [self.department, self.other_department, None]:
            response = self.client.post(endpoint, {'department': department.pk if department else ''})
            self.assertEqual(response.status_code, 200)
            self.unassigned.refresh_from_db()
            self.assertEqual(self.unassigned.department, department)
        for data in [{}, {'department': 'invalid'}, {'department': '999999'}, {'department': '9' * 100}]:
            self.assertEqual(self.client.post(endpoint, data).status_code, 400)

    def test_bulk_departments_assign_move_remove_and_preserve_others(self):
        changes = [
            {'user_id': self.unassigned.pk, 'department_id': self.department.pk},
            {'user_id': self.member.pk, 'department_id': self.other_department.pk},
            {'user_id': self.outsider.pk, 'department_id': None},
        ]
        response = self.client.post(reverse('player:api_user_departments_update'), {
            'changes': json.dumps(changes),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['updated'], 3)
        for change in changes:
            self.assertEqual(get_user_model().objects.get(pk=change['user_id']).department_id,
                             change['department_id'])
        self.admin.refresh_from_db()
        self.assertIsNone(self.admin.department_id)

    def test_bulk_invalid_assignments_do_not_partially_save(self):
        valid = {'user_id': self.member.pk, 'department_id': self.other_department.pk}
        for invalid in [
            {'user_id': self.outsider.pk, 'department_id': 999999},
            {'user_id': 999999, 'department_id': None},
            {'user_id': self.outsider.pk},
            {'user_id': self.member.pk, 'department_id': None},
            {'user_id': True, 'department_id': None},
            {'user_id': self.outsider.pk, 'department_id': 'invalid'},
            {'user_id': 2**100, 'department_id': None},
        ]:
            with self.subTest(invalid=invalid):
                response = self.client.post(reverse('player:api_user_departments_update'), {
                    'changes': json.dumps([valid, invalid]),
                })
                self.assertEqual(response.status_code, 400)
                self.member.refresh_from_db()
                self.assertEqual(self.member.department_id, self.department.pk)

    def test_bulk_departments_require_admin_and_valid_payload(self):
        endpoint = reverse('player:api_user_departments_update')
        for payload in ['', 'invalid', '{}', 'null', '[]', '[null]']:
            self.assertEqual(self.client.post(endpoint, {'changes': payload}).status_code, 400)
        self.assertEqual(self.client.get(endpoint).status_code, 405)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(endpoint, {'changes': json.dumps([
            {'user_id': self.member.pk, 'department_id': None},
        ])}).status_code, 403)
        self.member.refresh_from_db()
        self.assertEqual(self.member.department_id, self.department.pk)
        self.client.logout()
        self.assertEqual(self.client.post(endpoint).status_code, 302)

    def test_admin_can_grant_and_revoke_portal_role(self):
        endpoint = reverse('player:api_user_departments_update')
        for role, expected_status in [('admin', 200), ('user', 302)]:
            self.client.force_login(self.admin)
            response = self.client.post(endpoint, {'changes': json.dumps([
                {'user_id': self.member.pk, 'department_id': self.other_department.pk, 'role': role},
            ])})
            self.assertEqual(response.status_code, 200)
            self.member.refresh_from_db()
            self.assertEqual(self.member.role, role)
            self.assertEqual(self.member.department_id, self.other_department.pk)
            self.assertFalse(self.member.is_superuser)
            self.assertFalse(self.member.is_staff)
            self.client.force_login(self.member)
            self.assertEqual(self.client.get(reverse('player:admin_panel')).status_code, expected_status)

    def test_role_validation_and_self_demotion_are_atomic(self):
        endpoint = reverse('player:api_user_departments_update')
        for target, role in [(self.member, 'superuser'), (self.admin, 'user'), (self.member, None)]:
            response = self.client.post(endpoint, {'changes': json.dumps([
                {'user_id': self.outsider.pk, 'department_id': None, 'role': 'admin'},
                {'user_id': target.pk, 'department_id': None, 'role': role},
            ])})
            self.assertEqual(response.status_code, 400)
            self.outsider.refresh_from_db()
            self.assertEqual(self.outsider.role, 'user')
            self.assertEqual(self.outsider.department_id, self.other_department.pk)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')

    def test_user_cannot_promote_self_and_department_edit_preserves_role(self):
        endpoint = reverse('player:api_user_departments_update')
        self.client.force_login(self.member)
        response = self.client.post(endpoint, {'changes': json.dumps([
            {'user_id': self.member.pk, 'department_id': None, 'role': 'admin'},
        ])})
        self.assertEqual(response.status_code, 403)
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, 'user')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(endpoint, {'changes': json.dumps([
            {'user_id': self.admin.pk, 'department_id': self.department.pk},
        ])}).status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')

    def test_department_changes_take_effect_on_next_request(self):
        endpoint = reverse('player:api_user_department_update', args=[self.member.pk])
        self.client.post(endpoint, {'department': self.other_department.pk})
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse('player:index')), 'Закрытая лекция')
        self.assertEqual(self.client.get(reverse('player:lecture', args=[self.restricted.pk])).status_code, 404)

    def test_create_lecture_for_multiple_departments_and_switch_to_public(self):
        response = self.client.post(reverse('player:api_lecture_create', args=[self.section.pk]), {
            'title': 'Для двух отделов', 'visibility': 'departments',
            'departments': [self.department.pk, self.other_department.pk],
        })
        self.assertEqual(response.status_code, 200)
        lecture = Lecture.objects.get(pk=response.json()['id'])
        self.assertFalse(lecture.is_public)
        self.assertEqual(lecture.departments.count(), 2)
        for user in [self.member, self.outsider]:
            self.assertTrue(Lecture.objects.visible_to(user).filter(pk=lecture.pk).exists())
        self.assertFalse(Lecture.objects.visible_to(self.unassigned).filter(pk=lecture.pk).exists())
        endpoint = reverse('player:api_lecture_update', args=[lecture.pk])
        self.assertEqual(self.client.post(endpoint, {'title': 'Новое название'}).status_code, 200)
        lecture.refresh_from_db()
        self.assertFalse(lecture.is_public)
        self.assertEqual(lecture.departments.count(), 2)
        self.assertEqual(self.client.post(endpoint, {'visibility': 'all'}).status_code, 200)
        lecture.refresh_from_db()
        self.assertTrue(lecture.is_public)
        self.assertFalse(lecture.departments.exists())
        self.assertEqual(self.client.post(endpoint, {
            'visibility': 'departments', 'departments': [self.department.pk],
        }).status_code, 200)
        lecture.refresh_from_db()
        self.assertFalse(lecture.is_public)
        self.assertEqual(list(lecture.departments.all()), [self.department])

    def test_invalid_access_never_saves_partial_changes(self):
        count = Lecture.objects.count()
        for data in [
            {'visibility': 'invalid'},
            {'visibility': 'departments'},
            {'visibility': 'departments', 'departments': ['invalid']},
            {'visibility': 'departments', 'departments': [self.department.pk, 999999]},
            {'visibility': 'departments', 'departments': ['9' * 100]},
        ]:
            with self.subTest(data=data):
                payload = dict(data, title='Не сохранять', has_test='1', test_url='https://forms.yandex.ru/u/abc123')
                self.assertEqual(self.client.post(
                    reverse('player:api_lecture_create', args=[self.section.pk]), payload,
                ).status_code, 400)
                self.assertEqual(self.client.post(
                    reverse('player:api_lecture_update', args=[self.restricted.pk]), payload,
                ).status_code, 400)
        self.assertEqual(Lecture.objects.count(), count)
        self.restricted.refresh_from_db()
        self.assertEqual(self.restricted.title, 'Закрытая лекция')
        self.assertEqual(self.restricted.test_url, '')
        self.assertFalse(self.restricted.is_public)
        self.assertEqual(list(self.restricted.departments.all()), [self.department])

    def test_home_and_direct_lecture_access_for_all_roles(self):
        for user, allowed in [(self.admin, True), (self.member, True),
                              (self.outsider, False), (self.unassigned, False)]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                page = self.client.get(reverse('player:index'))
                self.assertContains(page, 'Общая лекция', count=1)
                self.assertEqual(self.client.get(reverse('player:lecture', args=[self.public.pk])).status_code, 200)
                self.assertEqual(self.client.get(reverse('player:lecture', args=[self.restricted.pk])).status_code,
                                 200 if allowed else 404)
                if allowed:
                    self.assertContains(page, 'Закрытая лекция', count=1)
                    self.assertContains(page, 'Закрытый раздел', count=1)
                    self.assertContains(page, '2 лекц.')
                else:
                    self.assertNotContains(page, 'Закрытая лекция')
                    self.assertNotContains(page, 'Закрытый раздел')
                    self.assertContains(page, '1 лекц.')

    def test_empty_state_and_restricted_lecture_without_departments(self):
        self.public.delete()
        self.restricted.departments.clear()
        self.client.force_login(self.unassigned)
        self.assertContains(self.client.get(reverse('player:index')), 'Нет доступных лекций')
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('player:lecture', args=[self.restricted.pk])).status_code, 404)

    def test_files_and_legacy_media_urls_require_lecture_access(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            for lecture in [self.public, self.restricted]:
                lecture_file = LectureFile.objects.create(
                    lecture=lecture, name='material.pdf', type='pdf',
                    file=SimpleUploadedFile('material.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
                )
                for user in [self.admin, self.member, self.outsider, self.unassigned, None]:
                    with self.subTest(lecture=lecture.title, user=user):
                        self.client.logout()
                        if user:
                            self.client.force_login(user)
                        allowed = user and (lecture.is_public or user in [self.admin, self.member])
                        for url in [reverse('player:serve_file', args=[lecture_file.pk]), lecture_file.file.url]:
                            response = self.client.get(url)
                            self.assertEqual(response.status_code, 200 if allowed else 404 if user else 302)
                            if allowed:
                                self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.4 test')
                            response.close()

    def test_regular_users_cannot_manage_departments_or_access(self):
        endpoints = [
            (reverse('player:api_department_create'), {'title': 'Запрещено'}),
            (reverse('player:api_user_department_update', args=[self.member.pk]), {'department': ''}),
            (reverse('player:api_lecture_create', args=[self.section.pk]), {'visibility': 'all'}),
            (reverse('player:api_lecture_update', args=[self.restricted.pk]), {'visibility': 'all'}),
        ]
        self.client.force_login(self.member)
        for endpoint, data in endpoints:
            self.assertEqual(self.client.post(endpoint, data).status_code, 403)
        self.member.refresh_from_db()
        self.assertEqual(self.member.department, self.department)
        self.client.logout()
        for endpoint, data in endpoints:
            self.assertEqual(self.client.post(endpoint, data).status_code, 302)
        self.assertEqual(self.client.get(reverse('player:lecture', args=[self.public.pk])).status_code, 302)

    def test_admin_forms_render_current_access_and_departments(self):
        page = self.client.get(reverse('player:admin_panel'))
        self.assertContains(page, 'Пользователи, отделы и роли')
        self.assertContains(page, 'Кто видит лекцию')
        self.assertContains(page, 'data-visibility="departments"')
        self.assertContains(page, f'data-departments="{self.department.pk}"')
        self.assertContains(page, f'value="{self.department.pk}" selected')
