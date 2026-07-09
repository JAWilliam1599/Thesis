(() => {
  "use strict";

  const config = window.APP_CONFIG || {};
  const apiBase = (config.apiBaseUrl || "/prod").replace(/\/$/, "");
  const endpoint = `${apiBase}/guestbook`;

  const entriesEl = document.getElementById("entries");
  const statusEl = document.getElementById("status");
  const form = document.getElementById("entry-form");

  function setStatus(message, isError) {
    statusEl.textContent = message || "";
    statusEl.classList.toggle("error", Boolean(isError));
  }

  function render(entries) {
    entriesEl.innerHTML = "";
    if (!entries || entries.length === 0) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "No entries yet — be the first!";
      entriesEl.appendChild(li);
      return;
    }
    for (const entry of entries) {
      const li = document.createElement("li");
      const who = document.createElement("strong");
      who.textContent = entry.name;
      const when = document.createElement("time");
      when.textContent = new Date(entry.created_at).toLocaleString();
      const msg = document.createElement("p");
      msg.textContent = entry.message;
      li.append(who, when, msg);
      entriesEl.appendChild(li);
    }
  }

  async function loadEntries() {
    try {
      const res = await fetch(endpoint, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      render(data.entries);
    } catch (err) {
      entriesEl.innerHTML = "";
      const li = document.createElement("li");
      li.className = "muted error";
      li.textContent = `Could not load entries: ${err.message}`;
      entriesEl.appendChild(li);
    }
  }

  async function submitEntry(event) {
    event.preventDefault();
    const name = document.getElementById("name").value.trim();
    const message = document.getElementById("message").value.trim();
    if (!name || !message) {
      setStatus("Name and message are required.", true);
      return;
    }
    setStatus("Saving…", false);
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, message }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      form.reset();
      setStatus("Saved!", false);
      await loadEntries();
    } catch (err) {
      setStatus(`Failed to save: ${err.message}`, true);
    }
  }

  form.addEventListener("submit", submitEntry);
  loadEntries();
})();
