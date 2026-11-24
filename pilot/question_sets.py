"""Identify a problem by what the child must do, independently of option order."""
import re


def identity(group, item, index):
    answer = item["answer"]
    if group in {"keys","number-keys","my-letters","case-match","alphabet-gap","count1","count2","shift",
                 "letters","lowercase","digits","five","ten","twos","coins","clock","berry-basket","measure",
                 "backspace","sentence","magic-e","signs","hear-number","money-id","name-paint","match-paint","mix-paint"}:
        return answer.casefold()
    if "equation" in item:
        a, op, b = item["equation"].split()
        return (op, *sorted((a,b))) if op == "+" else (op,a,b)
    if group == "market":
        words = {"one":"1","two":"2","three":"3","four":"4","five":"5"}
        operands = re.findall(r"\b(?:\d+|one|two|three|four|five)\b", item["prompt"].lower())
        return tuple(sorted(words.get(n,n) for n in operands)), answer
    if group == "ladybugs":
        return item.get("x",index), item.get("y")
    if group in {"lines","river"}:
        return item.get("path", answer)
    if "carrots" in item:
        return item["carrots"], item["rabbits"]
    if "word" in item:
        return item["word"]
    if "maze" in item:
        return item["maze"]
    if "sides" in item:
        return answer, item["sides"][int(answer == "right")]["label"]
    if "piles" in item:
        return tuple(sorted(item["piles"]))
    if "board" in item:
        return item["board"]["name"]
    if "deck" in item:
        return tuple(sorted((c["label"], c.get("symbol",""), c.get("clip","")) for c in item["deck"]))
    if "blocks" in item:
        return item["target"], tuple(sorted(c["weight"] for c in item["blocks"]))
    if "handful" in item:
        return tuple(sorted(c["cents"] for c in item["handful"]))
    if "faces" in item:
        return item["sample"], tuple(sorted(item["faces"]))
    if "pieces" in item:
        return tuple(sorted((p["name"],p.get("color","")) for p in item["pieces"])), item["prompt"]
    if "dots" in item:
        return item["outline"]
    if "variants" in item or group == "living":
        return item["specimen"], answer
    # Linked passages, investigations, and check-ins have different instructions
    # for different steps, even when they use the same chart or physical props.
    return item["prompt"], item.get("display",""), answer
