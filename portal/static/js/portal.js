document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.learning-toggle');
  if (!toggle) return;
  const sections = document.getElementById(toggle.getAttribute('aria-controls'));
  const mobile = window.matchMedia('(max-width: 760px)');

  function setExpanded(expanded) {
    toggle.setAttribute('aria-expanded', String(expanded));
    sections.hidden = !expanded;
  }

  function syncLayout() {
    toggle.hidden = !mobile.matches;
    setExpanded(!mobile.matches);
  }

  toggle.addEventListener('click', () => {
    setExpanded(toggle.getAttribute('aria-expanded') !== 'true');
  });
  mobile.addEventListener('change', () => {
    // Keep keyboard focus visible when switching between layouts.
    if (mobile.matches && sections.contains(document.activeElement)) {
      toggle.hidden = false;
      toggle.focus();
    }
    if (!mobile.matches && document.activeElement === toggle) {
      setExpanded(true);
      sections.querySelector('a')?.focus();
    }
    syncLayout();
  });
  syncLayout();
});
