"""Parent-only focus editing, editable weekly plans and curriculum evidence."""
import re
import uuid
from collections import defaultdict
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .assessment import evidence_method
from .focus import AUTO_SHAPES, MIX, TARGETS, active_configs, lesson_weight, policy_for, token
from .models import Learner, LessonPlan, Observation, Purpose
from .paint import STUDIO
from .practice import CURRENT_LESSONS
from .progression import Progress
from .scheduling import release_due
from .skills import CURRICULUM, FACETS, LABELS, OPERATORS, PATHS, SOUND, objectives, proficiency, round_change, scored_evidence


def choices(values):
    return [(v,v) for v in values]


def multiple(label, values):
    return forms.MultipleChoiceField(label=label, choices=choices(values), required=False,
                                     widget=forms.CheckboxSelectMultiple)


class FocusForm(forms.Form):
    name = forms.CharField(max_length=64, label="Focus name")
    letters = forms.CharField(required=False,max_length=100,help_text="For example, M S or SH.")
    numbers = forms.CharField(required=False,max_length=120,help_text="For example, 3–5, 8.")
    operators = multiple("Operations", sorted(set(OPERATORS.values())))
    subjects = multiple("Subjects", CURRICULUM)
    branches = multiple("Skill areas", sorted({b for _,b in PATHS.values()}))
    objectives = forms.MultipleChoiceField(label="Specific skills", required=False,
        choices=[(subject,sorted([(obj,LABELS[obj]) for obj,(root,_) in PATHS.items() if root==subject],
                                 key=lambda pair:pair[1])) for subject in CURRICULUM],
        widget=forms.SelectMultiple(attrs={"size":6}))
    colors = multiple("Colors", STUDIO["colors"])
    shapes = multiple("Shapes", AUTO_SHAPES)
    vocabulary = forms.CharField(required=False,max_length=180, label="Words", help_text="Separate words with commas.")
    interests = forms.CharField(required=False,max_length=180, help_text="For example, space, trains or dinosaurs.")
    context = forms.TypedChoiceField(label="Use focus in other lesson examples", coerce=int,
                                     help_text="An S focus can bring a snake into Animal Lookout. Finding the snake counts toward animal recognition.",
                                     choices=[(0,"Off"),(30,"Occasionally"),(65,"Often"),(85,"Frequently")],initial=65)
    mode = forms.ChoiceField(label="Practice rounds", choices=[("only","Only selected targets"),("mixed","Mix in familiar targets")])
    familiar = forms.CharField(label="Familiar letters for keyboard review",required=False,max_length=90)
    starts = forms.DateField(required=False,widget=forms.DateInput(attrs={"type":"date"}))
    ends = forms.DateField(required=False,widget=forms.DateInput(attrs={"type":"date"}))
    automatic = forms.BooleanField(required=False,label="Choose weekly targets from demonstrated skills")
    name_letters = forms.BooleanField(required=False,label="Start keyboard practice with letters from the learner’s name")
    context_only = forms.BooleanField(required=False,label="Use as background context only")

    def __init__(self,*args,**kwargs):
        super().__init__(*args,label_suffix="",**kwargs)
        for index, label in enumerate(dict.fromkeys([*MIX.values(),"Other activities"])):
            self.fields[f"weight_{index}"] = forms.IntegerField(label=label, min_value=0,max_value=100,
                                                                 required=False,initial=1)
    def clean(self):
        data = super().clean()
        if data.get("ends") and data.get("starts") and data["ends"] < data["starts"]:
            self.add_error("ends","Choose an end date on or after the start date.")
        for field in ("letters","familiar"):
            raw = data.get(field,"").strip().upper()
            if raw and not re.fullmatch(r"[A-Z ,]+",raw):
                self.add_error(field,"Use letters A through Z.")
            else:
                parts = re.findall(r"[A-Z]+",raw)
                data[field] = list(dict.fromkeys(v for part in parts for v in ([part] if field=="letters" and part in {"SH","CH","TH"} else part)))
        numbers = set()
        for part in re.split(r"[,\s]+",data.get("numbers","").strip()):
            if not part:
                continue
            m = re.fullmatch(r"(\d{1,3})(?:[-–](\d{1,3}))?",part)
            if not m or not int(m[1])<=int(m[2] or m[1])<=100:
                self.add_error("numbers","Use numbers or ranges between 0 and 100.")
                break
            numbers.update(range(int(m[1]),int(m[2] or m[1])+1))
        data["numbers"] = list(map(str,sorted(numbers)))
        for field in ("vocabulary","interests"):
            data[field] = list(dict.fromkeys(w.strip().lower() for w in data.get(field,"").split(",") if w.strip()))
        dimensions = ("subjects","branches","objectives","operators","letters","numbers","colors","shapes","vocabulary","interests","familiar")
        self.config = {k:data[k] for k in dimensions if data.get(k)}
        if not self.config and not (data.get("automatic") or data.get("name_letters")):
            self.add_error(None,"Choose a subject, target or interest, or enable weekly targets.")
        self.config.update(context=data.get("context",0),mode=data.get("mode","only"))
        if data.get("name_letters"):
            self.config["name_letters"] = True
        self.config["weights"] = {f.label:0 if data.get("context_only") else data[k] if data.get(k) is not None else 1
                                  for k,f in self.fields.items() if k.startswith("weight_")}
        return data


