/**
 * Employee Form Manager
 * Handles both Create and Edit employee forms with dynamic formsets
 * Supports: Previous Employment, Attachments, and Nested Documents
 */

class EmployeeFormManager {
  constructor(formRoot) {
    if (!formRoot) {
      console.error('[EmployeeFormManager] No form root provided');
      return;
    }
    
    // Prevent double initialization
    if (formRoot._employeeFormInit) {
      console.debug('[EmployeeFormManager] Already initialized');
      return;
    }
    formRoot._employeeFormInit = true;

    this.root = formRoot;
    this.init();
  }

  init() {
    console.debug('[EmployeeFormManager] Initializing for:', this.root);
    this.initPreviousEmployment();
    this.initMainAttachments();
    this.initNestedAttachments();
  }

  // ============================================================
  // PREVIOUS EMPLOYMENT MANAGEMENT
  // ============================================================
  initPreviousEmployment() {
    const tbody = this.root.querySelector('#prevEmploymentTable tbody');
    const addBtn = this.root.querySelector('#addPrevRow');
    const template = this.root.querySelector('#prev-empty-row');
    const totalForms = this.root.querySelector('#id_previous_employments-TOTAL_FORMS');

    if (!addBtn || !tbody || !template || !totalForms) {
      console.debug('[EmployeeFormManager] Previous employment elements not found - skipping');
      return;
    }

    // Add new previous employment row
    addBtn.addEventListener('click', () => {
      const newIndex = parseInt(totalForms.value || '0', 10);
      const html = template.innerHTML.replace(/__prefix__/g, newIndex);
      
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = html;
      const newRow = tempDiv.querySelector('tr');
      
      // Update manage-documents button data-index
      const manageBtn = newRow.querySelector('.manage-documents');
      if (manageBtn) {
        manageBtn.setAttribute('data-index', newIndex);
      }
      
      tbody.appendChild(newRow);
      totalForms.value = newIndex + 1;
      
      // Ensure nested attachment placeholders exist for this new row
      this.ensureAttachmentPlaceholders(newIndex);
      
      console.debug(`[EmployeeFormManager] Added prev employment row ${newIndex}`);
    });

    // Remove previous employment row (event delegation)
    tbody.addEventListener('click', (e) => {
      const removeBtn = e.target.closest('.remove-prev-row');
      if (!removeBtn) return;
      
      const row = removeBtn.closest('tr');
      if (row) {
        row.remove();
        const currentTotal = parseInt(totalForms.value || '0', 10);
        totalForms.value = Math.max(0, currentTotal - 1);
        console.debug('[EmployeeFormManager] Removed prev employment row');
      }
    });
  }

  // ============================================================
  // MAIN EMPLOYEE ATTACHMENTS MANAGEMENT
  // ============================================================
  initMainAttachments() {
    const tbody = this.root.querySelector('#attachmentTable');
    const addBtn = this.root.querySelector('#addAttachmentRow');
    const template = this.root.querySelector('#attach-empty-row');
    const totalForms = this.root.querySelector('#id_attachments-TOTAL_FORMS');

    if (!addBtn || !tbody || !template || !totalForms) {
      console.debug('[EmployeeFormManager] Main attachments elements not found - skipping');
      return;
    }

    // Add new attachment row
    addBtn.addEventListener('click', () => {
      const index = parseInt(totalForms.value || '0', 10);
      const html = template.innerHTML.replace(/__prefix__/g, index);
      
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = html;
      const newRow = tempDiv.querySelector('tr');
      
      tbody.appendChild(newRow);
      totalForms.value = index + 1;
      
      console.debug(`[EmployeeFormManager] Added attachment row ${index}`);
    });

    // Remove attachment row (event delegation)
    tbody.addEventListener('click', (e) => {
      const removeBtn = e.target.closest('.remove-attachment-row');
      if (!removeBtn) return;
      
      const row = removeBtn.closest('tr');
      if (row) {
        row.remove();
        const currentTotal = parseInt(totalForms.value || '0', 10);
        totalForms.value = Math.max(0, currentTotal - 1);
        console.debug('[EmployeeFormManager] Removed attachment row');
      }
    });
  }

