const crypto = require('crypto');
const bcrypt = require('bcryptjs');
const { pool } = require('./db/pool');

const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 días

async function createOwner(username, password) {
  const passwordHash = await bcrypt.hash(password, 10);
  await pool.query(
    'INSERT INTO owners (username, password_hash) VALUES ($1, $2)',
    [username, passwordHash]
  );
}

/** Verifica usuario/contraseña y crea una sesión. Devuelve el token o null si falla. */
async function login(username, password) {
  const { rows } = await pool.query(
    'SELECT password_hash FROM owners WHERE username = $1',
    [username]
  );
  if (rows.length === 0) return null;
  const valid = await bcrypt.compare(password, rows[0].password_hash);
  if (!valid) return null;

  const token = crypto.randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + SESSION_TTL_MS);
  await pool.query(
    'INSERT INTO sessions (token, owner, expires_at) VALUES ($1, $2, $3)',
    [token, username, expiresAt]
  );
  return token;
}

/** Devuelve el owner del token si es válido y no expiró, o null. */
async function resolveSessionOwner(token) {
  if (!token) return null;
  const { rows } = await pool.query(
    'SELECT owner FROM sessions WHERE token = $1 AND expires_at > now()',
    [token]
  );
  return rows.length ? rows[0].owner : null;
}

function extractBearerToken(req) {
  const header = req.headers.authorization || '';
  const match = header.match(/^Bearer (.+)$/);
  return match ? match[1] : null;
}

/** Middleware: exige un ownerToken válido (Authorization: Bearer <token>) y expone req.owner. */
async function requireOwner(req, res, next) {
  const token = extractBearerToken(req);
  console.log('[Auth] Token recibido:', token ? `${token.substring(0, 16)}...` : 'NONE');
  const owner = await resolveSessionOwner(token);
  console.log('[Auth] Owner resuelto:', owner || 'NONE');
  if (!owner) {
    res.status(401).json({ error: 'No autenticado' });
    return;
  }
  req.owner = owner;
  next();
}

/** Middleware: exige la clave de servicio interna (usada por worker.js, nunca por el navegador). */
function requireServiceKey(req, res, next) {
  const key = req.headers['x-service-key'];
  if (!key || key !== process.env.SERVICE_KEY) {
    res.status(401).json({ error: 'Clave de servicio inválida' });
    return;
  }
  next();
}

module.exports = { createOwner, login, resolveSessionOwner, requireOwner, requireServiceKey };
