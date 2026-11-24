(() => {
  const toggle = document.querySelector("[data-password-toggle]");
  const password = document.getElementById(toggle.getAttribute("aria-controls"));

  function setVisible(visible) {
    const {selectionStart, selectionEnd, selectionDirection} = password;
    password.type = visible ? "text" : "password";
    if (selectionStart !== null) password.setSelectionRange(selectionStart, selectionEnd, selectionDirection);
    toggle.textContent = visible ? "Hide password" : "Show password";
  }

  toggle.hidden = false;
  toggle.addEventListener("pointerdown", event => {
    // Keep the caret and the mobile keyboard in place while checking a typed password.
    if (document.activeElement === password && event.button === 0) event.preventDefault();
  });
  toggle.addEventListener("click", () => setVisible(password.type === "password"));
  password.form.addEventListener("submit", () => setVisible(false));
  window.addEventListener("pagehide", () => setVisible(false));
})();
