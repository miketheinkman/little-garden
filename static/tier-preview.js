(() => {
  const stage = document.querySelector(".tier-preview");
  const replay = document.getElementById("replay-climb");

  function play() {
    stage.replaceChildren(gardenAnswerNote("correct", 0, {tier: 3, strand: "Number sense"}));
  }

  replay.addEventListener("click", play);
  replay.hidden = false;
  play();
})();
