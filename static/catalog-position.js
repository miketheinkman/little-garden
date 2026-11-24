// Keep the bookmark with this preview, including when it opens in another tab.
(() => {
  const shelf = document.getElementById("available-lessons");
  const tierKey = document.querySelector(".tier-key");
  const cards = () => [...shelf.querySelectorAll("[data-lesson]")];

  function bookmark(event) {
    const link = event.target.closest("a[data-preview]");
    if (!link) return;
    const card = link.closest("article");
    const offset = Math.round(card.getBoundingClientRect().top);
    const position = [cards().indexOf(card), offset, Number(tierKey.open)].join(":");
    const url = new URL(link.href);
    url.searchParams.set("catalog", position);
    link.href = url;
    if (event.type === "click" && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
      history.replaceState({...history.state, previewBookmark: {id: card.id, position}}, "");
    }
  }
  shelf.addEventListener("pointerdown", bookmark);
  shelf.addEventListener("click", bookmark); // Includes keyboard activation.

  window.addEventListener("pageshow", event => {
    // The library refreshes a cached library to pick up newly assigned lessons.
    if (event.persisted) return;
    const url = new URL(location.href);
    const saved = history.state?.previewBookmark;
    const position = url.searchParams.get("catalog") || saved?.position || "";
    const match = /^(\d{1,5}):(-?\d{1,7}):([01])$/.exec(position);
    if (!match) return;
    const id = url.searchParams.has("catalog") ? url.hash.slice(1) : saved.id;
    requestAnimationFrame(() => {
      tierKey.open = match[3] === "1";
      const remaining = cards();
      const card = remaining.find(item => item.id === id) || remaining[Math.min(Number(match[1]), remaining.length - 1)];
      const target = card || shelf.querySelector("[data-empty]");
      (card?.querySelector("[data-preview]") || target).focus({preventScroll: true});
      window.scrollBy({top: target.getBoundingClientRect().top - Number(match[2]), behavior: "instant"});
      const state = {...history.state};
      delete state.previewBookmark;
      if (url.searchParams.has("catalog")) {
        url.searchParams.delete("catalog");
        url.hash = "";
      }
      history.replaceState(state, "", url);
    });
  });
})();