@login_required
@never_cache
@require_http_methods(["GET","POST"])
def focus_home(request,pk):
    child = get_object_or_404(Learner,parent=request.user,pk=pk)
    rows = child.focuses.all().order_by("pk")
    edit_id = request.GET.get("edit")
    row = get_object_or_404(rows,pk=edit_id) if edit_id and edit_id.isdecimal() else None
    if edit_id and not row:
        raise Http404
    initial = {}
    if row:
        initial = {**row.config,"name":row.name,"automatic":row.automatic,"starts":row.starts,"ends":row.ends}
        for field in ("letters","numbers","vocabulary","interests","familiar"):
            initial[field] = ", ".join(initial.get(field,[]))
        for k,f in FocusForm().fields.items():
            if k.startswith("weight_"):
                initial[k] = row.config.get("weights",{}).get(f.label,1)
        initial["context_only"] = not any(row.config.get("weights",{"default":1}).values())
    form = FocusForm(request.POST if request.method=="POST" else None,initial=initial)
    if request.method=="POST":
        if request.POST.get("action") in {"pause","resume","remove"}:
            if not request.POST.get("focus_id","").isdecimal():
                raise Http404
            target = get_object_or_404(rows,pk=request.POST["focus_id"])
            if request.POST["action"]=="remove":
                target.delete()
            else:
                rows.filter(pk=target.pk).update(paused=request.POST["action"]=="pause")
            return redirect("focus",pk)
        if form.is_valid():
            data = form.cleaned_data
            values = {k:data[k] for k in ("name","automatic","starts","ends")}
            if row:
                rows.filter(pk=row.pk).update(**values,config=form.config)
            else:
                child.focuses.create(**values,config=form.config)
            messages.success(request,"Focus saved.")
            return redirect("focus",pk)
    configs = active_configs(child)
    picks = []
    for key,lesson in CURRENT_LESSONS.items():
        if lesson.get("checkin") or not lesson_weight(key,configs,child.lesson_theme):
            continue
        picks.append((key,lesson["title"]))
    saved = list(rows)
    for entry in saved:
        entry.skill_labels = [LABELS[o] for o in entry.config.get("objectives",[]) if o in LABELS]
    return render(request,"focus.html",dict(child=child, rows=saved, form=form, editing=row,picks=picks,
                effective=configs,weights=[form[k] for k in form.fields if k.startswith("weight_")]))