  // ============================================================
  // NESTED ATTACHMENTS (Previous Employment Documents)
  // ============================================================
  initNestedAttachments() {
    const nestedModal = document.getElementById('attachments_modal');
    const nestedContainer = document.getElementById('attachments_container');
    const nestedAddBtn = document.getElementById('add_attachment_btn');
    const nestedSaveBtn = document.getElementById('save_attachments_btn');
    const hiddenStorage = document.getElementById('hidden-nested-files');

    if (!nestedModal || !nestedContainer) {
      console.debug('[EmployeeFormManager] Nested attachments modal not found - skipping');
      return;
    }

    // Open nested attachments modal when "Manage Documents" clicked
    this.root.addEventListener('click', (e) => {
      const manageBtn = e.target.closest('.manage-documents');
      if (!manageBtn) return;

      const index = manageBtn.dataset.index;
      if (index === undefined) {
        console.error('[EmployeeFormManager] manage-documents button missing data-index');
        return;
      }

      console.debug(`[EmployeeFormManager] Opening nested attachments for row ${index}`);
      
      // Ensure placeholders exist
      this.ensureAttachmentPlaceholders(index);

      // Clear container
      nestedContainer.innerHTML = '';

      // Load existing server-rendered template if present
      const template = document.getElementById(`attachment-template-${index}`);
      if (template) {
        const existingRows = template.querySelectorAll('.attachment-row');
        existingRows.forEach(row => {
          nestedContainer.appendChild(row.cloneNode(true));
        });
      }

      // Also load any previously saved hidden-nested-files blocks
      if (hiddenStorage) {
        const savedRows = hiddenStorage.querySelectorAll(`[data-row="${index}"]`);
        savedRows.forEach(block => {
          nestedContainer.appendChild(block.cloneNode(true));
        });
      }

      // Store current index on modal and show it
      nestedModal.dataset.currentIndex = index;
      const modalInstance = new bootstrap.Modal(nestedModal);
      modalInstance.show();
    });

    // Add new document row in nested modal
    if (nestedAddBtn) {
      nestedAddBtn.addEventListener('click', () => {
        const index = nestedModal.dataset.currentIndex || '0';
        const emptyTemplate = document.getElementById(`empty-prevattach-${index}`) || 
                              document.getElementById('attachment-empty-template');
        
        if (emptyTemplate) {
          const html = emptyTemplate.innerHTML.replace(/__prefix__/g, Date.now());
          nestedContainer.insertAdjacentHTML('beforeend', html);
          console.debug('[EmployeeFormManager] Added nested document row');
        }
      });
    }

    // Save nested attachments to hidden storage
    if (nestedSaveBtn && hiddenStorage) {
      nestedSaveBtn.addEventListener('click', () => {
        const index = nestedModal.dataset.currentIndex || '0';
        
        // Remove existing entries for this index
        const existingBlocks = hiddenStorage.querySelectorAll(`[data-row="${index}"]`);
        existingBlocks.forEach(block => block.remove());

        // Collect all rows from the modal
        const rows = Array.from(nestedContainer.querySelectorAll('.attachment-row'));
        
        rows.forEach((row, i) => {
          const wrapper = document.createElement('div');
          wrapper.dataset.row = index;

          // Get file input
          const fileInput = row.querySelector('input[type="file"]');
          if (fileInput && fileInput.files.length > 0) {
            // Clone the file input with its files
            const clonedFileInput = fileInput.cloneNode(true);
            clonedFileInput.name = `attach-${index}-${i}-file`;
            wrapper.appendChild(clonedFileInput);
          }

          // Get document name
          const nameInput = row.querySelector('input[type="text"], input.attachment-name');
          const hiddenName = document.createElement('input');
          hiddenName.type = 'hidden';
          hiddenName.name = `attach-${index}-${i}-document_name`;
          hiddenName.value = nameInput ? (nameInput.value || '') : '';
          wrapper.appendChild(hiddenName);

          hiddenStorage.appendChild(wrapper);
        });

        console.debug(`[EmployeeFormManager] Saved ${rows.length} nested documents for row ${index}`);

        // Close modal
        const modalInstance = bootstrap.Modal.getInstance(nestedModal);
        if (modalInstance) modalInstance.hide();
      });
    }
  }

