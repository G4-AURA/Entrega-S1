(function () {
    function setRecalcularButtonLoading(button, isLoading, hasError) {
        if (!button) {
            return;
        }

        button.disabled = !!isLoading;
        button.classList.toggle('is-loading', !!isLoading);

        if (isLoading) {
            button.textContent = '⏳ Calculando...';
            return;
        }

        button.textContent = hasError ? '🔄 Reintentar' : '🔄 Calcular ruta';
    }

    window.RouteDetailUI = {
        setRecalcularButtonLoading,
    };
})();
