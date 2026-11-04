/* Shared helpers for the Settings Hub pages (Company Settings Hub, Roles &
 * Permissions). Extracted so both pages use one copy instead of duplicating
 * the same toast + AJAX-save pattern. Requires SweetAlert2 (Swal) to already
 * be loaded on the page, and a #csrf-token-holder element (or pass csrfToken
 * explicitly to hubPost) providing the CSRF token. */

function hubShowSuccess(msg) {
  Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: msg, showConfirmButton: false, timer: 2500 });
}

function hubShowError(msg) {
  Swal.fire({ toast: true, position: 'top-end', icon: 'error', title: msg, showConfirmButton: false, timer: 3500 });
}

/**
 * POST formData to url, toggling a spinner on btn and showing a success/error
 * toast based on the JSON response's {success, message/error} shape used
 * throughout this app's settings endpoints. Returns the parsed response data
 * (or null on a network-level failure) so callers can act on extra fields.
 */
async function hubPost(url, formData, btn, csrfToken) {
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Saving…';
  let data = null;
  try {
    const token = csrfToken || document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    formData.set('csrfmiddlewaretoken', token);
    const res = await fetch(url, { method: 'POST', body: formData, headers: { 'X-CSRFToken': token } });

    // These come back as HTML, not JSON, so they have to be recognised
    // before parsing -- otherwise res.json() throws and every one of them
    // surfaces as "Server error. Please try again.", which tells the user
    // to retry something that will never succeed.
    if (res.status === 403) {
      hubShowError("You don't have permission to do that. This action needs the Super Admin or Admin role.");
      return null;
    }
    if (res.status === 401) {
      hubShowError('Your session has expired. Please sign in again.');
      return null;
    }
    if (res.redirected) {
      hubShowError('You were signed out or redirected. Please reload the page and sign in again.');
      return null;
    }

    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      hubShowError(`Unexpected response from the server (HTTP ${res.status}).`);
      return null;
    }

    data = await res.json();
    if (data.success) hubShowSuccess(data.message || 'Saved!');
    else hubShowError(data.error || 'Failed to save.');
  } catch (e) {
    console.error(e);
    hubShowError('Could not reach the server. Check your connection and try again.');
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
  return data;
}
