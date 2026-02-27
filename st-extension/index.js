(() => {
  const KEY_BASE_URL = 'proxytavern.baseUrl';
  const KEY_PORT = 'proxytavern.port';

  const state = {
    baseUrl: localStorage.getItem(KEY_BASE_URL) || 'http://127.0.0.1',
    port: localStorage.getItem(KEY_PORT) || '8080',
  };

  function save(key, value) {
    localStorage.setItem(key, value);
  }

  function registerSettings() {
    if (!window?.SillyTavern?.settings) return;

    window.SillyTavern.settings.registerExtensionSettings?.('proxytavern', {
      label: 'ProxyTavern',
      items: [
        {
          type: 'text',
          key: 'baseUrl',
          label: 'Proxy endpoint base URL',
          default: state.baseUrl,
          onChange: (value) => {
            state.baseUrl = value;
            save(KEY_BASE_URL, value);
          },
        },
        {
          type: 'number',
          key: 'port',
          label: 'Proxy port',
          default: state.port,
          onChange: (value) => {
            state.port = String(value);
            save(KEY_PORT, String(value));
          },
        },
      ],
    });
  }

  registerSettings();
})();
