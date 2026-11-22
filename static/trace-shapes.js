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
    W: "M35 30L64 120L98 61L134 120L162 30", Z: "M55 25H145L55 125H145",
    N: "M60 125V25L140 125V25", 3: "M60 38Q155 -5 122 65L94 75Q165 80 125 118Q95 140 60 119",
    4: "M128 125V26L61 93H150", 7: "M55 27H147L85 126",
    river: "M22 112 Q70 12 114 66 T180 38", stream: "M24 25 C180 12 180 65 104 75 S30 130 178 122",
    line: "M28 75H172", hill: "M24 110Q100 -16 176 110",
    L: "M74 25V125H134", V: "M55 25L100 125L145 25",
    O: "M100 22C33 22 33 128 100 128C167 128 167 22 100 22",
    1: "M76 48L102 24V126", 2: "M58 49C67 0 162 18 132 65L59 125H146"
  };

// The child and mirror use the same stroke boundaries, including lifts for dots and crossbars.
function traceStrokes(svg) {
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
