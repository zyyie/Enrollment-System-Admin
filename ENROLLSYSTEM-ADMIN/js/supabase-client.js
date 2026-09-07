// Supabase client initialization
const SupabaseClient = (() => {
  let client = null;

  function getConfig() {
    return window.SUPABASE_CONFIG || {};
  }

  function isEnabled() {
    const config = getConfig();
    return Boolean(
      config.enabled &&
      config.url &&
      config.publishableKey &&
      config.url !== 'https://your-project-ref.supabase.co' &&
      typeof supabase !== 'undefined'
    );
  }

  function getClient() {
    if (!isEnabled()) return null;
    if (!client) {
      client = supabase.createClient(getConfig().url, getConfig().publishableKey);
    }
    return client;
  }

  return {
    getConfig,
    isEnabled,
    getClient
  };
})();
