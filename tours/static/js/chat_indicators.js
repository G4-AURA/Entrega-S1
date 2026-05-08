/* AURA — Indicadores compartidos de mensajes de chat */
'use strict';

(function () {
  const CHANNELS = {
    chat: {
      tabBadgeId: 'chat-badge',
      switchBadgeId: 'session-chat-switch-group-badge',
    },
    private: {
      tabBadgeId: 'chat-privado-badge',
      switchBadgeId: 'session-chat-switch-private-badge',
    },
  };

  const counts = {
    chat: 0,
    private: 0,
  };

  function normalizeChannel(channel) {
    return channel === 'private' || channel === 'chat-privado' ? 'private' : 'chat';
  }

  function formatCount(value) {
    return value > 99 ? '99+' : String(value);
  }

  function setBadgeValue(element, value) {
    if (!element) return;
    if (value > 0) {
      element.textContent = formatCount(value);
      element.style.display = 'inline-flex';
    } else {
      element.textContent = '';
      element.style.display = 'none';
    }
  }

  function updateChannel(channel) {
    const key = normalizeChannel(channel);
    const channelConfig = CHANNELS[key];
    const value = counts[key];

    setBadgeValue(document.getElementById(channelConfig.tabBadgeId), value);
    setBadgeValue(document.getElementById(channelConfig.switchBadgeId), value);

    const switchButton = document.querySelector(`[data-chat-tab="${key === 'private' ? 'chat-privado' : 'chat'}"]`);
    if (switchButton) {
      switchButton.classList.toggle('has-unread', value > 0);
    }
  }

  function updateTotal() {
    const total = counts.chat + counts.private;
    setBadgeValue(document.getElementById('session-chat-badge'), total);

    document.querySelectorAll('.session-nav-btn[data-open-tab="chat"]').forEach((button) => {
      button.classList.toggle('has-unread', total > 0);
    });
  }

  function render() {
    updateChannel('chat');
    updateChannel('private');
    updateTotal();
  }

  window.AuraChatIndicators = {
    increment(channel, amount = 1) {
      const key = normalizeChannel(channel);
      const numericAmount = Number.parseInt(String(amount), 10);
      counts[key] += Number.isFinite(numericAmount) && numericAmount > 0 ? numericAmount : 1;
      render();
    },
    clear(channel) {
      const key = normalizeChannel(channel);
      counts[key] = 0;
      render();
    },
    set(channel, value) {
      const key = normalizeChannel(channel);
      const numericValue = Number.parseInt(String(value), 10);
      counts[key] = Number.isFinite(numericValue) && numericValue > 0 ? numericValue : 0;
      render();
    },
    get(channel) {
      return counts[normalizeChannel(channel)];
    },
    render,
  };

  document.addEventListener('DOMContentLoaded', render);
})();