@login_required
@never_cache
@require_http_methods(["GET","POST"])
def focus_week(request, pk):
    child = get_object_or_404(Learner,parent=request.user,pk=pk)
    today = timezone.localdate()
    progress = Progress(child)
    days = []
    for i in range(5):
        day = today + timedelta(days=i)
        configs = active_configs(child,day)
        candidates = progress.recommendations(configs=configs, seed=day.isoformat(), limit=len(CURRENT_LESSONS))
        # A context-only focus never creates assignments. Include ordinary enrichment choices
        # for a parent editing a day that has direct practice available.
        direct = [r for r in candidates if lesson_weight(r["key"],configs,child.lesson_theme)]
        if not direct:
            days.append(dict(day=day,options=[],selected="",targets=[]))
            continue
        previous = [d["selected"] for d in days[-2:]]
        chosen = next((r for r in direct if r["key"] not in previous),direct[0])
        if any(c.get("automatic") for c in configs) and i==3:
            chosen = next((r for r in candidates if not lesson_weight(r["key"],configs,child.lesson_theme)),chosen)
        targets = [", ".join(c[k]) for c in configs for k in ("letters","numbers","colors","shapes") if c.get(k)]
        days.append(dict(day=day,options=candidates,selected=chosen["key"],targets=targets))
    for day in days:
        day["submission"] = uuid.uuid5(uuid.NAMESPACE_URL, f"little-garden/focus/{pk}/{day['day']}")
    saved = {plan.submission:plan for plan in child.lessonplan_set.filter(
        submission__in=[day["submission"] for day in days]).annotate(released=Count("assignment"))}
    for day in days:
        plan = saved.get(day["submission"])
        if plan and (plan.next_on or plan.released):
            day.update(saved=plan, saved_title=CURRENT_LESSONS[plan.lesson]["title"])
    if request.method == "POST":
        with transaction.atomic():
            Learner.objects.filter(pk=pk).update(nickname=F("nickname"))
            for day in days:
                date = day["day"]
                key = request.POST.get(date.isoformat())
                if not key or day.get("saved"):
                    continue
                if key not in {r["key"] for r in day["options"]}:
                    raise Http404
                values = dict(lesson=key,next_on=date,repeat="once",follow_focus=False,
                              focus_policy=policy_for(child,key,configs=active_configs(child,date)))
                plan,created = child.lessonplan_set.get_or_create(submission=day["submission"],defaults=values)
                if not created and not plan.next_on and not plan.assignment_set.exists():
                    child.lessonplan_set.filter(pk=plan.pk).update(**values)
            release_due(child,today)
        messages.success(request,"Saved the selected dates. You can edit upcoming dates in the lesson planner.")
        return redirect("planner",pk)
    return render(request,"focus_week.html",dict(child=child,days=days))


@login_required
@never_cache
def skill_report(request,pk):
    child = get_object_or_404(Learner,parent=request.user,pk=pk)
    purpose = request.GET.get("purpose","")
    if purpose and purpose not in Purpose.values:
        raise Http404
    scores = defaultdict(list)
    facets = defaultdict(lambda: defaultdict(list))
    for sample, target in scored_evidence(child,purpose):
        obj = target["objective"]
        scores[obj].append((sample.score,sample.assignment_id,sample.measured))
        for dimension,values in target["facets"].items():
            for value in set(values):
                facets[obj][dimension,value].append((sample.score,sample.assignment_id,sample.measured))
    lessons = defaultdict(list)
    for key,lesson in CURRENT_LESSONS.items():
        for obj in objectives(key):
            lessons[obj].append((key,lesson))
    notes = Observation.objects.filter(learner=child,assignment__isnull=False)
    if purpose:
        notes = notes.filter(assignment__purpose=purpose)
    observed = defaultdict(int)
    for entry in notes.values("assignment__lesson").annotate(count=Count("pk")):
        mapped = objectives(entry["assignment__lesson"])
        if len(mapped)==1:
            observed[mapped[0]] += entry["count"]

    def stats(values):
        return dict(count=len(values),percent=round(sum(v[0] for v in values)/len(values)) if values else None,
                    status=proficiency(values),change=round_change(values))
    groups = []
    for subject,branches in CURRICULUM.items():
        sections, all_values = [],[]
        for branch in branches:
            rows, values = [],[]
            for obj,(root,area) in PATHS.items():
                if (root,area)!=(subject,branch) or obj not in lessons:
                    continue
                options = lessons[obj]
                key,lesson = next(((k,l) for k,l in options if not l.get("checkin")),options[0])
                points = scores[obj]
                values.extend(points)
                concepts = []
                for (dim,value), observations in sorted(facets[obj].items()):
                    config_domain = "letters" if dim=="sounds" else "vocabulary" if dim in {"words","animals"} else dim
                    link = None
                    if TARGETS.get(obj) == config_domain:
                        config = {config_domain:[value],"mode":"only"}
                        policy = policy_for(child,key,"review",configs=[config],mode="only")
                        policy["contains"] = True
                        link = token(child,key,policy)
                    concepts.append(dict(label=FACETS[dim],value=value,focus=link,**stats(observations)))
                rows.append(dict(observations=observed[obj],objective=obj,label=LABELS[obj],key=key,concepts=concepts,observe=evidence_method(lesson)=="observation",
                                 **stats(points)))
            sections.append(dict(name=branch,rows=rows,observations=sum(r["observations"] for r in rows),
                                 covered=sum(bool(r["count"] or r["observations"]) for r in rows),total=len(rows),
                                 **stats(values)))
            all_values.extend(values)
        groups.append(dict(name=subject,sections=sections,observations=sum(s["observations"] for s in sections),
                           covered=sum(s["covered"] for s in sections),total=sum(s["total"] for s in sections),
                           **stats(all_values)))
    return render(request,"skill_report.html",dict(child=child,groups=groups,purpose=purpose,purposes=Purpose.choices))

