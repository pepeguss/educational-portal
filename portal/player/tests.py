from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import Department
from .models import Lecture, LectureFile, Section


class LectureTestLinkTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin', role='admin')
        self.client.force_login(self.admin)
        self.section = Section.objects.create(title='Раздел')
        self.create_url = reverse('player:api_lecture_create', args=[self.section.pk])

    def test_create_and_display_test_below_player(self):
        url = 'https://example.com/test?one=1&two=2'
        response = self.client.post(self.create_url, {
            'title': 'Лекция', 'has_test': '1', 'test_url': url,
        })
        self.assertEqual(response.status_code, 200)
        lecture = Lecture.objects.get(pk=response.json()['id'])
        self.assertEqual(lecture.test_url, url)
        page = self.client.get(reverse('player:lecture', args=[lecture.pk]))
        self.assertContains(page, 'href="https://example.com/test?one=1&amp;two=2"')
        self.assertContains(page, '<iframe src="https://example.com/test?one=1&amp;two=2"')
        html = page.content.decode()
        self.assertLess(html.index('id="viewer"'), html.index('Тест для оценки знаний'))

    def test_disabled_test_ignores_url_and_hides_link(self):
        response = self.client.post(self.create_url, {
            'title': 'Лекция', 'has_test': '0', 'test_url': 'https://example.com/test',
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
        self.assertEqual(embed['url'], url)
        self.assertNotIn('script', embed)

    def test_invalid_test_does_not_create_lecture(self):
        for url in ['', 'not a url', 'javascript:alert(1)', 'ftp://example.com/test',
                    'https://example.com/' + 'a' * 2000]:
            with self.subTest(url=url):
                response = self.client.post(self.create_url, {
                    'title': 'Лекция', 'has_test': '1', 'test_url': url,
                })
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Lecture.objects.exists())

    def test_edit_preserve_and_remove_test(self):
        lecture = Lecture.objects.create(section=self.section, title='Лекция')
        endpoint = reverse('player:api_lecture_update', args=[lecture.pk])
        url = 'https://example.com/test'
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
        self.assertContains(page, 'data-test-url="https://example.com/test"')
        self.client.post(endpoint, {'has_test': '0'})
        lecture.refresh_from_db()
        self.assertEqual(lecture.test_url, '')

    def test_regular_user_cannot_add_test(self):
        self.admin.role = 'user'
        self.admin.save()
        response = self.client.post(self.create_url, {
            'title': 'Лекция', 'has_test': '1', 'test_url': 'https://example.com/test',
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
                payload = dict(data, title='Не сохранять', has_test='1', test_url='https://example.com/test')
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
        self.assertContains(page, 'Пользователи и отделы')
        self.assertContains(page, 'Кто видит лекцию')
        self.assertContains(page, 'data-visibility="departments"')
        self.assertContains(page, f'data-departments="{self.department.pk}"')
        self.assertContains(page, f'value="{self.department.pk}" selected')
