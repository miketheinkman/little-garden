(() => {
  const app = document.querySelector("#device-launch");
  const form = document.querySelector("#device-pair");
  const status = document.querySelector("#device-status");
  const retry = document.querySelector("#device-retry");
  const install = document.querySelector("#install-garden");
  if ("serviceWorker" in navigator) {
    // Garden access still works as a regular page if app installation is unavailable.
    navigator.serviceWorker.register(app.dataset.worker).catch(() => {});
  }
  let db;
  function result(req) {
    return new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function keys(create) {
    if (!window.isSecureContext || !crypto.subtle || !window.indexedDB)
      throw Error("Open this shortcut over HTTPS in a browser that supports device keys.");
    if (!db) {
      const open = indexedDB.open("little-garden-devices", 1);
      open.onupgradeneeded = () => open.result.createObjectStore("keys");
      db = await result(open);
    }
    const id = app.dataset.device;
    let pair = await result(db.transaction("keys").objectStore("keys").get(id));
    if (!pair && create) {
      const generated = await crypto.subtle.generateKey({name:"ECDSA", namedCurve:"P-256"}, false, ["sign","verify"]);
      const tx = db.transaction("keys", "readwrite");
      const store = tx.objectStore("keys");
      // Recheck inside the write transaction in case another tab just paired.
      const read = store.get(id);
      read.onsuccess = () => {
        pair = read.result || generated;
        if (!read.result) store.add(pair, id);
      };
      await new Promise((resolve,reject) => { tx.oncomplete = resolve; tx.onabort = () => reject(tx.error); });
    }
    if (!pair) throw Error("This browser does not have the device key. Open the original shortcut or ask your parent to connect this installation.");
    return pair;
  }
  async function saveCertificate(pair, certificate) {
    pair.certificate = certificate;
    const tx = db.transaction("keys","readwrite");
    tx.objectStore("keys").put(pair,app.dataset.device);
    await new Promise((resolve,reject) => { tx.oncomplete = resolve; tx.onabort = () => reject(tx.error); });
  }
  async function post(url, fields) {
    const response = await fetch(url, {method:"POST",body:new URLSearchParams(fields),
      headers:{"X-CSRFToken":form.elements.csrfmiddlewaretoken.value},cache:"no-store"});
    if (response.status === 404) throw Error("This garden access has expired or was removed.");
    const data = await response.json();
    if (!response.ok) throw Error(data.error || "Unable to connect. Open the shortcut again.");
    return data;
  }
  const encode = buffer => btoa(String.fromCharCode(...new Uint8Array(buffer)));
  async function launch(code) {
    retry.hidden = true;
    const submit = form.querySelector("button:not([type])");
    submit.disabled = true;
    try {
      const pair = await keys(Boolean(code));
      if (code) {
        const pub = await crypto.subtle.exportKey("raw", pair.publicKey);
        const issued = await post(app.dataset.pair,{code,public_key:encode(pub)});
        form.hidden = true;
        await saveCertificate(pair,issued.certificate);
      }
      const {challenge,certificate} = await post(app.dataset.prove,pair.certificate ? {} : {recover_certificate:"1"});
      if (certificate) await saveCertificate(pair,certificate);
      const proof = await crypto.subtle.sign({name:"ECDSA", hash:"SHA-256"},pair.privateKey,new TextEncoder().encode(challenge));
      const {garden} = await post(app.dataset.prove,{challenge,certificate:pair.certificate,signature:encode(proof)});
      location.replace(garden);
    } catch (error) {
      status.textContent = error.message || "Unable to open your garden.";
      retry.hidden = !form.hidden;
    } finally { submit.disabled = false; }
  }
  window.addEventListener("beforeinstallprompt", e => {
    e.preventDefault();
    install.hidden = false;
    install.onclick = async () => { await e.prompt(); install.hidden = true; };
  });
  form.addEventListener("submit", e => { e.preventDefault(); launch(form.elements.code.value.trim()); });
  retry.onclick = () => location.reload();
  if (form.hidden) launch();
})();
