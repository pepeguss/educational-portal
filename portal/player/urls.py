from django.urls import path
from . import views

app_name = 'player'
urlpatterns = [
    path('', views.index_view, name='index'),
    path('lecture/<int:lecture_id>/', views.lecture_view, name='lecture'),
    path('admin/', views.admin_view, name='admin_panel'),
    path('api/department/create/', views.api_department_create, name='api_department_create'),
    path('api/user/<int:user_id>/department/', views.api_user_department_update, name='api_user_department_update'),

    path('api/section/create/', views.api_section_create, name='api_section_create'),
    path('api/section/<int:section_id>/update/', views.api_section_update, name='api_section_update'),
    path('api/section/<int:section_id>/delete/', views.api_section_delete, name='api_section_delete'),

    path('api/lecture/<int:section_id>/create/', views.api_lecture_create, name='api_lecture_create'),
    path('api/lecture/<int:lecture_id>/update/', views.api_lecture_update, name='api_lecture_update'),
    path('api/lecture/<int:lecture_id>/delete/', views.api_lecture_delete, name='api_lecture_delete'),

    path('api/file/<int:lecture_id>/upload/', views.api_file_upload, name='api_file_upload'),
    path('api/file/<int:file_id>/delete/', views.api_file_delete, name='api_file_delete'),

    path('file/<int:file_id>/', views.serve_file, name='serve_file'),
]
