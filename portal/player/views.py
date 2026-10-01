from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Count
from django.urls import reverse
from django.utils import timezone
from users.models import Department, User
from .models import Section, Lecture, LectureFile, PracticeSubmission, PracticeFile

PRACTICE_MAX_FILE_SIZE = 20 * 1024 * 1024
PRACTICE_MAX_FILES = 10

@login_required
@xframe_options_exempt  
def serve_file(request, file_id):
    obj = get_object_or_404(
        LectureFile.objects.filter(lecture__in=Lecture.objects.visible_to(request.user)),
        id=file_id,
    )
    
    
    response = FileResponse(obj.file.open('rb'), content_type='application/pdf' if obj.type == 'pdf' else None)
    response['Content-Disposition'] = f'inline; filename="{obj.name}"'
    return response


@login_required
def serve_media(request, path):
    if path.startswith('practice/'):
        obj = get_object_or_404(PracticeFile, file=path)
        return serve_practice_file(request, obj.pk)
    obj = get_object_or_404(
        LectureFile.objects.filter(lecture__in=Lecture.objects.visible_to(request.user)),
        file=path,
    )
    return serve_file(request, obj.pk)


@login_required
def index_view(request):
    lectures = Lecture.objects.visible_to(request.user)
    sections = Section.objects.filter(lectures__in=lectures).distinct().prefetch_related(
        Prefetch('lectures', queryset=lectures),
    )
    return render(request, 'player/index.html', {'sections': sections})

@login_required
def about_view(request):
    return render(request, 'player/about.html')


@login_required
def contacts_view(request):
    return render(request, 'player/contacts.html')


@login_required
def lecture_view(request, lecture_id):
    lecture = get_object_or_404(
        Lecture.objects.visible_to(request.user).prefetch_related('files'), id=lecture_id,
    )
    context = {'lecture': lecture}
    if lecture.has_practice:
        if request.user.role == 'admin':
            context['submissions'] = lecture.submissions.filter(submitted_at__isnull=False).select_related('user').prefetch_related('files')
        else:
            context['submission'] = lecture.submissions.filter(user=request.user).prefetch_related('files').first()
    return render(request, 'player/lecture.html', context)

@login_required
def admin_view(request):
    if request.user.role != 'admin':
        return redirect('player:index')
    sections = Section.objects.prefetch_related('lectures__files', 'lectures__departments').all()
    return render(request, 'player/admin.html', {
        'sections': sections,
        'departments': Department.objects.annotate(user_count=Count('users')),
        'portal_users': User.objects.select_related('department').order_by('full_name', 'username'),
    })

