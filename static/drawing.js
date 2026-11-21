const artColors = ["#fffdf5", "#d44e43", "#e9a92d", "#539653", "#437aaf", "#925485"];
const columns = 32, rows = 24, cell = 20;

function renderPicture(board, pixels, cursor) {
  const ctx = board.getContext("2d");
  const {kind, mask} = board.dataset;
  ctx.fillStyle = artColors[0];
  ctx.fillRect(0, 0, board.width, board.height);
  for (let i = 0; i < pixels.length; i++) {
    const x = i % columns, y = Math.floor(i / columns);
    const guide = mask[i] === "1" && (kind !== "mirror" || x < columns / 2);
    ctx.fillStyle = Number(pixels[i]) ? artColors[pixels[i]] :
      guide ? (kind === "color" ? "#e0e8d6" : "#536e64") : artColors[0];
    ctx.fillRect(x * cell, y * cell, cell, cell);
  }
  if (kind === "color") {
    ctx.strokeStyle = "#405e48";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < mask.length; i++) {
      if (mask[i] !== "1") continue;
      const x = (i % columns) * cell, y = Math.floor(i / columns) * cell;
      for (const [neighbor, ax, ay, bx, by] of [
        [i-1,x,y,x,y+cell], [i+1,x+cell,y,x+cell,y+cell],
        [i-columns,x,y,x+cell,y], [i+columns,x,y+cell,x+cell,y+cell]
      ]) {
        if (mask[neighbor] !== "1") { ctx.moveTo(ax,ay); ctx.lineTo(bx,by); }
      }
    }
    ctx.stroke();
  }
  if (kind === "mirror") {
    ctx.save(); ctx.strokeStyle = "#314a3f"; ctx.setLineDash([8,6]);
    ctx.beginPath(); ctx.moveTo(board.width/2,0); ctx.lineTo(board.width/2,board.height); ctx.stroke(); ctx.restore();
  }
  if (cursor) {
    ctx.strokeStyle = "#161616"; ctx.lineWidth = 3;
    ctx.strokeRect(cursor.x*cell+2,cursor.y*cell+2,cell-4,cell-4);
  }
}

function startDrawing(board) {
  let pixels = Array(columns*rows).fill(0);
  const cursor = {x:16,y:12};
  let pointer = null, previous, color = 1, keyboard = false;
  const history = [];
  const field = document.querySelector("#pixels");
  const undo = document.querySelector("#undo");
  const finish = document.querySelector("#finish-art");
  function refresh() {
    field.value = pixels.join("");
    finish.disabled = !pixels.some(Boolean);
    undo.disabled = !history.length;
    renderPicture(board,pixels,keyboard ? cursor : null);
  }
  function remember() {
    history.push(pixels.slice());
    if (history.length > 40) history.shift();
  }
  function paint(x,y) {
    const radius = (Number(document.querySelector("#brush").value)-1)/2;
    for (let dy=-radius; dy<=radius; dy++) for (let dx=-radius; dx<=radius; dx++) {
      const px=x+dx, py=y+dy;
      if (px<0 || px>=columns || py<0 || py>=rows || dx*dx+dy*dy>radius*radius) continue;
      if (board.dataset.kind === "mirror" && px<columns/2) continue;
      pixels[py*columns+px]=color;
    }
  }
  function stroke(event) {
    const rect=board.getBoundingClientRect();
    const x=Math.floor((event.clientX-rect.left)*columns/rect.width);
    const y=Math.floor((event.clientY-rect.top)*rows/rect.height);
    if (x<0 || y<0 || x>=columns || y>=rows) { previous=null; return; }
    const from=previous || {x,y};
    const steps=Math.max(1,Math.abs(x-from.x),Math.abs(y-from.y));
    for (let i=1; i<=steps; i++) paint(Math.round(from.x+(x-from.x)*i/steps),Math.round(from.y+(y-from.y)*i/steps));
    previous={x,y}; refresh();
  }
  board.onpointerdown = event => {
    if (pointer !== null || event.button !== 0) return;
    keyboard=false; previous=null; pointer=event.pointerId; remember();
    board.setPointerCapture(pointer); stroke(event);
  };
  board.onpointermove = event => { if (event.pointerId===pointer) stroke(event); };
  board.onlostpointercapture = () => { pointer=null; };
  board.onfocus=()=>{keyboard=true;refresh();};
  board.onblur=()=>{keyboard=false;refresh();};
  board.onkeydown = event => {
    const moves={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
    if (event.key!==" " && !moves[event.key]) return;
    event.preventDefault(); keyboard=true;
    if (event.key===" ") { remember(); paint(cursor.x,cursor.y); }
    else {
      const [dx,dy]=moves[event.key];
      cursor.x=Math.max(board.dataset.kind==="mirror"?16:0,Math.min(columns-1,cursor.x+dx));
      cursor.y=Math.max(0,Math.min(rows-1,cursor.y+dy));
    }
    refresh();
  };
  undo.onclick=()=>{ if(history.length) pixels=history.pop(); refresh(); };
  const tools=document.querySelectorAll("[data-color]");
  tools.forEach(button=>{
    const value=Number(button.dataset.color)%6;
    button.style.borderBottom="5px solid "+artColors[value];
    button.onclick=()=>{
      color=value;
      tools.forEach(other=>other.setAttribute("aria-pressed",String(button===other)));
    };
  });
  refresh();
}

document.querySelectorAll(".saved-art").forEach(board=>renderPicture(board,board.dataset.pixels,null));
const artBoard=document.querySelector("#board");
if(artBoard) startDrawing(artBoard);