  // ============================================================
  // HELPER: Ensure Attachment Placeholders Exist
  // ============================================================
  ensureAttachmentPlaceholders(index) {
    // Create attachment-template-<index> if not present
    if (!document.getElementById(`attachment-template-${index}`)) {
      const div = document.createElement('div');
      div.style.display = 'none';
      div.id = `attachment-template-${index}`;
      div.innerHTML = `<div class="attachments-placeholder" id="attachments-wrapper-${index}"></div>`;
      document.body.appendChild(div);
      console.debug(`[EmployeeFormManager] Created attachment-template-${index}`);
    }

    // Create empty-prevattach-<index> if not present
    if (!document.getElementById(`empty-prevattach-${index}`)) {
      const sampleTemplate = document.querySelector('[id^="empty-prevattach-"]');
      
      if (sampleTemplate) {
        const clone = sampleTemplate.cloneNode(true);
        clone.id = `empty-prevattach-${index}`;
        clone.innerHTML = clone.innerHTML.replace(/attach-\d+-__prefix__/g, `attach-${index}-__prefix__`);
        document.body.appendChild(clone);
      } else {
        // Fallback: create basic template
        const fallback = document.createElement('div');
        fallback.style.display = 'none';
        fallback.id = `empty-prevattach-${index}`;
        fallback.innerHTML = `
          <div class="row mb-2 attachment-row">
            <div class="col-6">
              <input type="file" name="attach-${index}-__prefix__-file" class="form-control attachment-file" />
            </div>
            <div class="col-4">
              <input type="text" name="attach-${index}-__prefix__-document_name" class="form-control attachment-name" placeholder="Document Name" />
            </div>
            <div class="col-2">
              <button type="button" class="btn btn-danger btn-sm nested-remove-attachment">Remove</button>
            </div>
          </div>
        `;
        document.body.appendChild(fallback);
      }
      
      console.debug(`[EmployeeFormManager] Created empty-prevattach-${index}`);
    }
  }
}

// ============================================================
// GLOBAL: Remove nested attachment rows (event delegation)
// ============================================================
document.addEventListener('click', (e) => {
  const removeBtn = e.target.closest('.nested-remove-attachment, .remove-attachment');
  if (!removeBtn) return;
  
  const row = removeBtn.closest('.attachment-row');
  if (row) {
    row.remove();
    console.debug('[EmployeeFormManager] Removed nested attachment row');
  }
});

// ============================================================
// AUTO-INITIALIZE ON PAGE LOAD
// ============================================================
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeForms);
} else {
  initializeForms();
}

function initializeForms() {
  // Initialize create form if present
  const createForm = document.querySelector('#employeeCreateForm');
  if (createForm) {
    new EmployeeFormManager(createForm);
    console.debug('[EmployeeFormManager] Auto-initialized create form');
  }

  // Initialize edit form if present (for static edit pages)
  const editForm = document.querySelector('#employeeEditForm');
  if (editForm) {
    new EmployeeFormManager(editForm);
    console.debug('[EmployeeFormManager] Auto-initialized edit form');
  }
}

// ============================================================
// AJAX EDIT MODAL LOADER
// ============================================================
document.addEventListener('click', function(e) {
  const editBtn = e.target.closest('.edit-employee-btn');
  if (!editBtn) return;

  const employeeId = editBtn.dataset.id;
  const modalBody = document.getElementById('editEmployeeBody');
  
  if (!modalBody) {
    console.error('[EmployeeFormManager] editEmployeeBody not found');
    return;
  }

  modalBody.innerHTML = '<div class="text-center p-3 text-muted">Loading...</div>';

  fetch(`/employee/${employeeId}/edit/`)
    .then(resp => {
      if (!resp.ok) throw new Error('Failed to load edit form');
      return resp.text();
    })
    .then(html => {
      // Inject the HTML
      modalBody.innerHTML = html;
      
      // ✅ CRITICAL: Initialize the form BEFORE showing modal
      const editForm = modalBody.querySelector('#employeeEditForm');
      if (editForm) {
        new EmployeeFormManager(editForm);
        console.debug('[EmployeeFormManager] Initialized AJAX-loaded edit form');
      } else {
        console.warn('[EmployeeFormManager] No #employeeEditForm found in loaded HTML');
      }
      
      // Now show the modal
      const modalEl = document.getElementById('editEmployeeModal');
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    })
    .catch(err => {
      console.error('[EmployeeFormManager] Edit load error:', err);
      modalBody.innerHTML = '<div class="alert alert-danger">Failed to load form. Please try again.</div>';
    });
});

// ============================================================
// DELETE CONFIRMATION
// ============================================================
function confirmEmployeeDelete(employeeId) {
  Swal.fire({
    title: 'Are you sure?',
    text: 'This employee will be permanently deleted!',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonColor: '#d33',
    cancelButtonColor: '#3085d6',
    confirmButtonText: 'Yes, delete!'
  }).then((result) => {
    if (result.isConfirmed) {
      const form = document.getElementById('deleteEmployeeForm');
      form.action = `/employee/delete/${employeeId}/`;
      form.submit();
    }
  });
}

// Make function globally available
window.confirmEmployeeDelete = confirmEmployeeDelete;

// ============================================================
// EXPORT FOR EXTERNAL USE
// ============================================================
window.EmployeeFormManager = EmployeeFormManager;