# --- API для админки (AJAX) ---
@login_required
@require_POST
def api_department_create(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    name = request.POST.get('title', '').strip()
    if not name or len(name) > 200:
        return JsonResponse({'error': 'Введите название отдела длиной от 1 до 200 символов.'}, status=400)
    try:
        with transaction.atomic():
            if any(existing.casefold() == name.casefold()
                   for existing in Department.objects.values_list('name', flat=True)):
                return JsonResponse({'error': 'Отдел с таким названием уже существует.'}, status=400)
            department = Department.objects.create(name=name)
    except IntegrityError:
        return JsonResponse({'error': 'Отдел с таким названием уже существует.'}, status=400)
    return JsonResponse({'id': department.pk, 'name': department.name})


@login_required
@require_POST
def api_user_department_update(request, user_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    user = get_object_or_404(User, pk=user_id)
    if 'department' not in request.POST:
        return JsonResponse({'error': 'Выберите отдел или «Без отдела».'}, status=400)
    department_id = request.POST['department']
    department = None
    if department_id:
        try:
            department = Department.objects.get(pk=int(department_id))
        except (ValueError, OverflowError, Department.DoesNotExist):
            return JsonResponse({'error': 'Выбранный отдел не существует.'}, status=400)
    user.department = department
    user.save(update_fields=['department'])
    return JsonResponse({'ok': True})


def lecture_access(request, lecture=None):
    visibility = request.POST.get('visibility')
    if visibility is None:
        if lecture is None:
            return True, []
        return lecture.is_public, list(lecture.departments.all())
    if visibility == 'all':
        return True, []
    if visibility != 'departments':
        raise ValidationError('Выберите, кому доступна лекция.')
    try:
        ids = {int(value) for value in request.POST.getlist('departments')}
        departments = list(Department.objects.filter(pk__in=ids))
    except (ValueError, OverflowError):
        raise ValidationError('Выберите существующие отделы.')
    if not ids or len(departments) != len(ids):
        raise ValidationError('Выберите хотя бы один существующий отдел.')
    return False, departments


def lecture_test_url(request, default=''):
    if 'has_test' not in request.POST:
        return default
    if request.POST.get('has_test') != '1':
        return ''
    url = request.POST.get('test_url', '').strip()
    if not url:
        raise ValidationError('Укажите ссылку на тест.')
    if len(url) > 2000:
        raise ValidationError('Ссылка на тест должна быть не длиннее 2000 символов.')
    try:
        URLValidator(schemes=['http', 'https'])(url)
    except ValidationError:
        raise ValidationError('Введите корректную ссылку на тест, начиная с http:// или https://.')
    return url


def lecture_practice(request, lecture=None):
    enabled = lecture.has_practice if lecture else False
    task = lecture.practice_task if lecture else ''
    if 'has_practice' not in request.POST:
        return enabled, task
    if request.POST['has_practice'] not in ('0', '1'):
        raise ValidationError('Укажите, нужна ли практическая часть.')
    enabled = request.POST['has_practice'] == '1'
    task = request.POST.get('practice_task', task).strip()
    if enabled and not task:
        raise ValidationError('Напишите задание для практической части.')
    if len(task) > 20000:
        raise ValidationError('Задание должно быть не длиннее 20 000 символов.')
    return enabled, task


@login_required
@require_POST
def api_section_create(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    title = request.POST.get('title', '').strip()
    if not title:
        return JsonResponse({'error': 'Пустой заголовок'}, status=400)
    sec = Section.objects.create(title=title)
    return JsonResponse({'id': sec.id, 'title': sec.title})

@login_required
@require_POST
def api_section_update(request, section_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    sec = get_object_or_404(Section, id=section_id)
    sec.title = request.POST.get('title', sec.title).strip()
    sec.save()
    return JsonResponse({'ok': True})

@login_required
@require_POST
def api_section_delete(request, section_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    Section.objects.filter(id=section_id).delete()
    return JsonResponse({'ok': True})

@login_required
@require_POST
def api_lecture_create(request, section_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    sec = get_object_or_404(Section, id=section_id)
    title = request.POST.get('title', '').strip()
    desc = request.POST.get('description', '').strip()
    try:
        test_url = lecture_test_url(request)
        is_public, departments = lecture_access(request)
        has_practice, practice_task = lecture_practice(request)
    except ValidationError as error:
        return JsonResponse({'error': error.messages[0]}, status=400)
    with transaction.atomic():
        lec = Lecture.objects.create(
            section=sec, title=title, description=desc, test_url=test_url, is_public=is_public,
            has_practice=has_practice, practice_task=practice_task,
        )
        lec.departments.set(departments)
    return JsonResponse({'id': lec.id, 'title': lec.title})

@login_required
@require_POST
def api_lecture_update(request, lecture_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    lec = get_object_or_404(Lecture, id=lecture_id)
    try:
        lec.test_url = lecture_test_url(request, lec.test_url)
        lec.is_public, departments = lecture_access(request, lec)
        lec.has_practice, lec.practice_task = lecture_practice(request, lec)
    except ValidationError as error:
        return JsonResponse({'error': error.messages[0]}, status=400)
    lec.title = request.POST.get('title', lec.title).strip()
    lec.description = request.POST.get('description', lec.description).strip()
    with transaction.atomic():
        lec.save()
        lec.departments.set(departments)
    return JsonResponse({'ok': True})

@login_required
@require_POST
def api_lecture_delete(request, lecture_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    Lecture.objects.filter(id=lecture_id).delete()
    return JsonResponse({'ok': True})

@login_required
@require_POST
def api_file_upload(request, lecture_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    lec = get_object_or_404(Lecture, id=lecture_id)
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'error': 'Нет файла'}, status=400)
    ext = f.name.rsplit('.', 1)[-1].lower()
    if ext not in ('pdf', 'docx', 'mp4', 'mp3'):
        return JsonResponse({'error': 'Недопустимый формат'}, status=400)
    obj = LectureFile.objects.create(lecture=lec, name=f.name, file=f, type=ext)
    return JsonResponse({'id': obj.id, 'name': obj.name, 'type': obj.type,
                         'url': reverse('player:serve_file', args=[obj.pk])})

@login_required
@require_POST
def api_file_delete(request, file_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    LectureFile.objects.filter(id=file_id).delete()
    return JsonResponse({'ok': True})


def practice_lecture(request, lecture_id, lock=False):
    lectures = Lecture.objects.filter(pk__in=Lecture.objects.visible_to(request.user), has_practice=True)
    if lock:
        lectures = lectures.select_for_update()
    return get_object_or_404(lectures, pk=lecture_id)


@login_required
@require_POST
def api_practice_upload(request, lecture_id):
    if request.user.role == 'admin':
        return JsonResponse({'error': 'Администратор просматривает сданные работы.'}, status=403)
    files = request.FILES.getlist('files')
    if not files:
        return JsonResponse({'error': 'Выберите файлы для загрузки.'}, status=400)
    if len(files) > PRACTICE_MAX_FILES:
        return JsonResponse({'error': 'К работе можно прикрепить не более 10 файлов.'}, status=400)
    for file in files:
        if not file.size or file.size > PRACTICE_MAX_FILE_SIZE:
            return JsonResponse({'error': 'Файл должен быть непустым и не больше 20 МБ.'}, status=400)
        if len(file.name) > 255:
            return JsonResponse({'error': 'Имя файла должно быть не длиннее 255 символов.'}, status=400)
    stored = []
    try:
        with transaction.atomic():
            lecture = practice_lecture(request, lecture_id, lock=True)
            submission, _ = PracticeSubmission.objects.get_or_create(lecture=lecture, user=request.user)
            if submission.submitted_at:
                return JsonResponse({'error': 'Сначала верните работу в черновик.'}, status=409)
            if submission.files.count() + len(files) > PRACTICE_MAX_FILES:
                return JsonResponse({'error': 'К работе можно прикрепить не более 10 файлов.'}, status=400)
            for file in files:
                obj = PracticeFile(submission=submission, name=file.name, size=file.size)
                obj.file.save(file.name, file, save=False)
                stored.append(obj.file)
                obj.save()
            submission.save(update_fields=['updated_at'])
    except Exception:
        for file in stored:
            file.storage.delete(file.name)
        raise
    return JsonResponse({'ok': True})


@login_required
@require_POST
def api_practice_file_delete(request, file_id):
    with transaction.atomic():
        obj = get_object_or_404(PracticeFile.objects.select_related('submission'), pk=file_id, submission__user=request.user)
        practice_lecture(request, obj.submission.lecture_id, lock=True)
        submission = PracticeSubmission.objects.get(pk=obj.submission_id)
        if submission.submitted_at:
            return JsonResponse({'error': 'Сначала верните работу в черновик.'}, status=409)
        obj.delete()
        submission.save(update_fields=['updated_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def api_practice_submit(request, lecture_id):
    with transaction.atomic():
        lecture = practice_lecture(request, lecture_id, lock=True)
        submission = PracticeSubmission.objects.filter(lecture=lecture, user=request.user).first()
        if not submission or not submission.files.exists():
            return JsonResponse({'error': 'Прикрепите хотя бы один файл перед сдачей работы.'}, status=400)
        if not submission.submitted_at:
            submission.submitted_at = timezone.now()
            submission.save(update_fields=['submitted_at', 'updated_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def api_practice_withdraw(request, lecture_id):
    with transaction.atomic():
        lecture = practice_lecture(request, lecture_id, lock=True)
        submission = get_object_or_404(PracticeSubmission, lecture=lecture, user=request.user)
        submission.submitted_at = None
        submission.save(update_fields=['submitted_at', 'updated_at'])
    return JsonResponse({'ok': True})


@login_required
def serve_practice_file(request, file_id):
    obj = get_object_or_404(PracticeFile.objects.select_related('submission'), pk=file_id)
    practice_lecture(request, obj.submission.lecture_id)
    if obj.submission.user_id != request.user.pk:
        if request.user.role != 'admin' or not obj.submission.submitted_at:
            raise Http404
    response = FileResponse(obj.file.open('rb'), as_attachment=True, filename=obj.name, content_type='application/octet-stream')
    response['X-Content-Type-Options'] = 'nosniff'
    return response
