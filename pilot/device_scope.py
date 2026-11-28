"""Give each installed learner app its own URL space and session cookie."""
import re
from uuid import UUID

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import get_script_prefix, set_script_prefix
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from .models import LearnerDevice


class LearnerAppScope:
    mount = re.compile(r"^/g/([a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12})(/.*)$")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        match = self.mount.match(request.path_info)
        if not match:
            return self.get_response(request)
        request.garden_device = UUID(match[1])
        request.urlconf = "garden.learner_urls"
        request.path_info = match[2]
        previous = get_script_prefix()
        prefix = previous.rstrip("/") + "/g/" + match[1] + "/"
        names = {settings.SESSION_COOKIE_NAME:"lg_app_session", settings.CSRF_COOKIE_NAME:"lg_app_csrf",
                 "messages":"lg_app_messages"}
        for original, scoped in names.items():
            request.COOKIES.pop(original, None)
            if scoped in request.COOKIES:
                request.COOKIES[original] = request.COOKIES[scoped]
        set_script_prefix(prefix)
        try:
            response = self.get_response(request)
        finally:
            set_script_prefix(previous)
        for original, scoped in names.items():
            if original in response.cookies:
                cookie = response.cookies.pop(original)
                response.cookies[scoped] = cookie.value
                response.cookies[scoped].update(dict(cookie))
                response.cookies[scoped]["path"] = prefix
        add_never_cache_headers(response)
        return response

    def process_view(self, request, view, args, kwargs):
        if not getattr(request, "garden_device", None):
            return None
        if not request.is_secure() and request.get_host().split(":")[0] not in {"localhost","127.0.0.1"}:
            return HttpResponseForbidden("Open this learner app over HTTPS.")
        if request.resolver_match.url_name in {"device_launch","manifest","device_worker","pair","prove"}:
            return None
        if (request.session.get("device") == str(request.garden_device) and
            LearnerDevice.objects.filter(pk=request.garden_device, learner_id=request.session.get("child"),
                                         learner__parent__is_active=True, expires__gt=timezone.now(),
                                         last_used__isnull=False).exists()):
            return None
        request.session.flush()
        return redirect("device_launch")
