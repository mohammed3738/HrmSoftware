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
    data = await res.json();
    if (data.success) hubShowSuccess(data.message || 'Saved!');
    else hubShowError(data.error || 'Failed to save.');
  } catch (e) {
    console.error(e);
    hubShowError('Server error. Please try again.');
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
  return data;
}
