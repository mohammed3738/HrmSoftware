/* Field Duty: location, live selfie, punch.
 *
 * Both buttons on the page funnel into one capture flow, because both ends
 * of a duty need the same three things -- the server's clock, the device's
 * coordinates and a photo taken now.
 *
 * The camera is the only source of the photo. There is no file input
 * anywhere in this flow by design -- see templates/field_duty/_capture_modal.html.
 *
 * Nothing here is trusted by the server. The timestamps are the server's
 * own, and views_field_duty.py re-validates the coordinates and decodes the
 * image rather than believing its content type. This file's job is to make
 * the capture work and to say something useful when it cannot.
 *
 * Permissions
 * -----------
 * Asking is the normal case, and it is driven by the button: every open of
 * the modal, and every press of Allow, calls getUserMedia /
 * getCurrentPosition again. Those calls *are* the prompt -- there is no
 * separate "ask" API -- so a dismissed prompt or a mis-tap is always one
 * press away from being asked again.
 *
 * What the Permissions API adds is only the ability to tell three states
 * apart, so the page does not lie to the employee:
 *
 *   granted -> use it, no prompt, nothing to say;
 *   prompt  -> ask now; the browser puts up its own dialog;
 *   denied  -> the browser will NOT prompt again, however many times it is
 *              asked. Telling somebody to "try again" here would be a loop
 *              with no exit, so the row says where the switch is instead --
 *              and still offers the button, because the moment they flip it
 *              the retry works.
 *
 * The API is advisory: Safari does not implement it for the camera, and the
 * whole thing is absent on older browsers. So it only ever decides what to
 * *say*; the request itself is made regardless, and a browser that would
 * have prompted still prompts.
 */
