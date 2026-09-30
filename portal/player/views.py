from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Count
from django.urls import reverse
from users.models import Department, User
from .models import Section, Lecture, LectureFile

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
def lecture_view(request, lecture_id):
    lecture = get_object_or_404(
        Lecture.objects.visible_to(request.user).prefetch_related('files'), id=lecture_id,
    )
    return render(request, 'player/lecture.html', {'lecture': lecture})

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
    except ValidationError as error:
        return JsonResponse({'error': error.messages[0]}, status=400)
    with transaction.atomic():
        lec = Lecture.objects.create(
            section=sec, title=title, description=desc, test_url=test_url, is_public=is_public,
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
