from django.apps import AppConfig


class PlayerConfig(AppConfig):
    name = 'player'

    def ready(self):
        from . import signals  # noqa: F401