(function () {
  "use strict";

  var config = readJson("field-duty-config", {});
  var reportActivities = readJson("field-duty-report-activities", []);

  var modalEl = document.getElementById("fieldDutyCaptureModal");
  if (!modalEl) {
    return;
  }

  var video = document.getElementById("field-duty-video");
  var preview = document.getElementById("field-duty-preview");
  var canvas = document.getElementById("field-duty-canvas");
  var captureBtn = document.getElementById("field-duty-capture-btn");
  var retakeBtn = document.getElementById("field-duty-retake-btn");
  var submitBtn = document.getElementById("field-duty-submit-btn");
  var errorBox = document.getElementById("field-duty-capture-error");
  var hint = document.getElementById("field-duty-capture-hint");
  var titleEl = document.getElementById("fieldDutyCaptureTitle");
  var statusList = document.getElementById("field-duty-capture-status");

  // The longest side a selfie is uploaded at. A 12-megapixel phone photo is
  // several megabytes of evidence nobody will ever zoom into; 720px is
  // plenty to recognise a face and keeps the upload working on a weak
  // mobile signal, which is where this page is actually used.
  var MAX_SELFIE_PX = 720;
  var JPEG_QUALITY = 0.8;

  // Where the switch is, when a permission has been refused outright.
  var UNBLOCK_HELP =
    "Tap the padlock (or ⓘ) next to the web address, turn this on for this " +
    "site, then press Allow again.";

  var state = {
    mode: null,        // "start" or "end"
    stream: null,
    location: null,
    blob: null,
    busy: false
  };

  // -- small helpers -------------------------------------------------------

  function readJson(id, fallback) {
    var el = document.getElementById(id);
    if (!el) {
      return fallback;
    }
    try {
      return JSON.parse(el.textContent);
    } catch (err) {
      return fallback;
    }
  }

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function stepRow(name) {
    return statusList && statusList.querySelector('[data-step="' + name + '"]');
  }

  /* One row of the checklist.
   *
   * `state` is "pending", "ok" or "error". `help` is the second line, used
   * for the how-to-unblock sentence. `retryLabel` draws the button; leaving
   * it out hides it, which is what "ok" and "pending" want.
   */
  function setStep(name, stepState, text, help, retryLabel) {
    var row = stepRow(name);
    if (!row) {
      return;
    }
    var icon = row.querySelector("i");
    var label = row.querySelector("[data-step-text]");
    var helpEl = row.querySelector("[data-step-help]");
    var button = row.querySelector("[data-step-retry]");

    if (icon) {
      icon.className = {
        ok: "ri-checkbox-circle-fill text-success mt-1",
        error: "ri-error-warning-fill text-danger mt-1",
        pending: "ri-loader-4-line mt-1"
      }[stepState] || "ri-loader-4-line mt-1";
    }
    if (label && text) {
      label.textContent = text;
    }
    if (helpEl) {
      helpEl.textContent = help || "";
      helpEl.classList.toggle("d-none", !help);
    }
    if (button) {
      button.textContent = retryLabel || "Allow";
      button.classList.toggle("d-none", !retryLabel);
      button.disabled = false;
    }
  }

  function showError(message) {
    if (!errorBox) {
      return;
    }
    errorBox.textContent = message;
    errorBox.classList.remove("d-none");
  }

  function clearError() {
    if (errorBox) {
      errorBox.textContent = "";
      errorBox.classList.add("d-none");
    }
  }

  function stopStream() {
    if (state.stream) {
      state.stream.getTracks().forEach(function (track) {
        track.stop();
      });
      state.stream = null;
    }
    if (video) {
      video.srcObject = null;
    }
  }

  /* The browser's own view of a permission: "granted", "prompt", "denied"
   * or "unknown" when it will not say. Never throws -- Safari rejects an
   * unsupported name, and Firefox has no "camera" descriptor at all.
   */
  function permissionState(name) {
    if (!navigator.permissions || !navigator.permissions.query) {
      return Promise.resolve("unknown");
    }
    try {
      return navigator.permissions
        .query({ name: name })
        .then(function (status) {
          watchPermission(name, status);
          return status.state;
        })
        .catch(function () {
          return "unknown";
        });
    } catch (err) {
      return Promise.resolve("unknown");
    }
  }

  // Granting a permission in site settings does not reload the page, so
  // without this the employee would turn it on and still be looking at the
  // refusal. One listener per descriptor, for the life of the page.
  var watched = {};

  function watchPermission(name, status) {
    if (watched[name]) {
      return;
    }
    watched[name] = true;
    status.onchange = function () {
      if (status.state !== "granted") {
        return;
      }
      if (name === "camera" && !state.stream && !state.blob) {
        requestCamera();
      }
      if (name === "geolocation" && !state.location) {
        requestLocation();
      }
    };
  }

  // -- location ------------------------------------------------------------

  function requestLocation() {
    state.location = null;
    refreshButtons();

    if (!navigator.geolocation) {
      setStep("location", "error", "This browser cannot report a location.",
              "A field duty punch records where you are. Use the phone's own " +
              "browser (Chrome or Safari).");
      return;
    }

    setStep("location", "pending", "Getting your location…");

    permissionState("geolocation").then(function (permission) {
      if (permission === "denied") {
        // Asking again would not raise a prompt, so say where the switch is
        // -- but still offer the button, because it works the moment the
        // switch is flipped.
        setStep("location", "error", "Location is blocked for this site.",
                UNBLOCK_HELP, "Allow");
        return;
      }
      // This call is the prompt, when the state is "prompt".
      navigator.geolocation.getCurrentPosition(onPosition, onPositionError, {
        // No cached fix: the point of the coordinates is where the employee
        // is standing now, and a cached one could be this morning's office.
        enableHighAccuracy: true, timeout: 20000, maximumAge: 0
      });
    });
  }

  function onPosition(position) {
    state.location = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracy: position.coords.accuracy
    };
    var metres = Math.round(position.coords.accuracy || 0);
    setStep("location", "ok",
            "Location captured (accurate to about " + metres + " m).");
    refreshButtons();
  }

  function onPositionError(err) {
    if (err && err.code === 1) {
      setStep("location", "error", "Location permission was refused.",
              UNBLOCK_HELP + " A field duty punch records where you are.",
              "Allow");
    } else if (err && err.code === 3) {
      setStep("location", "error", "Could not get a location fix in time.",
              "Step outside or near a window, turn on GPS / Location, then " +
              "press Try again.", "Try again");
    } else {
      setStep("location", "error", "Could not get your location.",
              "Turn on GPS / Location, then press Try again.", "Try again");
    }
    refreshButtons();
  }

  // -- camera --------------------------------------------------------------

  function requestCamera() {
    stopStream();
    refreshButtons();

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStep("camera", "error", "This browser cannot use the camera.",
              window.isSecureContext
                ? "Use the phone's own browser (Chrome or Safari)."
                : "");
      if (!window.isSecureContext) {
        showError(
          "The camera and location only work over a secure (https) " +
          "connection. Open this page using the https address and try again."
        );
      }
      return;
    }

    setStep("camera", "pending", "Starting the camera…");

    permissionState("camera").then(function (permission) {
      if (permission === "denied") {
        setStep("camera", "error", "The camera is blocked for this site.",
                UNBLOCK_HELP, "Allow");
        return;
      }
      navigator.mediaDevices
        // facingMode "user" asks for the front camera; it is a preference,
        // not a guarantee, and a laptop with one camera simply uses that.
        .getUserMedia({ video: { facingMode: "user" }, audio: false })
        .then(onStream)
        .catch(onCameraError);
    });
  }

  function onStream(stream) {
    state.stream = stream;
    video.srcObject = stream;
    setStep("camera", "ok", "Camera ready.");
    refreshButtons();
  }

  function onCameraError(err) {
    var name = err && err.name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      setStep("camera", "error", "Camera permission was refused.",
              UNBLOCK_HELP + " A field duty punch records a selfie.", "Allow");
    } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      setStep("camera", "error", "No camera was found on this device.",
              "Use a phone to punch field duty.");
    } else if (name === "NotReadableError" || name === "TrackStartError") {
      setStep("camera", "error", "The camera is in use by another app.",
              "Close the other app, then press Try again.", "Try again");
    } else {
      setStep("camera", "error", "Could not start the camera.",
              "Close any other app using it, then press Try again.",
              "Try again");
    }
    refreshButtons();
  }

  // -- capture -------------------------------------------------------------

  function capture() {
    if (!video.videoWidth) {
      showError("The camera has not started yet. Wait a moment and tap Capture again.");
      return;
    }

    var scale = Math.min(1, MAX_SELFIE_PX / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      function (blob) {
        if (!blob) {
          showError("Could not save the photo. Tap Capture again.");
          return;
        }
        state.blob = blob;
        preview.src = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
        preview.classList.remove("d-none");
        video.classList.add("d-none");
        stopStream();  // the photo is taken; stop holding the camera open
        setStep("camera", "ok", "Photo taken.");
        if (hint) {
          hint.textContent = "Happy with it? Confirm to punch. Otherwise retake.";
        }
        refreshButtons();
      },
      "image/jpeg",
      JPEG_QUALITY
    );
  }

  function retake() {
    state.blob = null;
    preview.classList.add("d-none");
    preview.removeAttribute("src");
    video.classList.remove("d-none");
    if (hint) {
      hint.textContent = "Hold the phone at arm's length so your face is in frame, then tap Capture.";
    }
    clearError();
    requestCamera();
    refreshButtons();
  }

  function refreshButtons() {
    var taken = Boolean(state.blob);
    captureBtn.classList.toggle("d-none", taken);
    captureBtn.disabled = !state.stream || state.busy;
    retakeBtn.classList.toggle("d-none", !taken);
    submitBtn.classList.toggle("d-none", !taken);
    // Both pieces of evidence or nothing: the server refuses a punch
    // missing either, so there is no point letting it be sent.
    submitBtn.disabled = !taken || !state.location || state.busy;
  }

  // -- submit --------------------------------------------------------------

  function submit() {
    if (state.busy) {
      return;
    }
    clearError();

    var data = new FormData();
    data.append("latitude", state.location.latitude);
    data.append("longitude", state.location.longitude);
    if (state.location.accuracy != null) {
      data.append("accuracy", state.location.accuracy);
    }
    data.append("selfie", state.blob, "selfie.jpg");

    if (state.mode === "start") {
      data.append("activity", valueOf("field-duty-activity"));
      data.append("purpose", valueOf("field-duty-purpose"));
      data.append("notes", valueOf("field-duty-notes"));
    }

    var url = state.mode === "start" ? config.startUrl : config.endUrl;
    setBusy(true, state.mode === "start" ? "Starting…" : "Ending…");

    fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
      body: data,
      credentials: "same-origin"
    })
      .then(readPayload)
      .then(function (payload) {
        if (!payload.success) {
          setBusy(false);
          showError(payload.error || "The punch was not recorded. Try again.");
          return;
        }
        // The server is the only source of truth for what the punch did to
        // the day's attendance, so reload rather than patch the page by hand.
        sessionStorage.setItem(
          "fieldDutyFlash",
          [payload.message, payload.attendance_note].filter(Boolean).join(" ")
        );
        window.location.reload();
      })
      .catch(function () {
        setBusy(false);
        showError(
          "Could not reach the server. Check your signal and try again -- " +
          "nothing has been recorded yet."
        );
      });
  }

  function readPayload(response) {
    return response
      .json()
      .catch(function () {
        return { success: false, error: "The server returned an unexpected response (" + response.status + ")." };
      })
      .then(function (payload) {
        if (!response.ok && payload.success === undefined) {
          payload.success = false;
        }
        return payload;
      });
  }

  function setBusy(busy, label) {
    state.busy = busy;
    var span = submitBtn.querySelector("[data-submit-label]");
    if (span && label) {
      span.textContent = label;
    }
    refreshButtons();
  }

  function valueOf(id) {
    var el = document.getElementById(id);
    return el ? el.value : "";
  }

  // -- opening and closing -------------------------------------------------

  function openFor(mode) {
    state.mode = mode;
    state.blob = null;
    state.location = null;
    state.busy = false;
    clearError();

    preview.classList.add("d-none");
    preview.removeAttribute("src");
    video.classList.remove("d-none");

    if (titleEl) {
      titleEl.textContent = mode === "start" ? "Start field duty" : "End field duty";
    }
    if (hint) {
      hint.textContent = "Hold the phone at arm's length so your face is in frame, then tap Capture.";
    }
    var span = submitBtn.querySelector("[data-submit-label]");
    if (span) {
      span.textContent = mode === "start" ? "Confirm & Start" : "Confirm & End";
    }
    submitBtn.className = mode === "start"
      ? "btn btn-success flex-grow-1"
      : "btn btn-danger flex-grow-1";

    refreshButtons();

    var modal = window.bootstrap
      ? window.bootstrap.Modal.getOrCreateInstance(modalEl)
      : null;
    if (modal) {
      modal.show();
    }

    // Asked on every open, so a permission granted since last time is just
    // used, and one that was dismissed is asked for again. The camera goes
    // first and the location follows once it has settled: some mobile
    // browsers drop the second of two prompts raised at the same moment.
    requestCamera();
    window.setTimeout(requestLocation, 400);
  }

  // -- wiring --------------------------------------------------------------

  document.querySelectorAll("[data-field-duty-action]").forEach(function (button) {
    button.addEventListener("click", function () {
      openFor(button.getAttribute("data-field-duty-action"));
    });
  });

  // Each row asks again for its own permission. Independent on purpose: a
  // working camera is not re-requested because the location failed.
  if (statusList) {
    statusList.querySelectorAll("[data-step-retry]").forEach(function (button) {
      button.addEventListener("click", function () {
        var row = button.closest("[data-step]");
        var name = row && row.getAttribute("data-step");
        button.disabled = true;
        clearError();
        if (name === "camera") {
          requestCamera();
        } else if (name === "location") {
          requestLocation();
        }
      });
    });
  }

  captureBtn.addEventListener("click", capture);
  retakeBtn.addEventListener("click", retake);
  submitBtn.addEventListener("click", submit);

  // Never leave the camera running behind a closed modal.
  modalEl.addEventListener("hidden.bs.modal", stopStream);
  window.addEventListener("pagehide", stopStream);

  // The report upload forms post JSON back, so they are sent from here
  // rather than navigating to a page of raw JSON.
  document.querySelectorAll("[data-field-duty-report-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type=submit]");
      if (button) {
        button.disabled = true;
      }
      fetch(form.action, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
        body: new FormData(form),
        credentials: "same-origin"
      })
        .then(readPayload)
        .then(function (payload) {
          if (!payload.success) {
            if (button) {
              button.disabled = false;
            }
            window.alert(payload.error || "The upload failed.");
            return;
          }
          sessionStorage.setItem("fieldDutyFlash", payload.message || "");
          window.location.reload();
        })
        .catch(function () {
          if (button) {
            button.disabled = false;
          }
          window.alert("Could not reach the server. Check your signal and try again.");
        });
    });
  });

  // Which activities need a report is the server's list, so the hint on the
  // page cannot drift from what actually happens on End Field Duty.
  var activitySelect = document.getElementById("field-duty-activity");
  var reportHint = document.getElementById("field-duty-report-hint");
  if (activitySelect && reportHint) {
    var defaultHint = reportHint.innerHTML;
    activitySelect.addEventListener("change", function () {
      if (reportActivities.indexOf(activitySelect.value) === -1) {
        reportHint.textContent =
          "This closes as soon as you tap End Field Duty -- no report needed.";
      } else {
        reportHint.innerHTML = defaultHint;
      }
    });
  }

  // "Started 2h 15m ago", ticking, so an open duty does not look stale.
  document.querySelectorAll("[data-elapsed-since]").forEach(function (el) {
    var since = new Date(el.getAttribute("data-elapsed-since"));
    if (isNaN(since.getTime())) {
      return;
    }
    function tick() {
      var minutes = Math.max(0, Math.floor((Date.now() - since.getTime()) / 60000));
      var hours = Math.floor(minutes / 60);
      el.textContent = "· " + (hours ? hours + "h " : "") + (minutes % 60) + "m ago";
    }
    tick();
    window.setInterval(tick, 30000);
  });

  // Whatever the last punch did, said once after the reload.
  var flash = sessionStorage.getItem("fieldDutyFlash");
  if (flash) {
    sessionStorage.removeItem("fieldDutyFlash");
    var banner = document.createElement("div");
    banner.className = "alert alert-success alert-dismissible";
    banner.setAttribute("role", "status");
    banner.textContent = flash;
    var close = document.createElement("button");
    close.type = "button";
    close.className = "btn-close";
    close.setAttribute("data-bs-dismiss", "alert");
    close.setAttribute("aria-label", "Close");
    banner.appendChild(close);
    var container = document.querySelector(".container-xxl.container-p-y");
    if (container) {
      container.insertBefore(banner, container.firstChild);
    }
  }
})();
