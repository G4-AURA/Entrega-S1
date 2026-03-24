(function () {
    if (window.AuraFeedback) {
        return;
    }

    const state = {
        initialized: false,
        pendingResolver: null,
        lastFocusedElement: null,
        overlay: null,
        modal: null,
        iconWrap: null,
        iconEl: null,
        titleEl: null,
        messageEl: null,
        cancelBtn: null,
        confirmBtn: null,
        toastHost: null,
    };

    const iconByType = {
        default: 'help',
        info: 'info',
        success: 'check_circle',
        danger: 'warning',
        error: 'error',
    };

    function createFeedbackDom() {
        const overlay = document.createElement('div');
        overlay.id = 'aura-feedback-overlay';
        overlay.className = 'aura-feedback-overlay is-hidden';
        overlay.setAttribute('aria-hidden', 'true');

        const modal = document.createElement('div');
        modal.id = 'aura-feedback-modal';
        modal.className = 'aura-feedback-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'aura-feedback-title');
        modal.setAttribute('aria-describedby', 'aura-feedback-message');

        const iconWrap = document.createElement('div');
        iconWrap.id = 'aura-feedback-icon-wrap';
        iconWrap.className = 'aura-feedback-modal-icon-wrap';

        const icon = document.createElement('span');
        icon.id = 'aura-feedback-icon';
        icon.className = 'material-icons-round';
        icon.textContent = 'help';
        iconWrap.appendChild(icon);

        const title = document.createElement('h2');
        title.id = 'aura-feedback-title';
        title.className = 'aura-feedback-modal-title';
        title.textContent = 'Confirmación';

        const message = document.createElement('p');
        message.id = 'aura-feedback-message';
        message.className = 'aura-feedback-modal-message';
        message.textContent = '¿Deseas continuar?';

        const actions = document.createElement('div');
        actions.className = 'aura-feedback-modal-actions';

        const cancelButton = document.createElement('button');
        cancelButton.type = 'button';
        cancelButton.id = 'aura-feedback-cancel';
        cancelButton.className = 'aura-feedback-modal-cancel';
        cancelButton.textContent = 'Cancelar';

        const confirmButton = document.createElement('button');
        confirmButton.type = 'button';
        confirmButton.id = 'aura-feedback-confirm';
        confirmButton.className = 'aura-feedback-modal-confirm';
        confirmButton.textContent = 'Aceptar';

        actions.appendChild(cancelButton);
        actions.appendChild(confirmButton);

        modal.appendChild(iconWrap);
        modal.appendChild(title);
        modal.appendChild(message);
        modal.appendChild(actions);
        overlay.appendChild(modal);

        const toastHost = document.createElement('div');
        toastHost.id = 'aura-feedback-toast-host';
        toastHost.className = 'aura-feedback-toast-host';
        toastHost.setAttribute('aria-live', 'polite');
        toastHost.setAttribute('aria-atomic', 'true');

        document.body.appendChild(overlay);
        document.body.appendChild(toastHost);

        state.overlay = overlay;
        state.modal = modal;
        state.iconWrap = iconWrap;
        state.iconEl = icon;
        state.titleEl = title;
        state.messageEl = message;
        state.cancelBtn = cancelButton;
        state.confirmBtn = confirmButton;
        state.toastHost = toastHost;
    }

    function getFocusableElements() {
        return Array.from(
            state.modal.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')
        ).filter((el) => !el.disabled && el.offsetParent !== null);
    }

    function closeModal(accepted) {
        state.overlay.classList.add('is-hidden');
        state.overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('aura-feedback-open');

        if (
            state.lastFocusedElement &&
            typeof state.lastFocusedElement.focus === 'function'
        ) {
            state.lastFocusedElement.focus();
        }
        state.lastFocusedElement = null;

        const resolver = state.pendingResolver;
        state.pendingResolver = null;
        if (resolver) {
            resolver(Boolean(accepted));
        }
    }

    function initListeners() {
        state.overlay.addEventListener('click', (event) => {
            if (event.target === state.overlay) {
                closeModal(false);
            }
        });

        state.cancelBtn.addEventListener('click', () => closeModal(false));
        state.confirmBtn.addEventListener('click', () => closeModal(true));

        document.addEventListener('keydown', (event) => {
            if (state.overlay.classList.contains('is-hidden')) {
                return;
            }

            if (event.key === 'Escape') {
                event.preventDefault();
                closeModal(false);
                return;
            }

            if (event.key !== 'Tab') {
                return;
            }

            const focusable = getFocusableElements();
            if (!focusable.length) {
                event.preventDefault();
                return;
            }

            const first = focusable[0];
            const last = focusable[focusable.length - 1];

            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
                return;
            }
            if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });
    }

    function ensureInitialized() {
        if (state.initialized) {
            return;
        }
        if (!document.body) {
            return;
        }

        createFeedbackDom();
        initListeners();
        state.initialized = true;
    }

    function normalizeType(type) {
        return type && Object.prototype.hasOwnProperty.call(iconByType, type)
            ? type
            : 'default';
    }

    async function confirm(options = {}) {
        ensureInitialized();
        if (!state.initialized) {
            return false;
        }

        if (state.pendingResolver) {
            closeModal(false);
        }

        const normalizedType = normalizeType(options.type);
        const showCancel = options.showCancel !== false;

        state.titleEl.textContent = options.title || 'Confirmación';
        state.messageEl.textContent = options.message || '¿Deseas continuar?';
        state.confirmBtn.textContent = options.confirmText || 'Aceptar';
        state.cancelBtn.textContent = options.cancelText || 'Cancelar';
        state.cancelBtn.style.display = showCancel ? '' : 'none';
        state.confirmBtn.style.flex = showCancel ? '1' : '0 0 auto';
        state.confirmBtn.style.minWidth = showCancel ? '' : '160px';

        state.iconEl.textContent = iconByType[normalizedType];
        state.iconWrap.classList.toggle(
            'is-danger',
            normalizedType === 'danger' || normalizedType === 'error'
        );
        state.confirmBtn.classList.toggle(
            'is-danger',
            normalizedType === 'danger' || normalizedType === 'error'
        );

        state.lastFocusedElement = document.activeElement;
        state.overlay.classList.remove('is-hidden');
        state.overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('aura-feedback-open');
        setTimeout(() => state.confirmBtn.focus(), 0);

        return new Promise((resolve) => {
            state.pendingResolver = resolve;
        });
    }

    function toast(message, options = {}) {
        ensureInitialized();
        if (!state.initialized || !state.toastHost) {
            return;
        }

        const normalizedType = ['success', 'error', 'info'].includes(options.type)
            ? options.type
            : 'info';

        const toastEl = document.createElement('div');
        toastEl.className = `aura-feedback-toast aura-feedback-toast--${normalizedType}`;

        const iconSpan = document.createElement('span');
        iconSpan.className = 'material-icons-round aura-feedback-toast-icon';
        iconSpan.textContent = iconByType[normalizedType];

        const textSpan = document.createElement('span');
        textSpan.className = 'aura-feedback-toast-text';
        textSpan.textContent = String(message || '');

        toastEl.appendChild(iconSpan);
        toastEl.appendChild(textSpan);
        state.toastHost.appendChild(toastEl);

        requestAnimationFrame(() => {
            toastEl.classList.add('is-visible');
        });

        const closeToast = () => {
            toastEl.classList.remove('is-visible');
            setTimeout(() => toastEl.remove(), 220);
        };

        setTimeout(closeToast, Math.max(1800, Number(options.duration) || 2800));
    }

    async function alertModal(options = {}) {
        const message =
            typeof options === 'string'
                ? options
                : options.message || options.text || 'Continuar';
        const title = typeof options === 'string' ? 'Información' : options.title || 'Información';
        const buttonText = typeof options === 'string' ? 'Aceptar' : options.buttonText || 'Aceptar';
        const type = typeof options === 'string' ? 'info' : options.type || 'info';

        return confirm({
            title,
            message,
            confirmText: buttonText,
            showCancel: false,
            type,
        });
    }

    window.AuraFeedback = {
        confirm,
        toast,
        alert: alertModal,
    };

    if (document.readyState !== 'loading') {
        ensureInitialized();
    } else {
        document.addEventListener('DOMContentLoaded', ensureInitialized, { once: true });
    }
})();
