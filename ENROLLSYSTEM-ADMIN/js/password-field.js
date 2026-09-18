(function hideNativePasswordRevealForEdge() {
  const styleId = 'ems-hide-native-password-reveal';
  if (document.getElementById(styleId)) return;
  const style = document.createElement('style');
  style.id = styleId;
  style.textContent = `
    input[type="password"]::-ms-reveal,
    input[type="password"]::-ms-clear {
      display: none !important;
      width: 0 !important;
      height: 0 !important;
      max-width: 0 !important;
      max-height: 0 !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }
    input[type="password"]::-webkit-credentials-auto-fill-button {
      visibility: hidden !important;
      pointer-events: none !important;
      width: 0 !important;
      height: 0 !important;
    }
  `;
  (document.head || document.documentElement).appendChild(style);
})();

function passwordEyeShowIcon() {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
    <circle cx="12" cy="12" r="3"></circle>
  </svg>`;
}

function passwordEyeHideIcon() {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"></path>
    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"></path>
    <line x1="1" y1="1" x2="23" y2="23"></line>
  </svg>`;
}

function togglePasswordVisibility(input, button) {
  const show = input.type === 'password';
  input.type = show ? 'text' : 'password';
  button.innerHTML = show ? passwordEyeHideIcon() : passwordEyeShowIcon();
  button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  button.setAttribute('aria-pressed', show ? 'true' : 'false');
  button.classList.toggle('is-visible', show);
}

function bindPasswordField(input) {
  if (!input || input.dataset.passwordBound === '1') return;

  let wrapper = input.closest('.password-field');
  if (wrapper) {
    const extraToggles = wrapper.querySelectorAll('.password-toggle');
    extraToggles.forEach((btn, index) => {
      if (index > 0) btn.remove();
    });
  }

  let toggle = wrapper ? wrapper.querySelector('.password-toggle') : null;

  if (!wrapper) {
    wrapper = document.createElement('div');
    wrapper.className = 'password-field';
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);
  }

  if (!toggle) {
    toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'password-toggle';
    toggle.setAttribute('aria-label', 'Show password');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.innerHTML = passwordEyeShowIcon();
    wrapper.appendChild(toggle);
  }

  if (toggle.dataset.passwordToggleBound !== '1') {
    toggle.addEventListener('click', () => togglePasswordVisibility(input, toggle));
    toggle.dataset.passwordToggleBound = '1';
  }
  input.dataset.passwordBound = '1';
}

function bindPasswordFields(root) {
  const scope = root || document;
  scope.querySelectorAll('input[type="password"]').forEach(bindPasswordField);
}

function initPasswordFields() {
  bindPasswordFields();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPasswordFields, { once: true });
} else {
  initPasswordFields();
}
