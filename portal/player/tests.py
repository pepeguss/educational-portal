from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Lecture, Section


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
