from django.db import migrations, models


def restore_missing_columns(apps, schema_editor):
    """Keep data from the removed practice migration; also support fresh databases."""
    lecture = apps.get_model('player', 'Lecture')
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name for column in schema_editor.connection.introspection.get_table_description(
                cursor, lecture._meta.db_table,
            )
        }
    for name in ('has_practice', 'practice_task'):
        field = lecture._meta.get_field(name)
        if field.column not in columns:
            schema_editor.add_field(lecture, field)


class Migration(migrations.Migration):
    dependencies = [('player', '0004_alter_lecture_test_url')]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='lecture', name='has_practice',
                    field=models.BooleanField(default=False, verbose_name='Есть практическое задание'),
                ),
                migrations.AddField(
                    model_name='lecture', name='practice_task',
                    field=models.TextField(blank=True, default='', verbose_name='Практическое задание'),
                ),
            ],
        ),
        migrations.RunPython(restore_missing_columns),
    ]
