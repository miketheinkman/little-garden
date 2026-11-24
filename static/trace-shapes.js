const traceShapes = {
    // Lowercase letters share a baseline at 116 and an x-height at 66.
    l: "M100 26V116", c: "M121 73C98 51 71 77 79 103Q88 125 120 109",
    o: "M116 73C98 55 77 68 77 92C77 123 119 125 121 95Q123 80 116 73",
    v: "M74 66L99 116L126 66", w: "M56 66L77 116L99 73L121 116L143 66",
    s: "M120 72C96 53 65 77 98 89C142 102 111 129 77 110",
    u: "M77 66V96Q77 129 101 111Q118 100 118 66V116",
    e: "M77 91H122C122 57 79 56 77 90C74 117 101 125 123 109",
    a: "M118 73C93 51 72 77 79 103C88 128 117 116 118 88V67V116",
    b: "M81 26V116V89C84 66 107 58 119 78C139 112 100 129 82 107",
    d: "M116 73C90 51 68 81 80 106C93 128 117 113 117 89V26V116",
    f: ["M122 32Q100 14 95 47V116", "M76 68H116"],
    g: "M117 72C87 50 68 86 83 105C96 123 118 107 118 85V68V121Q117 148 86 136",
    h: "M80 26V116V82Q91 58 109 68Q121 73 121 89V116",
    i: ["M100 67V116", "M100 47v0.5"],
    j: ["M108 67V122Q108 147 84 136", "M108 47v0.5"],
    k: ["M82 26V116", "M120 66L83 91L122 116"],
    m: "M57 66V116V84Q68 60 81 68Q90 72 90 89V116V84Q103 59 116 68Q128 73 128 91V116",
    n: "M80 66V116V83Q93 59 108 69Q120 74 120 90V116",
    p: "M81 66V141V88C86 63 110 59 122 79C137 106 108 130 82 107",
    q: "M117 73C87 50 68 85 81 105C96 128 117 108 118 87V66V140",
    r: "M84 66V116V87Q93 61 119 68",
    t: ["M98 37V99Q98 121 118 113", "M78 67H119"],
    x: ["M76 66L123 116", "M123 66L76 116"],
    y: "M74 66L101 115L126 66L94 140",
    z: "M78 66H123L78 116H124",
    A: ["M52 124L100 25L148 124","M74 82H126"],
    B: ["M65 25V124","M65 25H99C146 25 149 73 99 73H65","M65 73H102C153 73 150 124 100 124H65"],
    C: "M143 43C91 -4 49 45 54 88C59 127 112 144 144 108",
    D: ["M64 25V125","M64 25H86C166 25 166 125 86 125H64"],
    E: ["M66 25V124H142","M66 25H142","M66 72H128"],
    F: ["M67 25V125","M67 25H143","M67 71H128"],
    G: "M142 43C102 6 56 29 55 76C55 124 111 145 145 111V78H110",
    H: ["M62 25V124","M138 25V124","M62 72H138"],
    I: ["M100 25V124","M72 25H128","M72 124H128"],
    J: ["M126 25V97Q125 147 64 111","M93 25H148"],
    K: ["M65 25V124","M139 25L69 77L142 124"],
    M: "M48 124V25L100 88L152 25V124",
    P: ["M67 25V124","M67 25H103C155 25 153 78 103 78H67"],
    Q: ["M100 22C35 22 35 124 100 124C165 124 165 22 100 22","M113 94L148 132"],
    R: ["M64 25V124","M64 25H104C154 25 151 76 104 76H64","M101 76L147 124"],
    S: "M139 39C109 7 53 24 62 55C70 81 132 69 139 99C146 132 83 143 56 112",
    T: ["M53 25H147","M100 25V125"], U: "M60 25V88C60 139 140 139 140 88V25",
    X: ["M59 25L142 125","M141 25L58 125"], Y: ["M54 25L100 75L146 25","M100 75V125"],
    0: "M99 24C48 24 48 125 99 125C150 125 150 24 99 24",
    5: ["M131 26H71V71C99 52 143 68 136 101C128 135 82 135 61 113"],
    6: "M125 23C89 34 62 73 65 98C69 134 131 138 135 98C138 63 92 54 66 87",
    8: "M100 72C45 52 77 10 112 25C149 39 125 61 100 72C52 91 62 128 100 127C143 128 153 88 100 72",
    9: "M131 69C113 96 65 86 64 55C63 19 127 9 134 48C139 78 116 109 87 128",
    W: "M35 30L64 120L98 61L134 120L162 30", Z: "M55 25H145L55 125H145",
    N: "M60 125V25L140 125V25", 3: "M60 38Q155 -5 122 65L94 75Q165 80 125 118Q95 140 60 119",
    4: "M128 125V26L61 93H150", 7: "M55 27H147L85 126",
    river: "M22 112 Q70 12 114 66 T180 38", stream: "M24 25 C180 12 180 65 104 75 S30 130 178 122",
    line: "M28 75H172", hill: "M24 110Q100 -16 176 110",
    L: "M74 25V125H134", V: "M55 25L100 125L145 25",
    O: "M100 22C33 22 33 128 100 128C167 128 167 22 100 22",
    1: "M76 48L102 24V126", 2: "M58 49C67 0 162 18 132 65L59 125H146"
  };

