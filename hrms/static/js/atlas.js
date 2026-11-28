(() => {
  "use strict";

  document.querySelectorAll(".dashboard-avatar img, img[data-avatar-fallback]").forEach(photo => {
    function recoverPhoto() {
      if (photo.dataset.avatarFallback) {
        photo.src = photo.dataset.avatarFallback;
      } else {
        photo.hidden = true;
      }
    }
    if (photo.complete && !photo.naturalWidth) recoverPhoto();
    else photo.addEventListener("error", recoverPhoto, { once: true });
  });

  const nav = document.querySelector("#atlas-nav");
  const toggle = document.querySelector(".atlas-nav-trigger");
  const groups = [...nav.querySelectorAll("details")];
  const links = [...nav.querySelectorAll("a[href]")];
  const matches = links.filter(link => link.pathname === location.pathname);
  const query = new URLSearchParams(location.search);
  const current = matches.find(link => link.search &&
    [...new URLSearchParams(link.search)].every(([key, value]) => query.get(key) === value))
    || matches.find(link => !link.search);
  current?.setAttribute("aria-current", "page");
  const parentLink = current || links.find(link => link.dataset.routes?.split(" ").includes(nav.dataset.route));
  const currentGroup = nav.querySelector(".current-module") || parentLink?.closest("details");
  currentGroup?.classList.add("current-module");

  function closeNav() {
    groups.forEach(group => { group.open = false; });
    nav.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open navigation");
  }
  toggle.addEventListener("click", () => {
    if (nav.classList.contains("is-open")) closeNav();
    else {
      nav.classList.add("is-open");
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Close navigation");
      if (currentGroup) currentGroup.open = true;
    }
  });
  nav.addEventListener("click", event => {
    const group = event.target.closest("summary")?.parentElement;
    if (group) groups.filter(other => !other.contains(group)).forEach(other => { other.open = false; });
  });
  nav.addEventListener("focusout", event => {
    if (event.relatedTarget && !nav.contains(event.relatedTarget) && event.relatedTarget !== toggle) closeNav();
  });
  document.addEventListener("click", event => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) closeNav();
  });

  const palette = document.querySelector(".atlas-palette");
  const input = document.querySelector("#atlas-query");
  const results = document.querySelector("#atlas-results");
  const people = document.querySelector("#atlas-people");
  const status = document.querySelector("#atlas-empty");
  let timer;
  let lookup;

  function stopLookup() {
    clearTimeout(timer);
    lookup?.abort();
  }
  async function searchEmployees(query, signal) {
    try {
      const url = new URL(palette.dataset.employeeSearch, location.href);
      url.searchParams.set("q", query);
      const response = await fetch(url, {signal});
      if (!response.ok) throw new Error("Search unavailable");
      const employees = await response.json();
      if (signal.aborted) return;
      for (const employee of employees) {
        const link = document.createElement("a");
        link.href = palette.dataset.employeeDetail.replace(/\/0\/$/, "/" + employee.id + "/");
        link.textContent = [employee.name, employee.code].filter(Boolean).join(" · ");
        const item = document.createElement("li");
        item.append(link);
        people.append(item);
      }
      status.textContent = "No matches.";
      status.hidden = !!(results.childElementCount || people.childElementCount);
    } catch (error) {
      if (signal.aborted) return;
      status.textContent = "Employee search is unavailable. Try again.";
      status.hidden = false;
    }
  }
  const workspaceLinks = document.querySelector("#workspace-search").content.querySelectorAll("a");
  function filterPages() {
    stopLookup();
    people.replaceChildren();
    const query = input.value.trim().toLowerCase();
    const items = [];
    for (const link of [...links, ...workspaceLinks]) {
      const group = link.dataset.section || link.closest("details")?.querySelector("summary")?.textContent || "";
      if (!(link.textContent + " " + group).toLowerCase().includes(query)) continue;
      const item = document.createElement("li");
      const result = document.createElement("a");
      result.href = link.href;
      result.textContent = link.textContent;
      if (group) {
        const moduleName = document.createElement("small");
        moduleName.textContent = group;
        result.append(moduleName);
      }
      item.append(result);
      items.push(item);
    }
    results.replaceChildren(...items);
    status.textContent = "No matches.";
    status.hidden = items.length > 0;
    if (palette.dataset.employeeSearch && query.length >= 2) {
      status.textContent = "Searching employees…";
      status.hidden = false;
      lookup = new AbortController();
      timer = setTimeout(() => searchEmployees(query, lookup.signal), 180);
    }
  }
  const shortcut = document.querySelector(".search-shortcut");
  if (shortcut) {
    shortcut.textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? "\u2318 K" : "Ctrl K";
    shortcut.hidden = false;
  }
  function openSearch() {
    closeNav();
    input.value = "";
    filterPages();
    if (!palette.open) palette.showModal();
    input.focus();
  }
  document.querySelector(".atlas-search-trigger").addEventListener("click", openSearch);
  input.addEventListener("input", filterPages);
  palette.addEventListener("close", stopLookup);
  input.addEventListener("keydown", event => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      palette.querySelector("li a")?.focus();
    }
  });
  palette.addEventListener("keydown", event => {
    const link = event.target.closest("li a");
    if (!link || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const choices = [...palette.querySelectorAll("li a")];
    const next = choices.indexOf(link) + (event.key === "ArrowUp" ? -1 : 1);
    (next < 0 ? input : choices[Math.min(next, choices.length - 1)]).focus();
  });
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openSearch();
    }
    if (event.key !== "Escape" || palette.open) return;
    const group = document.activeElement.closest("details[open]");
    if (group && nav.contains(group)) {
      group.open = false;
      group.querySelector("summary").focus();
    } else if (nav.classList.contains("is-open")) {
      closeNav();
      toggle.focus();
    }
  });
})();

(() => {
  const options = document.querySelector("[data-dashboard-key]");
  if (!options) return;
  const key = options.dataset.dashboardKey;
  let hidden = new Set();
  try { hidden = new Set(JSON.parse(localStorage.getItem(key) || "[]")); } catch {}
  options.querySelectorAll("[data-widget]").forEach(input => {
    const id = input.dataset.widget;
    const card = document.getElementById("widget-" + id);
    input.checked = !hidden.has(id);
    card.hidden = !input.checked;
    input.addEventListener("change", () => {
      card.hidden = !input.checked;
      if (input.checked) hidden.delete(id);
      else hidden.add(id);
      try { localStorage.setItem(key, JSON.stringify([...hidden])); } catch {}
    });
  });
})();
