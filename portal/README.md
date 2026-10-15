# Ubuntu Server: автономная бета в локальной сети

Dockerfile собирает Linux-контейнер, подходящий и для Ubuntu Server, и для Docker
Desktop в режиме Linux containers. На Ubuntu нужны Docker Engine и Compose v2.
Серверный вариант — **compose.server.yaml**, обычный compose.yaml оставлен для разработки.

## Подготовка до перевозки сервера

Сборка требует интернета (образы, Python/JS-пакеты, LibreOffice и шрифты).
Соберите и проверьте образ заранее на самом Ubuntu-сервере. После сборки сайт,
PDF, PPTX, DOCX, MP3 и MP4 работают без внешних CDN. Яндекс Формы требуют интернета:
в серверном автономном режиме вместо них отображается сообщение.

В каталоге `portal` на Ubuntu:

```sh
# Если .env уже есть, допишите настройки в него, не перезаписывайте файл.
cp -n .env.example .env
openssl rand -hex 32
nano .env
```

Вставьте результат openssl в `DJANGO_SECRET_KEY`, а текущий IPv4 сервера — в
`DJANGO_ALLOWED_HOSTS`, например:

```dotenv
DJANGO_SECRET_KEY=сюда_результат_openssl
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.100
DJANGO_CSRF_TRUSTED_ORIGINS=
PORTAL_PORT=8000
```

В ALLOWED_HOSTS только IP/имена, без протокола и порта. При обычном открытии сайта
через его IP CSRF_TRUSTED_ORIGINS можно оставить пустым. Если впоследствии появится
отдельный доверенный origin, укажите его целиком, например `https://training.example`.
DEBUG в серверном Compose выключен. .env не включается в Git и Docker-образ.

```sh
docker compose -f compose.server.yaml build app
```

**Если нужны нынешние пользователи и лекции, сначала перенесите данные по разделу
ниже.** При первом запуске с пустыми томами создаётся новая база.

```sh
docker compose -f compose.server.yaml up -d --no-build
docker compose -f compose.server.yaml logs --tail=100 app
```

Миграции и collectstatic выполняются автоматически перед запуском Gunicorn.
Данные хранятся в именованных томах `training_portal_db` (SQLite) и
`training_portal_media` (материалы и предпросмотры). Обновление образа и пересоздание
контейнера их не удаляет. **Не выполняйте down -v**: эта команда удаляет тома.

Если база новая, создайте администратора Django и назначьте ему роль портала:

```sh
docker compose -f compose.server.yaml exec app python manage.py createsuperuser
docker compose -f compose.server.yaml exec app python manage.py shell -c "from users.models import User; User.objects.filter(is_superuser=True).update(role='admin')"
```

С другого компьютера откройте `http://IP_СЕРВЕРА:8000`. Проверьте вход, загрузку PPTX,
просмотр PDF/DOCX, мобильный вид и сохранность данных после перезапуска контейнера.
Повторите с отключённым внешним интернетом. Согласуйте с администратором сети
доступ сотрудников к TCP 8000 и ограничения доступа из остальных сетей с учётом
правил публикации портов Docker.

## Перенос существующей базы и материалов

Git не переносит db.sqlite3 и media. Остановите прежнее приложение на исходной
машине и скопируйте **оба** объекта на сервер в каталог portal. Сохраните отдельную
резервную копию. При переносе архива не потеряйте подкаталоги `media/previews`.

Перед первым запуском серверного приложения выполните из portal (Ubuntu):

```sh
docker compose -f compose.server.yaml run --rm --no-deps -v "$PWD:/import:ro" app python -c "from pathlib import Path; import shutil; target=Path('/data/db.sqlite3'); assert not target.exists(), 'Target database already exists; import cancelled'; assert Path('/import/db.sqlite3').is_file(), 'Source database missing'; assert not any(Path('/media').iterdir()), 'Target media is not empty'; shutil.copy2('/import/db.sqlite3', target); shutil.copytree('/import/media', '/media', dirs_exist_ok=True)"
```

Эта команда рассчитана на пустые серверные тома и откажется перезаписывать имеющуюся
базу. Если на исходной машине база использовала WAL, перед переносом корректно
завершите все процессы, работавшие с ней; не копируйте открытый файл базы.

## Смена IP в компании и обновления

Узнать адреса: `hostname -I`. Адрес в компании может отличаться от домашнего.
Желательно согласовать постоянный IP или DHCP reservation с администратором сети.

```sh
nano .env
docker compose -f compose.server.yaml up -d --no-build --force-recreate app
```

После изменения .env нужен пересозданный контейнер: `restart` не подхватывает новое
окружение. Сборка и Git для смены IP не нужны. Для обновления кода можно использовать
Git, скопировать файлы или перенести готовый образ. На сервере с доступом к Git:

```sh
git pull
docker compose -f compose.server.yaml up -d --build app
```

Без интернета заранее соберите образ на совместимой архитектуре и перенесите его
архив. На машине сборки: `docker save -o training-portal-beta.tar training-portal:beta`.
На сервере: `docker load -i training-portal-beta.tar`, затем
`docker compose -f compose.server.yaml up -d --no-build app`.
Compose-файл и .env на сервере всё равно нужны; данные переносятся отдельно.

Для простой резервной копии с согласованными файлами остановите приложение и
выгрузите оба тома (не выполняйте параллельно обновление):

```sh
docker compose -f compose.server.yaml stop app
docker compose -f compose.server.yaml run --rm --no-deps -v "$PWD:/backup" app python -c "import tarfile, time; archive=tarfile.open('/backup/portal-backup-'+time.strftime('%Y%m%d-%H%M%S')+'.tar.gz', 'w:gz'); archive.add('/data', arcname='data'); archive.add('/media', arcname='media'); archive.close()"
docker compose -f compose.server.yaml up -d --no-build app
```

Храните архив и копию .env отдельно от репозитория и ограничьте доступ: в них
пользовательские данные и ключ. Копию стоит унести с диска самого сервера.

## Локальная разработка и презентации

После обновления выполните `python manage.py migrate`.

Для просмотра PPTX используется LibreOffice Impress: при загрузке создаётся
закрытый PDF-предпросмотр, который открывается в плеере с правами исходной лекции.
Анимация, переходы и встроенные видео не воспроизводятся.

В Docker конвертер и шрифты устанавливаются автоматически. Пересоберите образ:
`docker compose up --build -d app` и примените миграции:
`docker compose exec app python manage.py migrate`.

При запуске без Docker установите LibreOffice Impress и добавьте `soffice` в PATH
либо задайте `LIBREOFFICE_BINARY` в настройках Django (полный путь к исполняемому файлу).
Лимит PPTX — 100 МБ, время преобразования — до 120 секунд; при использовании
прокси его таймаут должен позволять дождаться подготовки слайдов.

Параметры PDF-экспорта: https://help.libreoffice.org/latest/en-US/text/shared/guide/pdf_params.html

Для запуска Python без Docker установите requirements.txt. Статические зависимости
подготавливаются один раз через Node.js и pnpm (Docker делает это сам):

```sh
cd assets
pnpm install --frozen-lockfile
pnpm run build
cd ..
python manage.py runserver
```
