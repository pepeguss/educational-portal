"""Prepare the database and static files before starting the application."""
import os
import shutil
import subprocess
import sys

if sys.argv[1:2] == ['gunicorn']:
    # Also works with the development bind mount over /app.
    shutil.copytree('/opt/portal-vendor', 'static/vendor', dirs_exist_ok=True)
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], check=True)
    subprocess.run([sys.executable, 'manage.py', 'collectstatic', '--noinput'], check=True)
os.execvp(sys.argv[1], sys.argv[1:])