@login_required
@never_cache
def objective_details(request, pk, objective):
    from django.core.paginator import Paginator
    from .models import QuestionAttempt
    from .practice import LESSONS
    from .skills import COLOR, LETTER

    child = get_object_or_404(Learner,parent=request.user,pk=pk)
    keys = [k for k in CURRENT_LESSONS if objective in objectives(k)]
    if not keys:
        raise Http404
    key = next((k for k in keys if not CURRENT_LESSONS[k].get("checkin")),keys[0])
    purpose = request.GET.get("purpose","")
    if purpose and purpose not in Purpose.values:
        raise Http404
    values = defaultdict(list)
    for sample,target in scored_evidence(child,purpose):
        if target["objective"] == objective:
            for dim, targets in target["facets"].items():
                for target_value in targets:
                    values[dim,target_value].append((sample.score,sample.assignment_id))
    # Known finite teaching sets can also be selected before any evidence exists.
    if objective in LETTER:
        domain, expected = "letters", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    elif objective in SOUND:
        domain = "sounds"
        if objective == "middle-sound":
            expected = "AEIOU"
        elif objective == "digraphs":
            expected = ["SH","CH","TH"]
        else:
            from .remix import CVC
            expected = sorted({word[0].upper() for word in CVC} | {"S","M"})
    elif objective in COLOR:
        domain, expected = "colors", STUDIO["colors"]
    elif objective == "same-different":
        domain, expected = "shapes", AUTO_SHAPES
    elif objective == "number-keys":
        domain, expected = "numbers", map(str,range(10))
    else:
        domain, expected = "", []
    for v in expected:
        values[domain,v]
    targets = []
    for (dim,value), seen in sorted(values.items()):
        link = None
        field = "letters" if dim=="sounds" else "vocabulary" if dim in {"words","animals"} else dim
        if field == TARGETS.get(objective):
            policy = policy_for(child,key,configs=[{field:[value]}],mode="only")
            policy["contains"] = True
            link = token(child,key,policy)
        targets.append(dict(label=FACETS[dim], value=value, count=len(seen), status=proficiency(seen),link=link))
    legacy = Q(pk__in=[])
    for old_key in LESSONS:
        mapped = objectives(old_key)
        if objective in mapped:
            match = Q(assignment__lesson=old_key)
            if len(mapped) > 1:
                match &= Q(step=mapped.index(objective))
            legacy |= match
    attempts = QuestionAttempt.objects.filter(assignment__learner=child).filter(
        Q(direct__objective=objective) | (Q(direct={}) & legacy)).select_related("assignment")
    observations = Observation.objects.filter(learner=child,assignment__lesson__in=keys)
    if purpose:
        attempts = attempts.filter(assignment__purpose=purpose)
        observations = observations.filter(assignment__purpose=purpose)
    return render(request,"objective_details.html",dict(child=child,key=key,title=LABELS[objective],targets=targets,
                  history=Paginator(attempts.order_by("-created","-pk"),25).get_page(request.GET.get("page")),
                  notes=observations.order_by("-observed_on")[:10],purpose=purpose))
