// Keep the learner's live connection while replacing the server-rendered lesson.
const activityScript = 'script[src*="/activity.js?"]';
const loadedActivity = document.querySelector(activityScript)?.getAttribute("src");
let learnerRequest;
async function openLearnerPage(url, options = {}) {
  learnerRequest?.abort();
  const request = new AbortController();
  learnerRequest = request;
  const response = await fetch(url, {...options, signal: request.signal, cache: "no-store"});
  if (!response.ok) throw new Error("Could not load lesson");
  const next = new DOMParser().parseFromString(await response.text(), "text/html");
  if (request.signal.aborted) return;
  const badge = next.querySelector("#live-presence");
  // A new release may need different controls than the scripts already running in this tab.
  const nextActivity = next.querySelector(activityScript)?.getAttribute("src");
  if (!badge || nextActivity !== loadedActivity || badge.dataset.url !== document.querySelector("#live-presence").dataset.url) {
    location.assign(response.url);
    return;
  }
  const main = next.querySelector("main");
  main.querySelectorAll("script").forEach(script => script.remove());
  document.querySelector("main").replaceWith(main);
  if (response.url !== location.href) history.pushState(null, "", response.url);
  startLesson();
  const board = main.querySelector("#board");
  if (board) startDrawing(board);
  document.dispatchEvent(new Event("garden-screen"));
  const heading = main.querySelector("#prompt") || main.querySelector("h1");
  if (heading) {
    heading.tabIndex = -1;
    heading.focus({preventScroll: true});
  }
  window.scrollTo(0, 0);
}

document.addEventListener("click", event => {
  const link = event.target.closest('a[data-learner-link]');
  if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
      event.shiftKey || event.altKey) return;
  event.preventDefault();
  openLearnerPage(link.href).catch(error => {
    if (error.name !== "AbortError") location.assign(link.href);
  });
});

document.addEventListener("submit", event => {
  const form = event.target;
  if (!form.matches('form[data-start-suggestion]')) return;
  event.preventDefault();
  if (form.inert) return;
  const data = new FormData(form, event.submitter);
  form.inert = true;
  openLearnerPage(form.action, {method: "POST", body: data}).catch(error => {
    if (error.name !== "AbortError") location.assign("/");
  });
});

window.addEventListener("popstate", () => {
  openLearnerPage(location.href).catch(error => {
    if (error.name !== "AbortError") location.reload();
  });
});
