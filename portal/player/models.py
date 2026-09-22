from django.db import models

class Section(models.Model):
    title = models.CharField('Название раздела', max_length=200)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Раздел'
        verbose_name_plural = 'Разделы'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

class Lecture(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='lectures', verbose_name='Раздел')
    title = models.CharField('Название лекции', max_length=200)
    description = models.TextField('Описание', blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Лекция'
        verbose_name_plural = 'Лекции'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

class LectureFile(models.Model):
    TYPE_CHOICES = (
        ('pdf',  'PDF'),
        ('docx', 'DOCX'),
        ('mp4',  'MP4'),
        ('mp3',  'MP3'),
    )
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='files', verbose_name='Лекция')
    name = models.CharField('Имя файла', max_length=255)
    file = models.FileField('Файл', upload_to='lectures/%Y/%m/')
    type = models.CharField('Тип', max_length=5, choices=TYPE_CHOICES)

    class Meta:
        verbose_name = 'Файл лекции'
        verbose_name_plural = 'Файлы лекций'

    def __str__(self):
        return self.name