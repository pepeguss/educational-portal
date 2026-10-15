from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import LectureFile


@receiver(post_delete, sender=LectureFile)
def delete_lecture_file_content(sender, instance, using, **kwargs):
    # Cascades from lectures/sections also trigger this signal. Wait for commit so
    # a rolled-back deletion never leaves a restored record without its content.
    for field in (instance.file, instance.preview):
        if not field.name:
            continue

        def delete_if_unused(name=field.name, storage=field.storage):
            if not sender.objects.using(using).filter(Q(file=name) | Q(preview=name)).exists():
                storage.delete(name)

        transaction.on_commit(delete_if_unused, using=using, robust=True)
