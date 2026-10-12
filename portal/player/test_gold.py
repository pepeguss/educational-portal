from datetime import date
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .gold import parse_prices, gold_prices


XML = b'''<Metall>
<Record Date="02.10.2026" Code="1"><Buy>11200,50</Buy></Record>
<Record Date="01.10.2026" Code="2"><Buy>150</Buy></Record>
<Record Date="01.10.2026" Code="1"><Buy>11000,00</Buy></Record>
<Record Date="03.10.2026" Code="1"><Buy>12000</Buy></Record>
</Metall>'''


class GoldPricesTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_gold_only_sorted_with_no_future_prices(self):
        self.assertEqual(parse_prices(XML, date(2026, 10, 2)), [
            {'date': '2026-10-01', 'price': 11000.0},
            {'date': '2026-10-02', 'price': 11200.5},
        ])

    @patch('player.gold.urlopen')
    def test_success_is_cached(self, fetch):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = XML
        fetch.return_value = response
        result = gold_prices()
        self.assertFalse(result['stale'])
        self.assertEqual(gold_prices(), result)
        fetch.assert_called_once()

    @patch('player.gold.urlopen', side_effect=OSError)
    def test_outage_returns_previous_data_marked_stale(self, fetch):
        cache.set('gold-prices:last', {'points': [{'date': '2026-10-01', 'price': 11000}], 'stale': False})
        self.assertTrue(gold_prices()['stale'])

    @patch('player.gold.urlopen', side_effect=OSError)
    def test_outage_without_cache_is_reported(self, fetch):
        with self.assertRaises(ValueError):
            gold_prices()


class GoldEndpointTests(TestCase):
    def test_login_required_and_source_errors_handled(self):
        url = reverse('player:api_gold_prices')
        self.assertEqual(self.client.get(url).status_code, 302)
        user = get_user_model().objects.create_user(username='gold-reader')
        self.client.force_login(user)
        with patch('player.views.gold_prices', side_effect=ValueError):
            self.assertEqual(self.client.get(url).status_code, 503)
        with patch('player.views.gold_prices', return_value={'points': [], 'stale': False}):
            self.assertEqual(self.client.get(url).status_code, 200)
        page = self.client.get(reverse('player:index'))
        self.assertContains(page, 'Стоимость золота')
        self.assertNotContains(page, 'Добро пожаловать')
