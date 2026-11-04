/*
 * Employee type-ahead, shared by every employee picker in the app.
 *
 * Backed by /ajax/employees/search/ (website.views.employee_search), which
 * scopes results to the viewer's company.
 *
 *   wireEmployeeAutocomplete('inputId', 'dropdownId', onSelect, options)
 *
 * onSelect receives {id, name, code, department, status}.
 *
 * options:
 *   clearOnSelect  true  -- blank the box after choosing. Right for a
 *                           picker that adds the employee to a list below
 *                           it (the shift roster), wrong for a filter box
 *                           where the chosen name should stay visible.
 *   minChars       1     -- how much to type before asking the server.
 *   submitOnSelect false -- submit the input's form after choosing, for a
 *                           filter that takes effect immediately.
 *   filter         null  -- predicate(employee) -> keep?  For a picker that
 *                           builds a list, so names already on the list stop
 *                           being offered again.
 *
 * Marked up as:
 *   <input type="text" id="x" autocomplete="off">
 *   <ul id="xDropdown" class="list-group position-absolute w-100"
 *       style="z-index:1000; display:none; max-height:260px; overflow-y:auto;"></ul>
 * inside a position-relative parent.
 */
(function () {
  "use strict";

  var SEARCH_URL = "/ajax/employees/search/";

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  window.wireEmployeeAutocomplete = function (inputId, dropdownId, onSelect, options) {
    var input = document.getElementById(inputId);
    var dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return null;      // page does not have this picker

    var opts = options || {};
    var clearOnSelect = opts.clearOnSelect !== false;   // default true
    var minChars = opts.minChars || 1;
    var submitOnSelect = opts.submitOnSelect === true;
    var filter = typeof opts.filter === "function" ? opts.filter : null;

    var controller = null;
    var debounce = null;
    var rows = [];
    var active = -1;

    function close() {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
      rows = [];
      active = -1;
    }

    function highlight() {
      for (var i = 0; i < rows.length; i++) {
        rows[i].classList.toggle("active", i === active);
      }
      if (active >= 0 && rows[active]) {
        // Keep the keyboard selection inside a scrolled dropdown.
        var row = rows[active];
        if (row.offsetTop < dropdown.scrollTop) {
          dropdown.scrollTop = row.offsetTop;
        } else if (row.offsetTop + row.offsetHeight > dropdown.scrollTop + dropdown.clientHeight) {
          dropdown.scrollTop = row.offsetTop + row.offsetHeight - dropdown.clientHeight;
        }
      }
    }

    function choose(employee) {
      close();
      if (clearOnSelect) {
        input.value = "";
      } else {
        input.value = employee.code
          ? employee.name + " (" + employee.code + ")"
          : employee.name;
      }
      if (typeof onSelect === "function") onSelect(employee);
      if (submitOnSelect && input.form) input.form.submit();
    }

    function render(data) {
      if (filter) data = data.filter(filter);
      dropdown.innerHTML = "";
      rows = [];
      active = -1;

      if (!data.length) {
        dropdown.innerHTML =
          '<li class="list-group-item text-muted small">No employees found</li>';
        dropdown.style.display = "block";
        return;
      }

      data.forEach(function (employee) {
        var li = document.createElement("li");
        li.className = "list-group-item list-group-item-action py-2";
        li.style.cursor = "pointer";
        var meta = [];
        if (employee.code) meta.push(escapeHtml(employee.code));
        if (employee.department) meta.push(escapeHtml(employee.department));
        // Somebody who has left is still findable -- their old attendance and
        // payroll are still looked at -- but say so, so nobody picks them by
        // accident.
        var left = employee.status && employee.status !== "Active"
          ? ' <span class="badge bg-label-secondary ms-1">' +
            escapeHtml(employee.status) + "</span>"
          : "";
        li.innerHTML =
          "<strong>" + escapeHtml(employee.name) + "</strong>" + left +
          (meta.length ? ' <small class="text-muted ms-1">' + meta.join(" &middot; ") + "</small>" : "");
        li.addEventListener("mousedown", function (event) {
          // mousedown, not click: blur would close the dropdown first.
          event.preventDefault();
          choose(employee);
        });
        li.addEventListener("mouseenter", function () {
          active = rows.indexOf(li);
          highlight();
        });
        dropdown.appendChild(li);
        rows.push(li);
      });
      dropdown.style.display = "block";
    }

    function search() {
      var query = input.value.trim();
      if (query.length < minChars) { close(); return; }
      if (controller) controller.abort();
      controller = new AbortController();
      fetch(SEARCH_URL + "?q=" + encodeURIComponent(query), { signal: controller.signal })
        .then(function (res) { return res.json(); })
        .then(render)
        .catch(function (err) {
          if (err.name !== "AbortError") {
            console.error("Employee search failed", err);
            close();
          }
        });
    }

    input.setAttribute("autocomplete", "off");

    input.addEventListener("input", function () {
      // A short debounce: typing a six-character code otherwise fires six
      // requests, and aborting them still costs the round trips.
      clearTimeout(debounce);
      debounce = setTimeout(search, 180);
    });

    input.addEventListener("keydown", function (event) {
      if (dropdown.style.display === "none" || !rows.length) {
        if (event.key === "ArrowDown") search();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        active = (active + 1) % rows.length;
        highlight();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        active = active <= 0 ? rows.length - 1 : active - 1;
        highlight();
      } else if (event.key === "Enter") {
        if (active >= 0) {
          // Only swallow Enter when something is actually selected, so a
          // plain text search can still submit its form.
          event.preventDefault();
          rows[active].dispatchEvent(new MouseEvent("mousedown"));
        }
      } else if (event.key === "Escape") {
        close();
      }
    });

    input.addEventListener("blur", function () {
      // After mousedown has had its chance to fire.
      setTimeout(close, 150);
    });

    document.addEventListener("click", function (event) {
      if (event.target !== input && !dropdown.contains(event.target)) close();
    });

    return { search: search, close: close, input: input, dropdown: dropdown };
  };

  /*
   * A type-ahead that drives an existing <select name="employee">.
   *
   *   wireEmployeeSelectSearch('empSearch', 'empSearchDropdown', 'id_employee')
   *
   * The select stays the field that is submitted, so required-ness,
   * server-side validation and any change handlers already on it keep
   * working -- the box only picks the option. Only employees the select
   * actually offers are suggested: the search endpoint is scoped to the
   * company, but a form's own list is often narrower than that (active
   * employees, employees without a slip yet), and offering somebody the
   * form cannot accept would be a dead end.
   */
  window.wireEmployeeSelectSearch = function (inputId, dropdownId, selectId, options) {
    var select = document.getElementById(selectId);
    if (!select) return null;

    function optionFor(id) {
      return select.querySelector('option[value="' + String(id) + '"]');
    }

    var opts = options || {};
    opts.clearOnSelect = false;
    opts.filter = function (employee) { return !!optionFor(employee.id); };

    return window.wireEmployeeAutocomplete(inputId, dropdownId, function (employee) {
      var option = optionFor(employee.id);
      if (!option) return;
      select.value = option.value;
      // Pages hang salary lookups and totals off this event.
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }, opts);
  };
})();
