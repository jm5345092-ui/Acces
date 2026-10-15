const METERED_APP_DOMAIN = process.env.METERED_APP_DOMAIN || 'acces.metered.live';

/**
 * Pide credenciales TURN frescas a Metered.ca. Se hace desde el servidor (no desde
 * las apps/navegador) para que la API key nunca se exponga al cliente.
 */
async function fetchTurnCredentials() {
  const apiKey = process.env.METERED_API_KEY;
  if (!apiKey) throw new Error('METERED_API_KEY no configurada');
  const url = `https://${METERED_APP_DOMAIN}/api/v1/turn/credentials?apiKey=${apiKey}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Metered respondió ${res.status}`);
  return res.json();
}

module.exports = { fetchTurnCredentials };
