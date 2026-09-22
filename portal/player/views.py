from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_exempt
from .models import Section, Lecture, LectureFile

@login_required
@xframe_options_exempt  
def serve_file(request, file_id):
    try:
        obj = LectureFile.objects.get(id=file_id)
    except LectureFile.DoesNotExist:
        raise Http404
    
    
    response = FileResponse(obj.file.open('rb'), content_type='application/pdf' if obj.type == 'pdf' else None)
    response['Content-Disposition'] = f'inline; filename="{obj.name}"'
    return response


@login_required
def index_view(request):
    sections = Section.objects.prefetch_related('lectures').all()
    return render(request, 'player/index.html', {'sections': sections})

@login_required
def lecture_view(request, lecture_id):
    lecture = get_object_or_404(Lecture.objects.prefetch_related('files'), id=lecture_id)
    return render(request, 'player/lecture.html', {'lecture': lecture})

@login_required
def admin_view(request):
    if request.user.role != 'admin':
        return redirect('player:index')
    sections = Section.objects.prefetch_related('lectures__files').all()
    return render(request, 'player/admin.html', {'sections': sections})

# --- API для админки (AJAX) ---
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
    lec = Lecture.objects.create(section=sec, title=title, description=desc)
    return JsonResponse({'id': lec.id, 'title': lec.title})

@login_required
@require_POST
def api_lecture_update(request, lecture_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    lec = get_object_or_404(Lecture, id=lecture_id)
    lec.title = request.POST.get('title', lec.title).strip()
    lec.description = request.POST.get('description', lec.description).strip()
    lec.save()
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
    return JsonResponse({'id': obj.id, 'name': obj.name, 'type': obj.type, 'url': obj.file.url})

@login_required
@require_POST
def api_file_delete(request, file_id):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    LectureFile.objects.filter(id=file_id).delete()
    return JsonResponse({'ok': True})