from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import User

def login_view(request):
    if request.user.is_authenticated:
        return redirect('player:index')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('player:index')
        return render(request, 'users/login.html', {'form': {'errors': ['Неверный логин или пароль']}})
    return render(request, 'users/login.html')

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password1')
        full_name = request.POST.get('full_name')
        if User.objects.filter(username=username).exists():
            return render(request, 'users/register.html', {'form': {'errors': ['Логин занят']}})
        user = User.objects.create_user(username=username, password=password, full_name=full_name)
        login(request, user)
        return redirect('player:index')
    return render(request, 'users/register.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('users:login')