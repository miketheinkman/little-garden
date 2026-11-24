"""How each playable lesson can provide placement or review evidence."""


def evidence_method(lesson):
    kind = lesson["kind"]
    if lesson["participation"] == "Parent required" or kind in {"mouse", "adult", "trace", "draw", "memory"} or lesson.get("tool") == "maze":
        return "observation"
    if kind in {"color", "mirror"}:
        return "art"
    if kind == "puzzle":
        return "puzzle"
    if kind in {"choice", "type", "key", "basket", "balance"}:
        return "answer"
    raise ValueError(f"Choose an evidence method for {lesson['title']}")


METHODS = {
    "answer": "First submitted answers",
    "art": "Drawing overlap",
    "puzzle": "Independent puzzle solves",
    "observation": "Parent observation",
}


def observation_prompt(lesson):
    if lesson.get("tool") == "maze":
        return "Watch how the child changes direction at a turn and finds a way around a blocked path."
    if lesson["kind"] == "memory":
        return "Watch whether the child remembers a matching card’s location after it turns over."
    if lesson["kind"] == "trace":
        return "Watch where the child starts, follows the path and changes direction."
    if lesson["kind"] == "draw":
        return "Ask the child to describe a choice they made in their picture."
    if lesson["kind"] == "mouse":
        return "Watch how the child moves to a new target and selects it."
    return "Record what the child tried independently and which part needed a prompt."


def submitted_response(data, lesson, item):
    """A check advances after an actual choice, including an incorrect one."""
    tool = lesson.get("tool")
    fields = data.get("tool_state", "").split(",")
    if tool == "sort":
        return len(fields) == len(item["pieces"]) and all(v in {str(i+1) for i in range(len(item["bins"]))} for v in fields)
    if tool == "balance":
        return len(fields) == len(set(fields)) and all(v in {str(i) for i in range(len(item["blocks"]))} for v in fields)
    if tool == "paint-mix":
        return len(fields) == 2 and all(v in {str(i) for i in range(len(item["paints"]))} for v in fields)
    if tool == "dots":
        # A tap out of sequence is a real attempt. The finish button sends the full path.
        return data.get("answer") == "retry" or data.get("tool_state") == item["answer"]
    return bool(data.get("answer", "").strip())
