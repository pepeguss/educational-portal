import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def validate_yandex_form_url(value):
    """Accept only published Yandex Forms over HTTPS."""
    message = 'Укажите ссылку на Яндекс Форму: https://forms.yandex.ru/u/идентификатор'
    try:
        URLValidator(schemes=['https'])(value)
        parts = urlsplit(value)
        if (
            len(value) > 2000
            or parts.netloc not in ('forms.yandex.ru', 'forms.yandex.com')
            or not re.fullmatch(r'/(?:cloud/)?u/[a-zA-Z0-9_-]+/?', parts.path)
        ):
            raise ValidationError(message)
    except (ValidationError, ValueError):
        raise ValidationError(message, code='invalid_yandex_form')
