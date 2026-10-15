require('dotenv').config();

const fs = require('fs-extra');
const os = require('os');
const path = require('path');
const { execSync } = require('child_process');
const sharp = require('sharp');
const { pool } = require('./db/pool');

const TEMPLATE_DIR = path.join(__dirname, 'template-project');
const POLL_INTERVAL_MS = 4000;

// Tamaños de ícono requeridos por densidad
const ICON_SIZES = {
  'mipmap-mdpi': 48,
  'mipmap-hdpi': 72,
  'mipmap-xhdpi': 96,
  'mipmap-xxhdpi': 144,
  'mipmap-xxxhdpi': 192,
};

async function injectIcon(iconSourcePath, projectDir) {
  console.log(`[Worker] Inyectando ícono desde: ${iconSourcePath}`);
  const metadata = await sharp(iconSourcePath).metadata();
  console.log(`[Worker] Ícono: ${metadata.width}x${metadata.height} (${metadata.format})`);

  for (const [folder, size] of Object.entries(ICON_SIZES)) {
    const destDir = path.join(projectDir, 'app/src/main/res', folder);
    await fs.ensureDir(destDir);
    const destFile = path.join(destDir, 'ic_launcher.png');

    await sharp(iconSourcePath)
      .resize(size, size, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 1 } })
      .png()
      .toFile(destFile);

    console.log(`[Worker] ✓ ${size}x${size} en ${folder}`);
  }
}

const PORTAL_BASE_URL = process.env.PORTAL_BASE_URL || 'http://localhost:3000';

/** Crea el registro del host en el backend y devuelve sus credenciales de fábrica. */
async function createHostRecord(owner, friendlyName) {
  console.log(`[Worker] POST /api/hosts: owner=${owner}, friendlyName=${friendlyName}`);
  const res = await fetch(`${PORTAL_BASE_URL}/api/hosts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Service-Key': process.env.SERVICE_KEY,
    },
    body: JSON.stringify({ owner, friendlyName }),
  });

  const responseText = await res.text();
  if (!res.ok) throw new Error(`Error ${res.status}: ${responseText}`);

  const data = JSON.parse(responseText);
  console.log(`[Worker] Host creado: ID=${data.hostId.substring(0, 8)}...`);
  return data;
}

/** Reclama el job en cola más antiguo, de forma atómica (segura ante varios workers). */
async function claimNextJob() {
  const { rows } = await pool.query(`
    UPDATE build_jobs
    SET status = 'processing', claimed_at = now()
    WHERE job_id = (
      SELECT job_id FROM build_jobs
      WHERE status = 'queued'
      ORDER BY created_at
      FOR UPDATE SKIP LOCKED
      LIMIT 1
    )
    RETURNING job_id, owner, app_name, icon_data, content_url
  `);
  return rows[0] || null;
}

async function markDone(jobId, apkBuffer) {
  await pool.query(
    "UPDATE build_jobs SET status = 'done', apk_data = $1, completed_at = now() WHERE job_id = $2",
    [apkBuffer, jobId]
  );
}

async function markFailed(jobId, errorMsg) {
  await pool.query(
    "UPDATE build_jobs SET status = 'failed', error = $1, completed_at = now() WHERE job_id = $2",
    [errorMsg.slice(0, 4000), jobId]
  );
}

async function processJob(job) {
  const { job_id: jobId, owner, app_name: appName, icon_data: iconData, content_url: contentUrl } = job;
  const workDir = path.join(os.tmpdir(), `acces-build-${jobId}`);
  const projectDir = path.join(workDir, 'project');

  console.log(`[Worker] Procesando job ${jobId}: ${appName}`);

  try {
    const { hostId, hostSecret } = await createHostRecord(owner, appName);

    await fs.ensureDir(workDir);
    const iconPath = path.join(workDir, 'icon-source.png');
    await fs.writeFile(iconPath, iconData);

    await fs.copy(TEMPLATE_DIR, projectDir);
    await injectIcon(iconPath, projectDir);

    const isWindows = process.platform === 'win32';
    const wsUrl = process.env.WEBSOCKET_URL || 'ws://localhost:3000';

    // IMPORTANTE: NO anteponer "cmd /c" manualmente. execSync ya invoca cmd.exe
    // internamente en Windows; hacerlo dos veces rompe el quoting de rutas con espacios
    // (falla con "El nombre de archivo... no es correcto") y Gradle nunca llega a correr.
    const gradlewPath = isWindows ? path.join(projectDir, 'gradlew.bat') : path.join(projectDir, 'gradlew');
    // -PcontentUrl solo si el técnico puso una URL; si va vacío, la app no muestra WebView.
    const contentArg = contentUrl ? ` -PcontentUrl="${contentUrl}"` : '';
    const gradleCmd = `"${gradlewPath}" assembleRelease -PappName="${appName}" -PhostId="${hostId}" -PhostSecret="${hostSecret}" -PserverUrl="${wsUrl}"${contentArg}`;

    console.log(`[Worker] Conectando a: ${wsUrl}`);
    console.log(`[Worker] Ejecutando Gradle (2-3 minutos)...`);

    const env = { ...process.env, JAVA_HOME: process.env.JAVA_HOME };
    // Un fallo real de Gradle debe abortar el build — nunca firmar en silencio un APK
    // preexistente (eso enmascaró bugs de compilación en el pasado).
    execSync(gradleCmd, { cwd: projectDir, stdio: 'inherit', env });

    const unsignedApk = path.join(projectDir, 'app/build/outputs/apk/release/app-release-unsigned.apk');
    if (!(await fs.pathExists(unsignedApk))) {
      throw new Error(`APK sin firma no encontrado: ${unsignedApk}`);
    }

    const signedApk = path.join(workDir, 'app-signed.apk');
    const apksigner = process.env.APKSIGNER_PATH || 'apksigner';
    execSync(
      `"${apksigner}" sign --ks "${process.env.KEYSTORE_PATH}" ` +
      `--ks-pass pass:${process.env.KEYSTORE_PASS} ` +
      `--out "${signedApk}" "${unsignedApk}"`,
      { stdio: 'inherit' }
    );

    const apkBuffer = await fs.readFile(signedApk);
    if (apkBuffer.length < 10_000_000) {
      throw new Error(`APK inválido: solo ${apkBuffer.length} bytes`);
    }

    await markDone(jobId, apkBuffer);
    console.log(`[Worker] ✓ Build ${jobId} completado (${(apkBuffer.length / 1024 / 1024).toFixed(1)} MB)`);
  } catch (err) {
    console.error(`[Worker] Build ${jobId} falló: ${err.message}`);
    await markFailed(jobId, err.message);
  } finally {
    await fs.remove(workDir).catch(() => {});
  }
}

async function pollLoop() {
  console.log('[Worker] Escuchando build_jobs en Postgres...');
  for (;;) {
    try {
      const job = await claimNextJob();
      if (job) {
        await processJob(job);
        continue; // revisa inmediatamente si hay otro job en cola
      }
    } catch (err) {
      console.error('[Worker] Error en el ciclo de polling:', err.message);
    }
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
}

pollLoop();

process.on('SIGTERM', () => {
  console.log('Cerrando worker...');
  process.exit(0);
});
