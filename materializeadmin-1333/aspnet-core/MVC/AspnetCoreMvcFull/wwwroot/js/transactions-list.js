/**
 * Transactions CRUD JS
 */

'use strict';

// Transactions DataTable initialization
$(document).ready(function () {
  let borderColor, bodyBg, headingColor;

  if (isDarkStyle) {
    borderColor = config.colors_dark.borderColor;
    bodyBg = config.colors_dark.bodyBg;
    headingColor = config.colors_dark.headingColor;
  } else {
    borderColor = config.colors.borderColor;
    bodyBg = config.colors.bodyBg;
    headingColor = config.colors.headingColor;
  }

  var toastElements = document.querySelectorAll('.toast');

  if (toastElements) {
    toastElements.forEach(function (element) {
      var toast = new bootstrap.Toast(element);
      toast.show();
    });
  }

  // Transactions List DataTable Initialization (For Transactions CRUD Page)
  $('#transactionsTable').DataTable({
    order: [[1, 'desc']],
    displayLength: 7,
    dom:
      // Datatable DOM positioning
      '<"row"' +
      '<"col-md-2"<l>>' +
      '<"col-md-10"<"dt-action-buttons d-flex align-items-center justify-content-end flex-md-row flex-column gap-md-4 mb-4 mb-md-0"fB>>' +
      '>t' +
      '<"row"' +
      '<"col-sm-12 col-md-6"i>' +
      '<"col-sm-12 col-md-6"p>' +
      '>',
    lengthMenu: [7, 10, 15, 20],
    language: {
      sLengthMenu: '_MENU_',
      search: '',
      searchPlaceholder: 'Search Transaction',
      paginate: {
        next: '<i class="ri-arrow-right-s-line"></i>',
        previous: '<i class="ri-arrow-left-s-line"></i>'
      }
    },
    // Buttons with Dropdown
    buttons: [
      {
        extend: 'collection',
        className: 'btn btn-outline-secondary dropdown-toggle me-4 waves-effect waves-light',
        text: '<i class="ri-download-line ri-16px me-1"></i>Export',
        buttons: [
          {
            extend: 'print',
            title: 'Transactions Data',
            text: '<i class="ri-printer-line me-1" ></i>Print',
            className: 'dropdown-item',
            customize: function (win) {
              //customize print view for dark
              $(win.document.body)
                .css('color', config.colors.headingColor)
                .css('border-color', config.colors.borderColor)
                .css('background-color', config.colors.body);

              $(win.document.body)
                .find('table')
                .addClass('compact')
                .css('color', 'inherit')
                .css('border-color', 'inherit')
                .css('background-color', 'inherit');

              // Center the title "Transactions Data"
              $(win.document.body).find('h1').css('text-align', 'center');
            },
            exportOptions: {
              columns: [1, 2, 3, 4, 5, 6]
            }
          },
          {
            extend: 'csv',
            title: 'Transactions',
            text: '<i class="ri-file-text-line me-1" ></i>Csv',
            className: 'dropdown-item',
            exportOptions: {
              columns: [1, 2, 3, 4, 5, 6]
            }
          },
          {
            extend: 'excel',
            title: 'Transactions',
            text: '<i class="ri-file-excel-line me-1"></i>Excel',
            className: 'dropdown-item',
            exportOptions: {
              columns: [1, 2, 3, 4, 5, 6]
            }
          },
          {
            extend: 'pdf',
            title: 'Transactions',
            text: '<i class="ri-file-pdf-line me-1"></i>Pdf',
            className: 'dropdown-item',
            exportOptions: {
              columns: [1, 2, 3, 4, 5, 6]
            }
          },
          {
            extend: 'copy',
            title: 'Transactions',
            text: '<i class="ri-file-copy-line me-1"></i>Copy',
            className: 'dropdown-item',
            exportOptions: {
              columns: [1, 2, 3, 4, 5, 6]
            }
          }
        ]
      },
      {
        // For Create Transactions Button (Add New Transactions)
        text: '<i class="ri-add-line ri-16px me-0 me-sm-1_5"></i><span class="d-none d-sm-inline-block">Add Transaction</span>',
        className: 'add-new btn btn-primary waves-effect waves-light',
        action: function (e, dt, button, config) {
          window.location.href = '/Transactions/Add';
        }
      }
    ],
    responsive: true,
    // For responsive popup
    rowReorder: {
      selector: 'td:nth-child(2)'
    },
    // For responsive popup button and responsive priority for transactions name
    columnDefs: [
      {
        // For Responsive Popup Button (plus icon)
        className: 'control',
        searchable: false,
        orderable: false,
        responsivePriority: 2,
        targets: 0,
        render: function (data, type, full, meta) {
          return '';
        }
      },
      {
        // For Id
        targets: 1,
        responsivePriority: 4
      },
      {
        // For Transactions Name
        targets: 2,
        responsivePriority: 3
      },
      {
        // For Transactions Date
        targets: 3,
        responsivePriority: 9
      },
      {
        // For Due Date
        targets: 4,
        responsivePriority: 5
      },
      {
        // For Total Amount
        targets: 5,
        responsivePriority: 7
      },
      {
        // For Status
        targets: 6,
        responsivePriority: 8
      },
      {
        // For Actions
        targets: -1,
        searchable: false,
        orderable: false,
        responsivePriority: 1
      }
    ],
    responsive: {
      details: {
        display: $.fn.dataTable.Responsive.display.modal({
          header: function (row) {
            var data = row.data();
            return 'Transaction details of ' + data[2];
          }
        }),
        type: 'column',
        renderer: function (api, rowIdx, columns) {
          var data = $.map(columns, function (col, i) {
            // Exclude the last column (Action)
            if (i < columns.length - 1) {
              return col.title !== ''
                ? '<tr data-dt-row="' +
                    col.rowIndex +
                    '" data-dt-column="' +
                    col.columnIndex +
                    '">' +
                    '<td>' +
                    col.title +
                    ':' +
                    '</td> ' +
                    '<td>' +
                    col.data +
                    '</td>' +
                    '</tr>'
                : '';
            }
            return '';
          }).join('');

          return data ? $('<table class="table mt-3"/><tbody />').append(data) : false;
        }
      }
    }
  });
});

// Filter Form styles to default size after DataTable initialization
setTimeout(() => {
  $('.dataTables_filter input').addClass('ms-0');
  $('div.dataTables_wrapper .dataTables_filter').addClass('mt-0 mt-md-5');
  $('div.dataTables_wrapper div.dataTables_length').addClass('my-5');
}, 300);
