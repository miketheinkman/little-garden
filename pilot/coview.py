"""A household can see the latest visible garden screen while its viewer is open."""
import re

from django.contrib.auth.decorators import login_required
from django.core.cache import caches
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import matchmaker
from .art import art_item
from .models import Assignment, Learner
from .practice import LESSONS


LEASE_SECONDS = matchmaker.LEASE


@never_cache
@login_required
def room(request):
    children = Learner.objects.filter(parent=request.user).order_by("pk")
    return render(request, "coview.html", {"children": children})


def lesson_state(kind, data):
    state = {"retry": data.get("retry") == "1"}
    if kind in {"draw", "color", "mirror"} and re.fullmatch("[0-5]{768}", data.get("pixels", "")):
        state["pixels"] = data["pixels"]
    elif kind == "type":
        state["typed"] = data.get("typed", "")[:80]
    elif kind == "basket":
        value = data.get("count", "")
        state["count"] = int(value) if re.fullmatch(r"[0-9]|1[0-2]", value) else 0
    elif kind == "trace":
        value = data.get("percent", "")
        state["percent"] = int(value) if re.fullmatch(r"[0-9]{1,2}|100", value) else 0
    elif kind == "mouse":
        for axis in ("x", "y"):
            value = data.get(axis, "")
            if re.fullmatch(r"[0-9]{1,2}|100", value):
                state[axis] = int(value)
    return state


@never_cache
@require_POST
def broadcast(request, pk):
    if request.user.is_authenticated or request.session.get("child") != pk:
        raise Http404
    live = caches["coview"]
    watching = live.get(f"watch:{pk}") is not None
    source = request.POST.get("source", "")
    source = source if matchmaker.token(source) else ""
    if not watching:
        live.delete(f"frame:{pk}")
    elif request.POST.get("screen") == "garden":
        live.set(f"frame:{pk}", {"screen": "garden", "source": source}, LEASE_SECONDS)
    elif request.POST.get("screen") == "lesson":
        try:
            row_id = int(request.POST["assignment"])
            step = int(request.POST["step"])
        except (KeyError, ValueError):
            return HttpResponseBadRequest()
        row = get_object_or_404(Assignment, pk=row_id, learner_id=pk, step=step, completed=None, removed_at=None)
        state = None if source and request.POST.get("metadata") == "1" else lesson_state(LESSONS[row.lesson]["kind"], request.POST)
        live.set(f"frame:{pk}", {"screen": "lesson", "row": row.pk, "step": step, "state": state, "source": source}, LEASE_SECONDS)
    else:
        return HttpResponseBadRequest()
    signal = matchmaker.child_signal(pk, source, request.POST) if watching else {}
    return JsonResponse({"watching": watching, **signal})


def recent_response(child_id, title, step, action):
    live = caches["coview"]
    if live.get(f"watch:{child_id}"):
        live.set(f"response:{child_id}", f"{title} · Step {step + 1} · {action}", LEASE_SECONDS)


def current_frame(child, signal):
    frame = caches["coview"].get(f"frame:{child.pk}")
    if not frame:
        return None
    if frame["screen"] == "garden":
        rows = child.assignment_set.filter(completed=None, removed_at=None)
        titles = [(row.round_snapshot or LESSONS[row.lesson])["title"] for row in rows]
        return {"source": frame.get("source", ""), "html": render_to_string("coview_scene.html", {"garden": True, "titles": titles})}
    row = child.assignment_set.filter(pk=frame["row"], step=frame["step"], completed=None, removed_at=None).first()
    if not row:
        return None
    source = frame.get("source", "")
    if source and signal.get("source") == source and signal.get("direct") is True:
        return {"source": source, "reuse": True}
    lesson = row.round_snapshot or LESSONS[row.lesson]
    item = lesson["items"][row.step]
    if "shape" in item:
        item = art_item(item)
    return {"source": frame.get("source", ""), "html": render_to_string("coview_scene.html", {"lesson": lesson, "item": item, "step": row.step}),
            "state": frame["state"]}


@never_cache
@login_required
@require_POST
def watch(request):
    children = Learner.objects.filter(parent=request.user)
    selected = request.POST.get("child")
    if selected != "all":
        if not selected or not re.fullmatch("[0-9]{1,18}", selected):
            return HttpResponseBadRequest()
        children = [get_object_or_404(children, pk=selected)]
    result = {}
    signals = matchmaker.object_field(request.POST, "signals")
    replies = {}
    for child in children:
        caches["coview"].set(f"watch:{child.pk}", True, LEASE_SECONDS)
        signal = signals.get(str(child.pk))
        signal = signal if isinstance(signal, dict) else {}
        frame = current_frame(child, signal)
        replies[child.pk] = matchmaker.viewer_signal(child.pk, frame and frame["source"], signal)
        if frame:
            frame["response"] = caches["coview"].get(f"response:{child.pk}")
        result[child.pk] = frame
    return JsonResponse({"children": result, "signals": replies})
