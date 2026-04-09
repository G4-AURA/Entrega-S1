(function () {
    const errorBox = document.getElementById('upgrade-error');
    const feedbackBox = document.getElementById('plan-feedback');

    function showError(message) {
        if (!errorBox) {
            return;
        }
        errorBox.textContent = message;
        errorBox.classList.remove('d-none');
    }

    function showFeedback(message, type) {
        if (!feedbackBox) {
            return;
        }
        feedbackBox.classList.remove('d-none', 'alert-success', 'alert-warning', 'alert-danger');
        feedbackBox.classList.add(type || 'alert-success');
        feedbackBox.textContent = message;
    }

    async function postJson(endpoint) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            credentials: 'same-origin',
            body: '{}',
        });
        const payload = await response.json().catch(function () {
            return {};
        });
        return { response: response, payload: payload };
    }

    const upgradeButton = document.getElementById('btn-upgrade-plan');
    if (upgradeButton) {
        const endpoint = upgradeButton.dataset.endpoint || '/billing/create-checkout-session/';
        const defaultLabel = upgradeButton.textContent.trim();

        upgradeButton.addEventListener('click', async function () {
            upgradeButton.disabled = true;
            upgradeButton.textContent = 'Abriendo checkout...';
            if (errorBox) {
                errorBox.classList.add('d-none');
            }

            try {
                const result = await postJson(endpoint);
                const response = result.response;
                const payload = result.payload;

                if (!response.ok) {
                    throw new Error(payload.mensaje || 'No se pudo iniciar el checkout de Stripe.');
                }

                if (!payload.checkout_url) {
                    throw new Error('Stripe no devolvió URL de checkout.');
                }

                window.location.assign(payload.checkout_url);
            } catch (error) {
                showError(error.message || 'Error inesperado iniciando el pago.');
                upgradeButton.disabled = false;
                upgradeButton.textContent = defaultLabel;
            }
        });
    }

    const downgradeButton = document.getElementById('btn-downgrade-plan');
    if (!downgradeButton) {
        return;
    }

    const downgradeEndpoint = downgradeButton.dataset.endpoint || '/billing/schedule-downgrade/';
    const defaultDowngradeLabel = downgradeButton.textContent.trim();

    downgradeButton.addEventListener('click', async function () {
        downgradeButton.disabled = true;
        downgradeButton.textContent = 'Programando baja...';
        if (errorBox) {
            errorBox.classList.add('d-none');
        }
        if (feedbackBox) {
            feedbackBox.classList.add('d-none');
        }

        try {
            const result = await postJson(downgradeEndpoint);
            const response = result.response;
            const payload = result.payload;

            if (!response.ok) {
                throw new Error(payload.mensaje || 'No se pudo programar la baja a Freemium.');
            }

            showFeedback(payload.mensaje || 'Baja programada correctamente.', 'alert-success');

            const url = new URL(window.location.href);
            url.searchParams.set('downgrade', 'scheduled');
            window.setTimeout(function () {
                window.location.assign(url.toString());
            }, 900);
        } catch (error) {
            showError(error.message || 'Error inesperado programando la baja.');
            downgradeButton.disabled = false;
            downgradeButton.textContent = defaultDowngradeLabel;
        }
    });
})();
