from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from django.core.cache import cache


def parse_prices(payload, today):
    prices = {}
    for record in ElementTree.fromstring(payload).findall('Record'):
        if record.get('Code') != '1':
            continue
        date = datetime.strptime(record.get('Date'), '%d.%m.%Y').date()
        price = Decimal(record.findtext('Buy').replace(',', '.'))
        if date <= today and price.is_finite() and price > 0:
            prices[date.isoformat()] = float(price)
    if not prices:
        raise ValueError('No gold prices')
    return [{'date': date, 'price': prices[date]} for date in sorted(prices)]


def gold_prices():
    today = datetime.now(ZoneInfo('Europe/Moscow')).date()
    key = f'gold-prices:{today.isoformat()}'
    result = cache.get(key)
    if result:
        return result
    query = urlencode({
        'date_req1': (today - timedelta(days=370)).strftime('%d/%m/%Y'),
        'date_req2': today.strftime('%d/%m/%Y'),
    })
    try:
        with urlopen(f'https://www.cbr.ru/scripts/xml_metall.asp?{query}', timeout=10) as response:
            points = parse_prices(response.read(), today)
        result = {'points': points, 'stale': False}
        cache.set(key, result, 3600)
        cache.set('gold-prices:last', result, 7 * 86400)
        return result
    except (OSError, ValueError, TypeError, AttributeError, ArithmeticError, ElementTree.ParseError):
        previous = cache.get('gold-prices:last')
        if previous:
            result = {**previous, 'stale': True}
            cache.set(key, result, 60)
            return result
        raise ValueError('Gold prices unavailable') from None
