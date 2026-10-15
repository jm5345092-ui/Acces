// Resuelve el código de país (ISO-2, ej. "GT") de una IP, con caché en memoria.
// Usa ip-api.com (gratis, sin API key). Se llama server-to-server, así que no hay
// problema de CORS ni de contenido mixto desde el portal.

const cache = new Map(); // ip -> { countryCode, ts }
const TTL_MS = 24 * 60 * 60 * 1000;

function isPrivate(ip) {
  return (
    ip === '127.0.0.1' ||
    ip === '::1' ||
    ip.startsWith('10.') ||
    ip.startsWith('192.168.') ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(ip)
  );
}

async function resolveCountry(ip) {
  if (!ip) return null;
  const clean = ip.replace(/^::ffff:/, '');
  if (isPrivate(clean)) return null;

  const hit = cache.get(clean);
  if (hit && Date.now() - hit.ts < TTL_MS) return hit.countryCode;

  try {
    const res = await fetch(`http://ip-api.com/json/${clean}?fields=status,countryCode`);
    const data = await res.json();
    const cc = data.status === 'success' ? data.countryCode : null;
    cache.set(clean, { countryCode: cc, ts: Date.now() });
    return cc;
  } catch (err) {
    console.error('geoip lookup falló:', err.message);
    return null;
  }
}

// País del propio servidor (su IP pública saliente). Sin IP, ip-api.com
// responde con la geolocalización de quien hace la petición = este servidor.
let selfCC = null;
let selfTs = 0;
async function resolveSelfCountry() {
  if (selfCC && Date.now() - selfTs < TTL_MS) return selfCC;
  try {
    const res = await fetch('http://ip-api.com/json/?fields=status,countryCode');
    const data = await res.json();
    selfCC = data.status === 'success' ? data.countryCode : null;
    selfTs = Date.now();
    return selfCC;
  } catch (err) {
    console.error('geoip self lookup falló:', err.message);
    return null;
  }
}

module.exports = { resolveCountry, resolveSelfCountry };
