const express = require('express');
const crypto = require('crypto');
const { v4: uuidv4 } = require('uuid');
const { pool } = require('./db/pool');
const { login, requireOwner, requireServiceKey } = require('./auth');
const { resolveCountry } = require('./geoip');

/** Rutas de cuentas y hosts. Los getters vienen del módulo de señalización (mismo proceso). */
function createApiRouter({ isHostOnline, getHostIp, getHostStatus }) {
  const router = express.Router();

  router.post('/login', async (req, res) => {
    const { username, password } = req.body || {};
    if (!username || !password) {
      res.status(400).json({ error: 'Faltan usuario o contraseña' });
      return;
    }
    const token = await login(username, password);
    if (!token) {
      res.status(401).json({ error: 'Usuario o contraseña incorrectos' });
      return;
    }
    res.json({ ok: true, ownerToken: token, username });
  });

  // Lista una fila por teléfono (devices), no por APK: el mismo APK puede estar instalado en
  // varios. `hostId` en la respuesta es el device_id — es lo que host.php usa para conectar.
  router.get('/hosts', requireOwner, async (req, res) => {
    const { rows } = await pool.query(
      `SELECT d.device_id, d.friendly_name, d.device_model, d.last_seen_at,
              h.host_id, h.friendly_name AS app_name
       FROM devices d JOIN hosts h ON h.host_id = d.host_id
       WHERE h.owner = $1
       ORDER BY h.friendly_name, d.created_at`,
      [req.owner]
    );
    const hosts = await Promise.all(
      rows.map(async (r) => {
        const ip = getHostIp(r.device_id);
        const status = getHostStatus(r.device_id) || {};
        return {
          hostId: r.device_id,
          appHostId: r.host_id,
          appName: r.app_name,
          deviceModel: r.device_model || '',
          friendlyName: r.friendly_name,
          online: isHostOnline(r.device_id),
          ip,
          countryCode: await resolveCountry(ip),
          accessibilityEnabled: !!status.accessibilityEnabled,
          screenOn: !!status.screenOn,
          currentApp: status.appLabel || '',
          lastSeenAt: r.last_seen_at,
        };
      })
    );
    res.json(hosts);
  });

  // Renombrar un dispositivo (friendly_name) — solo el dueño. No afecta el nombre de la app instalada.
  router.post('/hosts/:hostId/rename', requireOwner, async (req, res) => {
    const { friendlyName } = req.body || {};
    const name = (friendlyName || '').trim();
    if (!name) {
      res.status(400).json({ error: 'Falta friendlyName' });
      return;
    }
    const { rowCount } = await pool.query(
      `UPDATE devices d SET friendly_name = $1
       FROM hosts h WHERE h.host_id = d.host_id AND d.device_id = $2 AND h.owner = $3`,
      [name, req.params.hostId, req.owner]
    );
    if (rowCount === 0) {
      res.status(404).json({ error: 'Host no encontrado o sin acceso' });
      return;
    }
    res.json({ ok: true, friendlyName: name });
  });

  // Eliminar — solo el dueño. Borra SOLO ese dispositivo (una fila de devices), NO el host/app.
  // Así, si varios teléfonos comparten la misma app (mismo host), se elimina únicamente el que
  // se pulsó en ver.php y los demás quedan intactos. El :hostId de la URL es el device_id.
  // Nota: si ese mismo teléfono sigue con la app instalada y vuelve a conectarse, se registrará
  // de nuevo y reaparecerá — eso es correcto (es un dispositivo activo de esa app). Para quitarlo
  // definitivamente hay que desinstalar la app en ese teléfono.
  router.delete('/hosts/:hostId', requireOwner, async (req, res) => {
    const { rowCount } = await pool.query(
      `DELETE FROM devices
       WHERE device_id = $1
         AND host_id IN (SELECT host_id FROM hosts WHERE owner = $2)`,
      [req.params.hostId, req.owner]
    );
    if (rowCount === 0) {
      res.status(404).json({ error: 'Dispositivo no encontrado o sin acceso' });
      return;
    }
    res.json({ ok: true });
  });

  // Interno: lo llama worker.js (nunca el navegador ni el APK) antes de compilar un Host.
  router.post('/hosts', requireServiceKey, async (req, res) => {
    const { owner, friendlyName } = req.body || {};
    if (!owner || !friendlyName) {
      res.status(400).json({ error: 'Faltan owner o friendlyName' });
      return;
    }
    const hostId = uuidv4();
    const hostSecret = crypto.randomBytes(24).toString('hex');
    await pool.query(
      'INSERT INTO hosts (host_id, owner, host_secret, friendly_name) VALUES ($1, $2, $3, $4)',
      [hostId, owner, hostSecret, friendlyName]
    );
    res.json({ hostId, hostSecret, friendlyName, owner });
  });

  return router;
}

module.exports = { createApiRouter };