// Two-digit numerals use separate strokes so a child can lift between digits.
const tensDigits = {
  "1": "M36 49L58 26V124",
  "2": "M22 49C30 9 95 23 82 57Q76 75 22 124H86"
};
const unitsDigits = [
  "M149 24C105 24 105 125 149 125C193 125 193 24 149 24",
  "M123 49L149 25V124",
  "M118 49C126 8 189 22 179 55Q175 73 118 124H183",
  "M118 39Q183 5 175 53Q171 70 144 75Q192 79 175 111Q153 139 117 117",
  "M167 125V26L116 93H184",
  "M178 26H122V68C154 52 187 72 177 102C168 132 138 133 117 114",
  "M171 25C135 38 111 78 120 106C132 140 182 128 180 97C177 67 140 61 120 88",
  "M116 27H184L140 125",
  "M149 72C103 51 131 9 161 26C188 43 171 63 149 72C107 90 118 128 148 126C187 128 192 91 149 72",
  "M177 69C154 95 113 82 118 51C125 14 171 14 179 47C185 76 164 112 133 127"
];
function paintTraceLights(root, percent) {
  root.querySelectorAll(".trace-lights span").forEach((light, i) => light.classList.toggle("lit", percent >= (i+1)*20));
}

// The child and mirror use the same stroke boundaries, including lifts for dots and crossbars.
function traceStrokes(svg) {
  const digits = svg.dataset.shape;
  if (/^(1[0-9]|20)$/.test(digits)) return [tensDigits[digits[0]], unitsDigits[Number(digits[1])]];
  const shape = svg.dataset.path || traceShapes[svg.dataset.shape];
  return Array.isArray(shape) ? shape : [shape];
}

function setTraceStroke(svg, strokes, index) {
  if (svg.dataset.stroke === String(index)) return;
  svg.dataset.stroke = index;
  const guide = svg.querySelector("#guide, .live-guide");
  const ink = svg.querySelector("#ink, .live-ink");
  if (strokes.length > 1) {
    let outline = svg.querySelector(".trace-outline");
    let finished = svg.querySelector(".trace-finished");
    if (!outline) {
      outline = document.createElementNS(svg.namespaceURI, "path");
      finished = document.createElementNS(svg.namespaceURI, "path");
      outline.setAttribute("class", "trace-outline");
      finished.setAttribute("class", "trace-finished");
      guide.before(outline, finished);
      outline.setAttribute("d", strokes.join(" "));
    }
    finished.setAttribute("d", strokes.slice(0, index).join(" "));
  }
  guide.setAttribute("d", strokes[index]);
  ink.setAttribute("d", strokes[index]);
}
