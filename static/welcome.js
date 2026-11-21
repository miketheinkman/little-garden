const replay = document.querySelector("#replay");
replay.hidden = false;
replay.addEventListener("click", () => {
  document.querySelector(".meadow-scene").getAnimations({subtree: true}).forEach(animation => {
    animation.currentTime = 0;
    animation.play();
  });
});
