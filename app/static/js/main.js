/**
 * SMART CAMPUS 360 - GENERAL APPLICATION JAVASCRIPT
 * Government Engineering College, Mosalehosahalli (Hassan)
 */

document.addEventListener('DOMContentLoaded', function () {
  // Auto-dismiss alerts after 6 seconds
  const alerts = document.querySelectorAll('.alert-dismissible');
  alerts.forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) {
        bsAlert.close();
      }
    }, 6000);
  });
});
