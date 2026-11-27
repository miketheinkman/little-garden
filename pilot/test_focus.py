from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .assessment import evidence_method
from .assignments import assign_lesson
from .focus import active_configs, compile_round, focus_rank, policy_for, token
from .models import Learner, LessonPlan, SkillSample
from .practice import CURRENT_LESSONS, build_round
from .scheduling import release_due
from .skills import PATHS, direct_target, known_targets, objectives, scored_evidence
from .themes import assignment_lesson
from .tests import correct_submission


class FocusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parent = get_user_model().objects.create_user("focus-family")
        cls.child = Learner.objects.create(nickname="Fern",parent=cls.parent)

    def setUp(self):
        self.client.force_login(self.parent)

    def test_curriculum_coverage_and_ordinary_rounds(self):
        for key,lesson in CURRENT_LESSONS.items():
            with self.subTest(key=key):
                self.assertTrue(set(objectives(key)) <= PATHS.keys())
                self.assertEqual(build_round(key,2),compile_round(key,2,None,{}))
                for i,item in enumerate(build_round(key,0)["items"]):
                    self.assertIn(direct_target(key,item,i)["objective"],PATHS)

    def test_direct_evidence_mixed_checks_and_skips(self):
        row=assign_lesson(self.child,"sound-check-v1",0,purpose="placement")
        self.client.post(reverse("manage",args=[self.child.pk]),{"action":"play"})
        play=reverse("play",args=[row.pk])
        for step,item in enumerate(row.round_snapshot["items"]):
            fields=correct_submission(item) if step==0 else {"action":"skip"} if step==1 else {"answer":"Z"}
            self.client.post(play,{**fields,"step":step})
        self.assertEqual(list(row.samples.order_by("step").values_list("direct__objective","score")),
                         [("sounds",100),("digraphs",0)])
        self.assertEqual(row.question_attempts.get(step=1).direct["facets"]["phonemes"],["U · /ʌ/"])
        self.assertFalse(known_targets(self.child))

    def test_saved_preview_known_review_and_household_boundary(self):
        self.child.focuses.create(name="Letters",config={"letters":["M","S"],"mode":"only","familiar":["A"]})
        url=reverse("preview",args=[self.child.pk,"keys-v2",0])
        page=self.client.get(url)
        items=page.context["lesson"]["items"]
        self.assertEqual({i["answer"] for i in items},{"M","S"})
        self.assertEqual(len(items),2)
        frozen=page.context["focus_token"]
        mixed=self.client.get(url+"?mode=mixed").context["lesson"]["items"]
        self.assertEqual({i["answer"] for i in mixed},{"M","S","A"})
        self.child.focuses.update(config={"letters":["Z"]})
        self.client.post(reverse("library",args=[self.child.pk]),dict(lesson="keys-v2",variation=0,focus=frozen))
        self.assertEqual(assignment_lesson(self.child.assignment_set.get())["items"],items)
        other=Learner.objects.create(nickname="Sage",parent=self.parent)
        self.assertEqual(self.client.get(reverse("preview",args=[other.pk,"keys-v2",0]),{"focus":frozen}).status_code,404)
        stranger=get_user_model().objects.create_user("stranger")
        self.client.force_login(stranger)
        for route in ("focus","focus_week","skill_report"):
            self.assertEqual(self.client.get(reverse(route,args=[self.child.pk])).status_code,404)

    def test_operator_operands_cues_and_equivalent_context(self):
        policy={"theme":"garden","configs":[{"operators":["Addition"],"numbers":["3","4"],"mode":"only"},
                                            {"colors":["red"],"context":85,"weights":{"Other activities":0}}]}
        sample=compile_round("add-groups-v1",0,None,policy)
        for i,item in enumerate(sample["items"]):
            target=direct_target("add-groups-v1",item,i)
            self.assertEqual(target["facets"]["operators"],["Addition"])
            self.assertLessEqual(set(target["facets"]["numbers"]),{"3","4"})
            self.assertNotIn("colors",target["facets"])
            left,_,right=item["equation"].split()
            self.assertEqual(int(item["answer"]),int(left)+int(right))
        contexts={"theme":"garden","configs":[{"colors":["red"],"context":85,"weights":{"Other activities":0}}]}
        varied=set()
        for v in range(8):
            base=build_round("add-groups-v1",v)
            themed=compile_round("add-groups-v1",v,None,contexts)
            for a,b in zip(base["items"],themed["items"],strict=True):
                self.assertEqual({k:v for k,v in b.items() if k!="context_icon"},a)
                varied.add(b.get("context_icon"))
        self.assertIn(None,varied)
        self.assertGreater(len(varied),1)
        no_context={"theme":"garden","configs":[{"interests":["space"],"context":0}]}
        self.assertEqual(compile_round("add-groups-v1",0,None,no_context),build_round("add-groups-v1",0))

    def test_shape_and_evidence_limits(self):
        policy={"theme":"space","configs":[{"shapes":["triangle"]}]}
        for item in compile_round("same-different-v1",1,None,policy)["items"]:
            self.assertEqual(item["faces"][int(item["answer"])],"▲")
            self.assertEqual(item["faces"].count("▲"),1)
            self.assertEqual(direct_target("same-different-v1",item,0)["facets"],{"shapes":["triangle"]})
        for index in range(2):
            row=assign_lesson(self.child,"keys-v2",0,purpose="review")
            row.samples.create(step=0,strand="Keyboard use",level=1,score=100,
                               direct={"objective":"keys","facets":{"letters":["M"]}})
        self.assertEqual(known_targets(self.child),{("keys","letters","M")})
        url=reverse("objective_details",args=[self.child.pk,"keys"])
        page=self.client.get(url,{"purpose":"review"})
        self.assertContains(page,"Demonstrated")
        self.assertContains(page,"Check Z")
        old=self.child.assignment_set.create(lesson="keys-v1",step=1)
        old.samples.create(step=0,strand="Keyboard use",level=1,score=100)
        self.assertEqual(list(scored_evidence(self.child))[-1][1]["facets"],{})

    def test_empty_zero_weights_dates_and_safe_fallback(self):
        today=timezone.localdate()
        self.child.focuses.create(name="Paused",paused=True,config={"numbers":["2"]})
        self.child.focuses.create(name="Later",starts=today+timedelta(days=2),config={"letters":["S"]})
        self.assertEqual(policy_for(self.child,"keys-v2"),{})
        off=self.child.focuses.create(name="Theme only",config={"letters":["S"],"weights":{"Keyboard":0},"context":65})
        round_data=compile_round("keys-v2",0,None,policy_for(self.child,"keys-v2"))
        self.assertEqual(round_data,build_round("keys-v2",0))
        off.config={"numbers":["99"],"operators":["Addition"]}
        off.save()
        fallback=compile_round("add-groups-v1",0,None,policy_for(self.child,"add-groups-v1"))
        self.assertTrue(fallback["focus_notice"])
        self.assertEqual(fallback["items"],build_round("add-groups-v1",0)["items"])

    def test_pinned_and_following_schedule(self):
        config=self.child.focuses.create(name="First",config={"letters":["M","S"],"mode":"only"})
        date=timezone.localdate()
        for follow,key in [(False,"keys-v2"),(True,"my-letters-v1")]:
            LessonPlan.objects.create(learner=self.child,lesson=key,next_on=date,repeat="daily",follow_focus=follow,
                                      focus_policy=policy_for(self.child,key))
        release_due(self.child,date)
        self.child.assignment_set.update(completed=timezone.now())
        config.config={"letters":["Z"],"mode":"only"}
        config.save()
        release_due(self.child,date+timedelta(days=1))
        for row in self.child.assignment_set.filter(completed=None):
            expected={"M","S"} if row.lesson=="keys-v2" else {"Z"}
            self.assertEqual({i["answer"] for i in row.round_snapshot["items"]},expected)

    def test_weekly_override_and_progression(self):
        self.child.focuses.create(name="Weekly",config={"mode":"mixed"},automatic=True)
        self.assertEqual(active_configs(self.child)[0]["letters"],["S","A"])
        for i in range(2):
            row=assign_lesson(self.child,"sounds-v1",i,policy={})
            row.samples.create(step=0,strand="Letter sounds",level=1,score=100,
                               direct={"objective":"sounds","facets":{"sounds":["S"]}})
        self.assertEqual(active_configs(self.child)[0]["letters"],["A","T"])
        url=reverse("focus_week",args=[self.child.pk])
        days=self.client.get(url).context["days"]
        eligible=days[0]["options"]
        self.assertTrue(eligible)
        self.assertNotIn("blend-v1",{r["key"] for r in eligible})
        payload={days[0]["day"].isoformat():eligible[-1]["key"]}
        self.client.post(url,payload)
        self.client.post(url,payload)
        self.assertEqual(self.child.lessonplan_set.count(),1)

    def test_explicit_letters_and_assessments_are_stable(self):
        policy={"theme":"space","configs":[{"letters":["M","S"]}]}
        fixed=compile_round("my-letters-v1",0,"QXZ",policy)
        self.assertEqual({i["answer"] for i in fixed["items"]},set("QXZ"))
        for key in ("key-check-v1","sound-check-v1","number-check-v1"):
            self.assertEqual(len(compile_round(key,3,None,policy)["items"]),3)

    def test_parent_form_save_pause_edit_and_eligibility(self):
        from .focus import lesson_weight
        url=reverse("focus",args=[self.child.pk])
        fields=dict(name="Letter week",letters="m s",mode="only",context=65)
        self.assertRedirects(self.client.post(url,fields),url)
        row=self.child.focuses.get()
        configs=active_configs(self.child)
        self.assertGreater(lesson_weight("keys-v2",configs),0)
        self.assertEqual(lesson_weight("middle-sound-v1",configs),0)
        self.assertEqual(lesson_weight("digraphs-v1",configs),0)
        self.client.post(url,dict(action="pause",focus_id=row.pk))
        self.assertFalse(active_configs(self.child))
        self.client.post(url,dict(action="resume",focus_id=row.pk))
        self.client.post(url+f"?edit={row.pk}",dict(name="Arithmetic",numbers="3–5",operators=["Addition"],
                                                     objectives=["add-groups"],mode="only",context=0))
        configs=active_configs(self.child)
        self.assertEqual(configs[0]["numbers"],["3","4","5"])
        self.assertEqual(lesson_weight("take-away-v1",configs),0)
        self.assertGreater(lesson_weight("add-groups-v1",configs),0)

    def test_context_only_no_plan_and_missing_audio_falls_back(self):
        from unittest.mock import patch
        self.child.focuses.create(name="Space",config={"interests":["space"],"context":85})
        week=self.client.get(reverse("focus_week",args=[self.child.pk]))
        self.assertTrue(all(not day["selected"] for day in week.context["days"]))
        policy={"theme":"garden","configs":[{"letters":["M"]}]}
        with patch("pilot.focus.has_audio",return_value=False):
            generated=compile_round("keys-v2",0,None,policy)
        self.assertTrue(generated["focus_notice"])
        self.assertEqual(generated["items"],build_round("keys-v2",0)["items"])

    def test_rollup_counts_two_operands_as_one_question(self):
        row=assign_lesson(self.child,"add-groups-v1",0,purpose="placement")
        target=direct_target(row.lesson,row.round_snapshot["items"][0],0)
        row.samples.create(step=0,strand="Number sense",level=2,score=100,direct=target)
        row.samples.create(step=1,strand="Number sense",level=2,score=100,direct=target,puzzle_help=1)
        report=self.client.get(reverse("skill_report",args=[self.child.pk]),{"purpose":"placement"})
        group=next(g for g in report.context["groups"] if g["name"]=="Math")
        self.assertEqual((group["covered"],group["count"],group["percent"]),(1,1,100))
        section=next(s for s in group["sections"] if s["name"]=="Arithmetic")
        activity=next(r for r in section["rows"] if r["objective"]=="add-groups")
        self.assertGreater(len(activity["concepts"]),1)
        self.assertTrue(all(c["count"]==1 for c in activity["concepts"]))

    def test_recorded_feedback_and_scheduled_preview_replay(self):
        from .models import LessonFeedback
        import uuid
        self.child.focuses.create(name="Selected",config={"letters":["M","S"],"mode":"only"})
        path=reverse("preview",args=[self.child.pk,"keys-v2",0])
        page=self.client.get(path)
        items=page.context["lesson"]["items"]
        frozen=page.context["action_token"]
        self.client.post(path,{"action":"feedback","kind":"worked","note":"Focused round"})
        day=timezone.localdate()+timedelta(days=4)
        self.client.post(reverse("planner",args=[self.child.pk])+f"?lesson=keys-v2&v=0&focus={frozen}",
                         {"lesson":"keys-v2","start":day,"repeat":"once","submission":uuid.uuid4()})
        self.child.focuses.update(config={"letters":["P"]})
        self.child.lesson_theme="space"
        self.child.save()
        replay=self.client.get(reverse("feedback_round",args=[LessonFeedback.objects.get().pk]))
        self.assertEqual(replay.context["lesson"]["items"],items)
        release_due(self.child,day)
        self.assertEqual(assignment_lesson(self.child.assignment_set.get())["items"],items)

    def test_automatic_blending_requires_verified_letter_sound_links(self):
        from .focus import permitted_blend
        self.assertIsNone(permitted_blend("blend-v1",0,"garden",{"S","T"}))
        selected=permitted_blend("blend-v1",0,"garden",{"S","A","T"})
        self.assertEqual([i["answer"] for i in selected[1]["items"]],list("SAT"))
        self.assertEqual(direct_target("digraphs-v1",{"answer":"sh","word":"ship","prompt":"Listen."},0)["facets"]["phonemes"],["SH · /ʃ/"])
        self.assertNotIn("phonemes",direct_target("digraphs-v1",{"answer":"ch","word":"choir","prompt":"Listen."},0)["facets"])

    def test_comparison_sharing_and_basket_follow_one_number(self):
        from .focus import has_audio, lesson_weight
        from .question_sets import identity
        for theme in ("garden","space"):
            for n in (0,5,8,12):
                configs = [{"numbers":[str(n)],"context":0,"mode":"only"}]
                policy = {"theme":theme,"mode":"only","configs":configs}
                for key in ("more-v1","berry-basket-v1","harvest-v1"):
                    with self.subTest(theme=theme,n=n,key=key):
                        items = compile_round(key,4,None,policy)["items"]
                        if key=="harvest-v1" and n==0:
                            self.assertEqual(lesson_weight(key,configs,theme),0)
                            continue
                        self.assertGreater(lesson_weight(key,configs,theme),0)
                        signatures = set()
                        for i,item in enumerate(items):
                            self.assertTrue(has_audio(key,item))
                            self.assertIn(str(n),direct_target(key,item,i)["facets"]["numbers"])
                            sig = identity(key.rsplit("-v",1)[0],item,i)
                            self.assertNotIn(sig,signatures)
                            signatures.add(sig)
                            if key=="more-v1":
                                a,b = item["piles"]
                                self.assertNotEqual(a,b)
                                self.assertEqual(item["answer"],"left" if a>b else "right")
                            elif key=="harvest-v1":
                                self.assertLessEqual(item["carrots"],12)
                                self.assertEqual(item["carrots"] % item["rabbits"],0)
                            else:
                                self.assertEqual(item["answer"],str(n))
        self.child.focuses.create(name="Eight",config={"numbers":["8"],"mode":"only"})
        preview = self.client.get(reverse("preview",args=[self.child.pk,"more-v1",1]))
        self.assertContains(preview, "pile with 8")
        counts = preview.context["item"]["piles"]
        self.assertEqual(preview.content.count(b'<i class="acorn"></i>'),sum(counts))

    def test_initials_bias_animals_without_letter_credit(self):
        from .focus import has_audio, lesson_weight
        config = {"letters":["M","S"],"context":85}
        self.child.focuses.create(name="Initials",config=config)
        key = "animal-lookout-v1"
        self.assertEqual(lesson_weight(key,[config]),0)
        for n in range(6):
            row = assign_lesson(self.child,key,n)
            items = assignment_lesson(row)["items"]
            self.assertGreaterEqual(sum(i["answer"][0].upper() in config["letters"] for i in items),4)
            self.assertEqual(len({i["answer"] for i in items}), len(items))
            for step,item in enumerate(items):
                self.assertIn(item["answer"],[a["name"] for a in item["animals"]])
                self.assertTrue(has_audio(key,item))
                self.assertEqual(direct_target(key,item,step)["facets"],{"animals":[item["answer"]]})
        base = build_round(key,0)
        for c in ({"letters":["M"],"context":0},{"letters":["Q"],"context":85}):
            self.assertEqual(compile_round(key,0,None,{"theme":"garden","configs":[c]}),base)

    def test_context_catalog_and_preserved_activities(self):
        from .focus import CONTEXT_SLOTS, TARGETS, has_audio
        from .focus_context import EXAMPLE_GROUPS, LINKED_GROUPS
        from .question_sets import identity
        fixed = set("lines river arrow-maze water-works train-tracks light-paths bridges delivery-routes gears-motion gates-switches number-check key-check sound-check".split())
        config = {"letters":["M","S"],"numbers":["3","4","5"],"colors":["red"],
                  "shapes":["triangle"],"interests":["space"],"context":85}
        for key in CURRENT_LESSONS:
            group = key.rsplit("-v",1)[0]
            with self.subTest(key=key):
                result = compile_round(key,2,None,{"theme":"garden","configs":[config]})
                if group in fixed:
                    self.assertEqual(result,build_round(key,2))
                else:
                    self.assertTrue(objectives(key)[0] in TARGETS or group in EXAMPLE_GROUPS
                                    | LINKED_GROUPS | CONTEXT_SLOTS | {"pattern","ladybugs","blend"})
                signatures = set()
                for step,item in enumerate(result["items"]):
                    self.assertTrue(has_audio(key,item))
                    sig = identity(group,item,step)
                    self.assertNotIn(sig,signatures)
                    signatures.add(sig)
