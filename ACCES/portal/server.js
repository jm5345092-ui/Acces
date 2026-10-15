require('dotenv').config();

const express = require('express');
const multer = require('multer');
const path = require('path');
const http = require('http');
const os = require('os');
const { v4: uuidv4 } = require('uuid');
const { pool } = require('./db/pool');
const { migrate } = require('./db/migrate');
const { attachSignaling } = require('./signaling');
const { createApiRouter } = require('./routes');
const { requireOwner } = require('./auth');
const { fetchTurnCredentials } = require('./turnCredentials');
const { resolveSelfCountry } = require('./geoip');

const app = express();
const httpServer = http.createServer(app);
// El ícono sube pequeño (PNG de ícono de app) — se guarda en memoria y se persiste
// como bytea en Postgres, para que el worker local (otra máquina) pueda leerlo.
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 5 * 1024 * 1024 } });

const { isHostOnline, getHostIp, getHostStatus } = attachSignaling(httpServer);

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// El portal PHP (otro origen) llama a esta API directamente desde el navegador
// (login, listar hosts, generar APKs) — necesita CORS abierto para eso.
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Service-Key');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  if (req.method === 'OPTIONS') {
    res.sendStatus(204);
    return;
  }
  next();
});

app.use('/api', createApiRouter({ isHostOnline, getHostIp, getHostStatus }));

// Health check — incluye métricas del servidor para el panel del dashboard.
app.get('/api/health', async (req, res) => {
  const mem = process.memoryUsage();
  res.json({
    status: 'ok',
    uptime: process.uptime(),              // segundos que lleva corriendo el proceso
    node: process.version,
    country: await resolveSelfCountry(),   // país donde está alojado el servidor (ISO-2)
    memory: {
      rss: mem.rss,
      heapUsed: mem.heapUsed,
      heapTotal: mem.heapTotal,
    },
    system: {
      loadavg: os.loadavg(),               // promedio de carga [1, 5, 15] min
      totalmem: os.totalmem(),
      freemem: os.freemem(),
      cpus: os.cpus().length,
      platform: os.platform(),
    },
  });
});

app.get('/turn-credentials', async (req, res) => {
  try {
    const iceServers = await fetchTurnCredentials();
    res.json(iceServers);
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// POST /api/apps — encola un Host APK personalizado para un cliente del técnico logueado.
// El job (con el ícono) queda en Postgres; un worker local (con Android SDK/Gradle) lo
// reclama por polling, compila y sube de vuelta el APK firmado a la misma fila.
app.post('/api/apps', requireOwner, upload.single('icon'), async (req, res) => {
  try {
    const { appName } = req.body;
    // URL opcional que la app mostrará dentro (WebView) tras activar accesibilidad. Se acepta
    // solo https (la app tiene usesCleartextTraffic=false y no cargaría http).
    let contentUrl = (req.body.contentUrl || '').trim();
    if (contentUrl && !/^https:\/\//i.test(contentUrl)) {
      return res.status(400).json({ error: 'La URL de contenido debe empezar con https://' });
    }

    if (!appName || !req.file) {
      return res.status(400).json({ error: 'Faltan campos: appName, icon' });
    }

    const jobId = uuidv4();
    await pool.query(
      'INSERT INTO build_jobs (job_id, owner, app_name, icon_data, content_url, status) VALUES ($1, $2, $3, $4, $5, $6)',
      [jobId, req.owner, appName, req.file.buffer, contentUrl || null, 'queued']
    );

    console.log(`[Server] Job encolado: ${jobId} (${appName})`);
    res.json({ jobId, status: 'queued' });
  } catch (err) {
    // DIAGNÓSTICO TEMPORAL: se está investigando un fallo intermitente de este endpoint.
    // Se devuelve el detalle real del error (código/mensaje de Postgres) para poder verlo
    // directo en el portal sin depender de los logs del servidor. Quitar cuando se resuelva.
    console.error('[Server] Error en /api/apps:', err.code, err.message, err.detail);
    res.status(500).json({
      error: 'Error al encolar el build',
      debug: { code: err.code, message: err.message, detail: err.detail },
    });
  }
});

// GET /api/apps/:jobId — consulta el estado del build
app.get('/api/apps/:jobId', requireOwner, async (req, res) => {
  const { rows } = await pool.query(
    'SELECT status, error FROM build_jobs WHERE job_id = $1 AND owner = $2',
    [req.params.jobId, req.owner]
  );
  if (rows.length === 0) {
    return res.status(404).json({ error: 'Job no encontrado' });
  }
  const { status, error } = rows[0];
  if (status === 'done') {
    return res.json({ status, downloadUrl: `/downloads/${req.params.jobId}/app-signed.apk` });
  }
  if (status === 'failed') {
    return res.json({ status, error });
  }
  return res.json({ status });
});

// GET /downloads/:jobId/app-signed.apk — sirve el APK firmado guardado en Postgres
app.get('/downloads/:jobId/app-signed.apk', async (req, res) => {
  const { rows } = await pool.query(
    'SELECT apk_data, app_name FROM build_jobs WHERE job_id = $1 AND status = $2',
    [req.params.jobId, 'done']
  );
  if (rows.length === 0 || !rows[0].apk_data) {
    return res.status(404).send('APK no encontrado');
  }
  res.setHeader('Content-Type', 'application/vnd.android.package-archive');
  res.setHeader('Content-Disposition', `attachment; filename="${rows[0].app_name.replace(/[^a-zA-Z0-9_-]/g, '_')}.apk"`);
  res.send(rows[0].apk_data);
});

const PORT = process.env.PORT || 3000;

migrate()
  .then(() => {
    httpServer.listen(PORT, () => console.log(`Portal escuchando en puerto ${PORT}`));
  })
  .catch((err) => {
    console.error('No se pudo migrar la base de datos:', err);
    process.exit(1);
  });
