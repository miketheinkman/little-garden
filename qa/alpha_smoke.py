"""Rehearse the alpha backend locally using a new, disposable Compose project and volume."""
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/alpha/compose.yaml"
HOST = "alpha.example.org"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    project = "garden-rehearsal-" + uuid4().hex[:12]
    volume = project + "-data"
    env = {**os.environ, "GARDEN_PUBLIC_HOST": HOST, "GARDEN_APP_IMAGE": "little-garden-alpha:rehearsal",
           "GARDEN_WEB_PORT": "0", "GARDEN_DATA_VOLUME": volume,
           "GARDEN_SECRET_KEY": secrets.token_urlsafe(64), "GARDEN_DB_PASSWORD": secrets.token_urlsafe(32),
           "GARDEN_DB_ADMIN_PASSWORD": secrets.token_urlsafe(32), "GARDEN_SMTP_HOST": "mail.invalid",
           "GARDEN_SMTP_USER": "rehearsal", "GARDEN_SMTP_PASSWORD": secrets.token_urlsafe(32),
           "GARDEN_FROM_EMAIL": "garden@example.org"}
    def compose(*args, capture=False):
        return subprocess.run(["docker", "compose", "-p", project, "-f", str(COMPOSE), *args],
                              env=env, check=True, text=True, stdout=subprocess.PIPE if capture else None)
    def manage(*args):
        return compose("run", "--rm", "--no-deps", "-T", "web", "python", "manage.py", *args)
    def check_http():
        port = compose("port", "web", "8000", capture=True).stdout.strip()
        assert port.startswith("127.0.0.1:"), port
        opener = build_opener(ProxyHandler({}), NoRedirect())
        def get(path, host=HOST, https=True):
            headers = {"Host": host}
            if https:
                headers["X-Forwarded-Proto"] = "https"
            try:
                return opener.open(Request(f"http://{port}{path}", headers=headers), timeout=5)
            except HTTPError as error:
                return error
        for _ in range(60):
            try:
                with get("/login/") as response:
                    if response.status == 200:
                        break
            except (URLError, ConnectionError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("The alpha login page did not become ready.")
        with get("/login/") as response:
            assert "Secure" in response.headers.get("Set-Cookie", "")
            assert "max-age=" in response.headers["Strict-Transport-Security"]
        with get("/login/", https=False) as response:
            assert response.status == 301 and response.headers["Location"] == f"https://{HOST}/login/"
        with get("/login/", host="wrong.example.org") as response:
            assert response.status == 400
        for path, signature in [("garden.css", None), ("phonics/words/sun.ogg", b"OggS")]:
            with get("/static/" + path) as response:
                assert response.status == 200
                body = response.read(128)
                assert body and (signature is None or body.startswith(signature))
    compose("config", "--quiet")
    compose("build", "web")
    subprocess.run(["docker", "volume", "create", volume], check=True, stdout=subprocess.DEVNULL)
    try:
        compose("up", "-d", "--wait", "db")
        manage("migrate", "--noinput")
        manage("check", "--deploy")
        manage("shell", "-c", """
from django.contrib.auth import get_user_model
from django.db import connection
from pathlib import Path
assert all(not Path('/app', p).exists() for p in ('db.sqlite3','.private-mail','.local-secret','.little-garden-live','.git','.venv'))
with connection.cursor() as c:
    c.execute('SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user')
    assert c.fetchone() == (False, False, False)
assert not get_user_model().objects.exists()
get_user_model().objects.create_user('rehearsal-parent')
""")
        manage("shell", "-c", """
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, override_settings
from pilot.models import ParentInvitation
assert settings.INVITE_ONLY_SIGNUP
parent = Client(HTTP_HOST=settings.PUBLIC_HOST)
fields = dict(username='invited-family', email='override@example.org', password1='RehearsalGarden83', password2='RehearsalGarden83')
assert b'Invitation code' in parent.post('/signup/', fields, secure=True).content
assert not get_user_model().objects.filter(username=fields['username']).exists()
with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
    call_command('invite_parent', 'invited@example.org')
    code = mail.outbox[-1].body.split(chr(10) * 2)[2]
assert parent.post('/signup/', {'code': code}, secure=True).status_code == 302
assert parent.post('/signup/', fields, secure=True).url == '/'
assert get_user_model().objects.get(username=fields['username']).email == 'invited@example.org'
assert not ParentInvitation.available().exists()
assert b'invalid or has expired' in Client(HTTP_HOST=settings.PUBLIC_HOST).post('/signup/', {'code': code}, secure=True).content
""")
        compose("up", "-d", "--no-build", "web")
        check_http()
        compose("down")
        compose("up", "-d", "--no-build", "web")
        check_http()
        manage("shell", "-c", "from django.contrib.auth import get_user_model; assert get_user_model().objects.filter(username='rehearsal-parent').exists()")
        print("Passed fresh PostgreSQL initialization, limited role, HTTP settings, static audio and data persistence.")
    finally:
        compose("down")
        subprocess.run(["docker", "volume", "rm", volume], check=True)


if __name__ == "__main__":
    main()
