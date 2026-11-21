"""Grid coordinates are shared by the outline, the brush and the feedback measures."""
WIDTH, HEIGHT = 32, 24


def inside(shape, x, y):
    if shape == "leaf":
        return abs(y-11.5+(x-15.5)*0.28) <= 7*(1-((x-15.5)/13)**2)
    if shape == "apple":
        return ((x-15.5)/9)**2 + ((y-13)/8)**2 <= 1 or (16 <= x <= 17 and 3 <= y <= 7)
    if shape == "kite":
        return abs(x-15.5)/11 + abs(y-11.5)/10 < 1
    if shape == "butterfly":
        return ((x-9)/5)**2+((y-8)/5)**2 <= 1 or ((x-12)/4)**2+((y-16)/4)**2 <= 1
    if shape == "pine":
        return (4 <= y <= 18 and abs(x-15.5) <= (y-3)*0.63) or (14 <= x <= 17 and 18 <= y <= 21)
    if shape == "heart":
        return (x-11)**2+(y-8)**2 <= 16 or (8 <= y < 21 and abs(x-15.5) <= (21-y)*0.68)
    if shape == "wheels":
        return any(5 <= (x-c)**2+(y-16)**2 <= 11 for c in (8,23))
    if shape == "eyes":
        return (x in (12,19) and y in (9,10))
    if shape == "stem":
        return x == 16 and 11 <= y <= 21
    raise ValueError(shape)


def art_item(item):
    return dict(item, palette=["Red","Gold","Green","Blue","Plum","Eraser"], mask="".join("1" if inside(item["shape"], x, y) else "0"
                for y in range(HEIGHT) for x in range(WIDTH)))


def evaluate(kind, mask, pixels):
    if len(pixels) != WIDTH*HEIGHT or set(pixels) - set("012345"):
        return None
    marks = {i for i, c in enumerate(pixels) if c != "0"}
    if not marks:
        return None
    target = {i for i, c in enumerate(mask) if c == "1"}
    if kind == "mirror":
        if any(i % WIDTH < WIDTH//2 for i in marks):
            return None
        reflected = {i-i%WIDTH + WIDTH-1-i%WIDTH for i in target if i%WIDTH < WIDTH//2}
        score = round(100*len(marks & reflected)/len(marks | reflected))
        return f"Mirror match: {score}% of the combined shape overlaps."
    if kind == "color":
        covered = round(100*len(marks & target)/len(target))
        outside = round(100*len(marks-target)/len(marks))
        return f"Shape filled: {covered}%. Color outside the outline: {outside}% of painted space."
    return "Finished an original drawing."


def match_score(kind, mask, pixels):
    marks = {i for i, value in enumerate(pixels) if value != "0"}
    target = {i for i, value in enumerate(mask) if value == "1"}
    if kind == "mirror":
        target = {i-i%WIDTH + WIDTH-1-i%WIDTH for i in target if i%WIDTH < WIDTH//2}
    return round(100*len(marks & target)/len(marks | target))
