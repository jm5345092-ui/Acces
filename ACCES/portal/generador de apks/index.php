<?php
require_once __DIR__ . '/lib/functions.php';

$jobs    = list_jobs();
$active  = preg_replace('/[^a-z0-9_]/', '', $_GET['job'] ?? '');
$error   = $_GET['error'] ?? '';
$baseUrl = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? 'https' : 'http')
         . '://' . $_SERVER['HTTP_HOST'] . rtrim(dirname($_SERVER['SCRIPT_NAME']), '/\\') . '/';

// Estilos e includes compartidos del portal ACCES (misma carpeta padre)
$portalDir = dirname(__DIR__) . '/public';
$portalUrl = '../public/';

function h($s): string { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function fmt_size(int $b): string { return $b > 1048576 ? round($b / 1048576, 1) . ' MB' : round($b / 1024) . ' KB'; }
function badge_class(string $status): string {
    return match ($status) {
        'DONE'            => 'status-badge--online',
        'RUNNING', 'QUEUED' => 'status-badge--running',
        'ERROR'           => 'status-badge--error',
        default           => 'status-badge--offline',
    };
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generador de Apps - ACCES</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="<?= h($portalUrl) ?>assets/css/style.css">
    <style>
        /* Extras propios del generador, sobre el style.css de ACCES */
        .wrap { max-width: 820px; }

        .color-row {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        #build-form input[type="color"] {
            width: 56px;
            height: 40px;
            padding: 3px;
            border-radius: 4px;
            border: 1px solid var(--neon-dim);
            background: rgba(0, 255, 65, 0.05);
            cursor: pointer;
        }

        #build-form input[type="color"]:focus {
            outline: none;
            border-color: var(--neon);
            box-shadow: 0 0 10px var(--neon-faint);
        }

        .color-text {
            font-size: 0.9rem;
            color: var(--text);
            opacity: 0.75;
            letter-spacing: 1px;
        }

        .hint {
            display: block;
            margin-top: 6px;
            font-size: 0.78rem;
            color: var(--text);
            opacity: 0.55;
            line-height: 1.5;
        }

        .file-preview img { background: #fff; }

        .build-log {
            margin-top: 12px;
            padding: 12px 14px;
            max-height: 300px;
            overflow: auto;
            border: 1px solid var(--neon-dim);
            border-radius: 4px;
            background: rgba(0, 0, 0, 0.55);
            color: var(--text);
            font-family: inherit;
            font-size: 0.78rem;
            line-height: 1.45;
            white-space: pre-wrap;
            word-break: break-all;
        }

        .done-box {
            display: none;
            gap: 20px;
            align-items: flex-start;
            flex-wrap: wrap;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid var(--neon-dim);
        }

        .done-box.visible { display: flex; }

        #qr {
            padding: 8px;
            background: #fff;
            border-radius: 4px;
            line-height: 0;
        }

        .done-box code {
            display: inline-block;
            margin-top: 4px;
            color: var(--neon);
            word-break: break-all;
        }

        .apps-section { margin-top: 36px; }

        .apps-section h2 {
            font-size: 1rem;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--neon);
            text-shadow: 0 0 8px var(--neon-dim);
        }

        .apps-section h2::before { content: "> "; }

        .hosts-table { font-size: 0.9rem; }
        .hosts-table td { vertical-align: middle; }
        .hosts-table a { color: var(--neon); text-decoration: none; }
        .hosts-table a:hover { text-decoration: underline; }
        .hosts-table .pkg { display: block; font-size: 0.75rem; opacity: 0.55; }
        .hosts-table .size { font-size: 0.75rem; opacity: 0.55; }

        .status-badge--running {
            color: #ffd166;
            border: 1px solid rgba(255, 209, 102, 0.6);
            box-shadow: 0 0 8px rgba(255, 209, 102, 0.15);
        }

        .status-badge--error {
            color: #ff6b81;
            border: 1px solid rgba(255, 45, 85, 0.5);
        }

        .table-scroll { overflow-x: auto; }

        .empty { opacity: 0.6; margin-top: 16px; }
    </style>
