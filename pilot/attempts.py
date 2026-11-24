"""Parent-readable evidence from submitted lesson answers."""
from itertools import groupby

from .assessment import evidence_method
from .models import QuestionAttempt

Outcome = QuestionAttempt.Outcome


def descriptions(item, lesson, data, method):
    prompt = item["prompt"]
    for field in ("word", "equation", "scene_alt"):
        context = item.get(field)
        if isinstance(context, str) and context.casefold() not in prompt.casefold():
            prompt += " · " + context
    expected = str(item.get("answer", "")) if method == "answer" else ""
    response = data.get("answer", "") if method == "answer" else ""
    tool = lesson.get("tool")
    selections = data.get("tool_state", "")[:150].split(",")
    if tool == "balance":
        blocks = {str(i): str(block["weight"]) for i, block in enumerate(item["blocks"])}
        weights = [blocks[i] for i in selections if i in blocks]
        response = " + ".join(weights) if weights else "Empty pan"
    elif tool == "sort":
        bins = {str(i): b["label"] if isinstance(b, dict) else b for i, b in enumerate(item["bins"], 1)}
        def baskets(indices):
            return ", ".join(f'{p["name"]} → {bins.get(i, "unplaced")}' for p, i in zip(item["pieces"], indices))
        response = baskets(selections)
        expected = baskets(str(p["bin"]) for p in item["pieces"])
    elif tool == "paint-mix":
        paints = {str(i): paint["name"] for i, paint in enumerate(item["paints"])}
        response = " + ".join(paints[i] for i in selections if i in paints)
    elif tool == "dots":
        expected = " → ".join(str(dot["label"]) for dot in item["dots"])
        response = "Out of sequence" if response == "retry" else ""
    elif item.get("faces"):
        faces = {str(i): str(face) for i, face in enumerate(item["faces"])}
        response, expected = faces.get(response, response), faces.get(expected, expected)
    return prompt[:600], expected[:300], response[:300]


def record_attempt(row, item, lesson, data, *, submission, method, accepted, skip, advanced, score, pace, help_used):
    if skip:
        outcome = Outcome.SKIPPED
    elif method in {"answer", "puzzle"}:
        outcome = Outcome.CORRECT if accepted else Outcome.INCORRECT
    else:
        outcome = Outcome.COMPLETED if accepted else Outcome.RETRY
    prompt, expected, response = descriptions(item, lesson, data, method)
    QuestionAttempt.objects.create(assignment=row, step=row.step, outcome=outcome, advanced=advanced, submission=submission,
                                   prompt=prompt, expected=expected, response="" if skip else response,
                                   score=score if method == "art" and accepted else None,
                                   ms_per_key=pace, help_used=help_used)


def populate_history(row):
    attempts = list(row.question_attempts.all())
    # Older assignments can contain only aggregate counts, including part of a current round.
    earlier_steps = row.step - sum(a.advanced for a in attempts)
    earlier_errors = row.retries - sum(a.outcome in {Outcome.INCORRECT, Outcome.RETRY} for a in attempts)
    row.earlier_history = earlier_steps > 0 or earlier_errors > 0
    row.correct_attempts = sum(a.outcome == Outcome.CORRECT for a in attempts)
    row.incorrect_attempts = sum(a.outcome == Outcome.INCORRECT for a in attempts)
    row.answered_questions = row.answered
    row.question_details = []
    row.first_try_correct = 0
    row.first_try_total = 0
    samples = {s.step: s for s in row.samples.all()}
    for step, entries in groupby(attempts, key=lambda a: a.step):
        entries = list(entries)
        first = entries[0]
        samples.pop(step, None)
        if first.outcome in {Outcome.CORRECT, Outcome.INCORRECT}:
            row.first_try_total += 1
            row.first_try_correct += int(first.outcome == Outcome.CORRECT)
        for attempt in entries:
            if attempt.ms_per_key:
                attempt.seconds_per_key = attempt.ms_per_key / 1000
        if not any(a.advanced and a.outcome != Outcome.SKIPPED for a in entries) and any(a.outcome != Outcome.SKIPPED for a in entries):
            row.answered_questions += 1
        row.question_details.append({"number": step + 1, "prompt": first.prompt, "expected": first.expected, "attempts": entries})
    for step, sample in samples.items():
        method = evidence_method(row.info)
        items = row.info["items"]
        label = f"Recorded score {sample.score}%"
        if method == "answer":
            label = "First answer correct" if sample.score == 100 else "First answer incorrect"
        row.question_details.append({"number": step + 1, "prompt": items[step]["prompt"] if step < len(items) else "",
                                     "earlier": label})
    row.question_details.sort(key=lambda q: q["number"])
    row.has_recorded_attempts = bool(attempts)
    row.graded_answers = evidence_method(row.info) in {"answer", "puzzle"}