</head>
<body>
    <?php require $portalDir . '/includes/bg_decor.php'; ?>
    <nav class="top-menu">
        <span class="top-menu__brand">ACCES</span>
        <div class="top-menu__links">
            <a href="index.php" class="active">Generador</a>
            <a href="<?= h($portalUrl) ?>dashboard.php">Portal</a>
        </div>
    </nav>

    <div class="wrap">
        <span class="eyebrow">Nueva app</span>
        <h1>Generador de Apps</h1>
        <p class="subtitle">
            Convierte la página web de un emprendimiento en una app Android instalable.
            Ingresa el nombre, la URL y un ícono; al terminar obtienes un APK firmado
            listo para compartir por enlace o QR.
        </p>

        <div class="panel">
            <?php if ($error): ?>
                <div class="error-msg"><?= h($error) ?></div>
            <?php endif; ?>

            <form id="build-form" method="post" action="build.php" enctype="multipart/form-data">
                <label for="name">Nombre de la aplicación</label>
                <input type="text" id="name" name="name" required minlength="2" maxlength="40" placeholder="Ej: Panadería La Espiga" autofocus>
                <span class="hint">Es el nombre que aparece debajo del ícono en el celular.</span>

                <label for="url">URL de la página web</label>
                <input type="url" id="url" name="url" required placeholder="https://laespiga.com">

                <label for="icon">Ícono de la app</label>
                <div class="file-drop" id="file-drop">
                    <input type="file" id="icon" name="icon" accept="image/png,image/jpeg" required>
                    <span class="file-drop-text">Arrastra una imagen o haz clic para elegirla</span>
                </div>
                <div class="file-preview" id="file-preview">
                    <img id="file-preview-img" alt="">
                    <span id="file-preview-name"></span>
                </div>
                <span class="hint">PNG o JPG cuadrado, mínimo 192×192 px (recomendado 512×512). Si tiene fondo transparente se verá con el color de abajo.</span>

                <label for="color">Color de fondo del ícono y de la barra de estado</label>
                <div class="color-row">
                    <input type="color" id="color" name="color" value="#FFFFFF">
                    <span class="color-text" id="color-text">#FFFFFF</span>
                </div>

                <button type="submit" id="submit-btn">Generar APK</button>
            </form>

            <div class="status" id="status">
                <div class="status-row">
                    <span class="dot" id="status-dot"></span>
                    <span class="status-label" id="status-label">Encolando…</span>
                </div>
                <div class="status-detail" id="status-detail"></div>
                <pre class="build-log" id="log" hidden></pre>
                <div class="done-box" id="done-box">
                    <div id="qr"></div>
                    <div>
                        <p><strong>APK listo</strong> <span id="apk-size"></span></p>
                        <a class="download-link" id="apk-link" href="#">Descargar APK</a>
                        <span class="hint">Escanea el QR desde el celular (misma red Wi‑Fi) o comparte el enlace:<br><code id="apk-url"></code></span>
                        <span class="hint">Al instalar, Android pedirá permitir "instalar apps de origen desconocido".</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="apps-section">
            <h2>Apps generadas</h2>
            <?php if (!$jobs): ?>
                <p class="empty">Todavía no has generado ninguna app.</p>
            <?php else: ?>
            <div class="table-scroll">
            <table class="hosts-table">
                <thead><tr><th>App</th><th>URL</th><th>Estado</th><th>APK</th><th></th></tr></thead>
                <tbody>
                <?php foreach ($jobs as $j): ?>
                    <tr>
                        <td><?= h($j['name']) ?><span class="pkg"><?= h($j['package']) ?> · v<?= h($j['versionName']) ?></span></td>
                        <td><a href="<?= h($j['url']) ?>" target="_blank" rel="noopener"><?= h($j['url']) ?></a></td>
                        <td><span class="status-badge <?= badge_class($j['status']) ?>"><?= h($j['status']) ?></span></td>
                        <td><?php if ($j['apk_exists']): ?><a href="apks/<?= h($j['slug']) ?>.apk"><?= h($j['slug']) ?>.apk</a> <span class="size"><?= fmt_size($j['apk_size']) ?></span><?php else: ?>—<?php endif; ?></td>
                        <td><a href="index.php?job=<?= h($j['slug']) ?>" class="btn btn--small">Ver</a></td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
            </div>
            <?php endif; ?>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <script>
        const BASE_URL = <?= json_encode($baseUrl) ?>;

        const form = document.getElementById('build-form');
        const iconInput = document.getElementById('icon');
        const fileDrop = document.getElementById('file-drop');
        const filePreview = document.getElementById('file-preview');
        const filePreviewImg = document.getElementById('file-preview-img');
        const filePreviewName = document.getElementById('file-preview-name');
        const colorInput = document.getElementById('color');
        const colorText = document.getElementById('color-text');
        const submitBtn = document.getElementById('submit-btn');
        const statusBox = document.getElementById('status');
        const statusDot = document.getElementById('status-dot');
        const statusLabel = document.getElementById('status-label');
        const statusDetail = document.getElementById('status-detail');
        const logBox = document.getElementById('log');
        const doneBox = document.getElementById('done-box');

        // Vista previa del ícono y del color
        iconInput.addEventListener('change', () => {
            const file = iconInput.files[0];
            if (!file) { filePreview.style.display = 'none'; return; }
            filePreviewImg.src = URL.createObjectURL(file);
            filePreviewName.textContent = file.name;
            filePreview.style.display = 'flex';
        });

        colorInput.addEventListener('input', () => {
            colorText.textContent = colorInput.value.toUpperCase();
            filePreviewImg.style.background = colorInput.value;
        });

        ['dragover', 'dragenter'].forEach((evt) =>
            fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.add('dragover'); })
        );
        ['dragleave', 'drop'].forEach((evt) =>
            fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.remove('dragover'); })
        );
        fileDrop.addEventListener('drop', (e) => {
            if (e.dataTransfer.files[0]) {
                iconInput.files = e.dataTransfer.files;
                iconInput.dispatchEvent(new Event('change'));
            }
        });

        function setStatus(label, detail, kind) {
            statusBox.classList.add('visible');
            statusLabel.textContent = label;
            statusDetail.textContent = detail || '';
            statusDot.className = 'dot' + (kind ? ' ' + kind : '');
        }

        function setBusy(busy) {
            submitBtn.disabled = busy;
            submitBtn.textContent = busy ? 'Procesando...' : 'Generar APK';
        }

        // Seguimiento de la compilación (consulta status.php cada 3 s)
        let timer = null, qrDone = false;

        async function pollJob(slug) {
            try {
                const res = await fetch('status.php?job=' + encodeURIComponent(slug), { cache: 'no-store' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const d = await res.json();

                logBox.hidden = false;
                const atBottom = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 20;
                logBox.textContent = d.log || '';
                if (atBottom) logBox.scrollTop = logBox.scrollHeight;

                if (d.status === 'DONE' && d.apk) {
                    setStatus('Listo', d.name, 'done');
                    const apkUrl = BASE_URL + d.apk;
                    document.getElementById('apk-link').href = apkUrl + '?v=' + Date.now();
                    document.getElementById('apk-url').textContent = apkUrl;
                    document.getElementById('apk-size').textContent = '(' + (d.apk_size / 1048576).toFixed(1) + ' MB)';
                    if (!qrDone) {
                        new QRCode(document.getElementById('qr'), { text: apkUrl, width: 140, height: 140 });
                        qrDone = true;
                    }
                    doneBox.classList.add('visible');
                    clearInterval(timer);
                    setBusy(false);
                    return;
                }
                if (d.status === 'ERROR') {
                    setStatus('Falló la compilación', d.name + ' — revisa el log.', 'failed');
                    clearInterval(timer);
                    setBusy(false);
                    return;
                }
                setStatus('Compilando…', d.name + ' · Esto puede tardar unos minutos.');
            } catch (err) {
                setStatus('Error', 'No se pudo consultar el estado: ' + err.message, 'failed');
                clearInterval(timer);
                setBusy(false);
            }
        }

        function trackJob(slug) {
            qrDone = false;
            doneBox.classList.remove('visible');
            document.getElementById('qr').innerHTML = '';
            history.replaceState(null, '', 'index.php?job=' + encodeURIComponent(slug));
            clearInterval(timer);
            pollJob(slug);
            timer = setInterval(() => pollJob(slug), 3000);
        }

        // Envío del formulario sin recargar la página
        let isSubmitting = false;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (isSubmitting) return;

            isSubmitting = true;
            setBusy(true);
            logBox.hidden = true;
            doneBox.classList.remove('visible');
            setStatus('Encolando…', '');

            try {
                const res = await fetch('build.php', {
                    method: 'POST',
                    headers: { 'Accept': 'application/json' },
                    body: new FormData(form),
                });
                const data = await res.json();
                if (!res.ok || !data.ok) {
                    setStatus('Error', data.error || 'No se pudo encolar la compilación', 'failed');
                    isSubmitting = false;
                    setBusy(false);
                    return;
                }
                isSubmitting = false;
                trackJob(data.slug);
            } catch (err) {
                setStatus('Error de red', err.message, 'failed');
                isSubmitting = false;
                setBusy(false);
            }
        });

        const activeJob = <?= json_encode($active) ?>;
        if (activeJob) {
            setStatus('Cargando…', '');
            trackJob(activeJob);
        }
    </script>
</body>
</html>
