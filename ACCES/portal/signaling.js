const { WebSocketServer } = require('ws');
const { pool } = require('./db/pool');
const { resolveSessionOwner } = require('./auth');
const { generateSessionId } = require('./sessionId');

function attachSignaling(httpServer) {
  console.log('[Signaling] Inicializando WebSocket...');

  // Crear WebSocketServer adjunto al HTTP server
  const wss = new WebSocketServer({ server: httpServer });

  // Todos los mapas en memoria van por deviceId (un teléfono concreto), no por hostId
  // (el APK), porque un mismo APK puede estar instalado en varios teléfonos a la vez.
  const hostsById = new Map();
  const hostIpById = new Map();
  const hostStatusById = new Map();
  const sessions = new Map();
  const clientState = new WeakMap();

  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  const send = (ws, message) => {
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(message));
  };

  const otherPeer = (session, ws) =>
    session.hostWs === ws ? session.controllerWs : session.hostWs;

  const handleMessage = async (ws, msg) => {
    try {
      switch (msg.type) {
        case 'register': {
          console.log(`[Signaling] Host registrando: ${msg.hostId?.substring(0, 8)}...`);

          try {
            const { rows } = await pool.query(
              'SELECT host_secret, friendly_name FROM hosts WHERE host_id = $1',
              [msg.hostId]
            );

            if (rows.length === 0) {
              console.warn(`[Signaling] ✗ Host no encontrado en BD`);
              send(ws, { type: 'error', message: 'Host no encontrado' });
              ws.close();
              return;
            }

            if (rows[0].host_secret !== msg.hostSecret) {
              console.warn(`[Signaling] ✗ Secret incorrecto`);
              send(ws, { type: 'error', message: 'Credenciales inválidas' });
              ws.close();
              return;
            }

            // APKs viejos no mandan deviceId: se usa el hostId como dispositivo único.
            const deviceId = UUID_RE.test(msg.deviceId || '') ? msg.deviceId.toLowerCase() : msg.hostId;
            const deviceModel = typeof msg.deviceModel === 'string' ? msg.deviceModel.slice(0, 80) : null;

            // Nombre inicial: "<APK> · <modelo>" para distinguir teléfonos; el técnico lo puede
            // renombrar desde el portal y el rename se conserva (no se pisa en cada registro).
            const defaultName = deviceModel ? `${rows[0].friendly_name} · ${deviceModel}` : rows[0].friendly_name;
            const { rows: devRows } = await pool.query(
              `INSERT INTO devices (device_id, host_id, friendly_name, device_model, last_seen_at)
               VALUES ($1, $2, $3, $4, now())
               ON CONFLICT (device_id) DO UPDATE
                 SET device_model = COALESCE(EXCLUDED.device_model, devices.device_model),
                     last_seen_at = now()
               RETURNING friendly_name`,
              [deviceId, msg.hostId, defaultName, deviceModel]
            );

            // Si el mismo teléfono reconecta antes de que se cierre el socket viejo, se descarta el viejo.
            const previous = hostsById.get(deviceId);
            if (previous && previous !== ws) {
              clientState.delete(previous);
              try { previous.close(); } catch { /* ya cerrado */ }
            }

            console.log(`[Signaling] ✓ Registrado: ${devRows[0].friendly_name} (device ${deviceId.substring(0, 8)}...)`);
            hostsById.set(deviceId, ws);
            if (ws.remoteIp) hostIpById.set(deviceId, ws.remoteIp);
            clientState.set(ws, { role: 'host', hostId: msg.hostId, deviceId });

            pool.query('UPDATE hosts SET last_seen_at = now() WHERE host_id = $1', [msg.hostId])
              .catch(e => console.error('Error updating last_seen_at:', e.message));

            send(ws, {
              type: 'registered',
              hostId: msg.hostId,
              deviceId,
              friendlyName: devRows[0].friendly_name
            });
            break;
          } catch (dbErr) {
            console.error(`[Signaling] Error BD: ${dbErr.message}`);
            send(ws, { type: 'error', message: `Error BD: ${dbErr.message}` });
            ws.close();
          }
          break;
        }

        case 'host-status': {
          const state = clientState.get(ws);
          if (state && state.role === 'host' && state.deviceId) {
            hostStatusById.set(state.deviceId, {
              accessibilityEnabled: !!msg.accessibilityEnabled,
              screenOn: !!msg.screenOn,
              appLabel: typeof msg.appLabel === 'string' ? msg.appLabel : '',
            });
          }
          break;
        }

        case 'connect-request': {
          console.log(`[Signaling] connect-request: hostId=${msg.hostId?.substring(0, 8)}..., ownerToken=${msg.ownerToken ? msg.ownerToken.substring(0, 16) + '...' : 'NONE'}`);
          const owner = await resolveSessionOwner(msg.ownerToken);
          if (!owner) {
            console.warn(`[Signaling] ✗ connect-request rechazado: token no resuelve a ningún owner`);
            send(ws, { type: 'error', message: 'No autenticado' });
            return;
          }
          // msg.hostId aquí es el deviceId (lo que lista /api/hosts y usa host.php).
          const { rows } = await pool.query(
            'SELECT h.owner FROM devices d JOIN hosts h ON h.host_id = d.host_id WHERE d.device_id = $1',
            [msg.hostId]
          );
          if (rows.length === 0 || rows[0].owner !== owner) {
            console.warn(`[Signaling] ✗ connect-request rechazado: host no encontrado o pertenece a otro owner (owner=${owner})`);
            send(ws, { type: 'error', message: 'Host no encontrado' });
            return;
          }
          const hostWs = hostsById.get(msg.hostId);
          if (!hostWs) {
            console.warn(`[Signaling] ✗ connect-request rechazado: host desconectado`);
            send(ws, { type: 'error', message: 'Host desconectado' });
            return;
          }
          // Si este host ya tenía una sesión en curso (p. ej. el técnico recargó la página o
          // reintentó "Conectar" varias veces), se cierra primero para que quede una sola
          // sesión válida — evita que controlador y host queden sincronizados con sessionIds
          // distintos, que es lo que hacía que los botones de control dejaran de responder.
          for (const [oldSessionId, oldSession] of sessions) {
            if (oldSession.hostWs === hostWs) {
              console.log(`[Signaling] Cerrando sesión anterior del mismo host: ${oldSessionId}`);
              send(oldSession.controllerWs, { type: 'peer-disconnected', sessionId: oldSessionId });
              sessions.delete(oldSessionId);
            }
          }
          const sessionId = generateSessionId();
          sessions.set(sessionId, { hostWs, controllerWs: ws, accepted: false });
          clientState.set(ws, { role: 'controller', sessionId });
          send(hostWs, { type: 'incoming-request', sessionId });
          send(ws, { type: 'request-sent', sessionId });
          console.log(`[Signaling] ✓ connect-request enviado al host, sessionId=${sessionId}`);
          break;
        }

        case 'respond-request': {
          const session = sessions.get(msg.sessionId);
          if (!session || session.hostWs !== ws) {
            send(ws, { type: 'error', message: 'Sesión inválida' });
            return;
          }
          if (msg.accept) {
            session.accepted = true;
            send(session.controllerWs, { type: 'request-accepted', sessionId: msg.sessionId });
          } else {
            send(session.controllerWs, { type: 'request-rejected', sessionId: msg.sessionId });
            sessions.delete(msg.sessionId);
          }
          break;
        }

        case 'signal': {
          const session = sessions.get(msg.sessionId);
          if (!session || !session.accepted) {
            send(ws, { type: 'error', message: 'Sesión inválida' });
            return;
          }
          send(otherPeer(session, ws), { type: 'signal', sessionId: msg.sessionId, data: msg.data });
          break;
        }

        // "Video a texto": canal de respaldo, INDEPENDIENTE de la conexión WebRTC (video +
        // datachannel). Va por este WebSocket de señalización, que se mantiene vivo aunque la
        // transmisión de pantalla se congele o la sesión WebRTC entera se caiga — así, mientras
        // uno de los dos métodos no sirva, el otro sigue funcionando. controller -> host.
        case 'text-command': {
          const session = sessions.get(msg.sessionId);
          if (!session || !session.accepted) {
            send(ws, { type: 'error', message: 'Sesión inválida' });
            return;
          }
          send(session.hostWs, { type: 'text-command', sessionId: msg.sessionId, data: msg.data });
          break;
        }

        // Respuesta del host (lectura de pantalla en texto) de vuelta al controller. host -> controller.
        case 'text-response': {
          const session = sessions.get(msg.sessionId);
          if (!session || !session.accepted) return;
          send(session.controllerWs, { type: 'text-response', sessionId: msg.sessionId, data: msg.data });
          break;
        }

        case 'end-session': {
          const session = sessions.get(msg.sessionId);
          if (session) {
            send(otherPeer(session, ws), { type: 'peer-disconnected', sessionId: msg.sessionId });
            sessions.delete(msg.sessionId);
          }
          break;
        }

        default:
          send(ws, { type: 'error', message: 'Tipo desconocido' });
      }
    } catch (err) {
      console.error(`[Signaling] Error: ${err.message}`);
      send(ws, { type: 'error', message: 'Error interno' });
    }
  };

  const handleDisconnect = (ws) => {
    const state = clientState.get(ws) || {};

    if (state.role === 'host' && state.deviceId) {
      // Solo se limpia si este socket sigue siendo el vigente para el dispositivo
      // (si reconectó, el nuevo socket ya reemplazó al viejo en el mapa).
      if (hostsById.get(state.deviceId) === ws) {
        hostsById.delete(state.deviceId);
        hostIpById.delete(state.deviceId);
        hostStatusById.delete(state.deviceId);
      }
      pool.query('UPDATE devices SET last_seen_at = now() WHERE device_id = $1', [state.deviceId])
        .catch(e => console.error('Error updating offline:', e.message));
    }

    for (const [sessionId, session] of sessions) {
      if (session.hostWs === ws || session.controllerWs === ws) {
        send(otherPeer(session, ws), { type: 'peer-disconnected', sessionId });
        sessions.delete(sessionId);
      }
    }

    clientState.delete(ws);
  };

  wss.on('connection', (ws, req) => {
    const forwarded = (req.headers['x-forwarded-for'] || '').split(',')[0].trim();
    ws.remoteIp = forwarded || req.socket.remoteAddress || null;
    clientState.set(ws, {});

    console.log(`[Signaling] Nueva conexión desde ${ws.remoteIp}`);

    ws.on('message', (raw) => {
      let msg;
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        send(ws, { type: 'error', message: 'JSON inválido' });
        return;
      }
      handleMessage(ws, msg).catch((err) => {
        console.error('[Signaling] Error manejando mensaje:', err.message);
        send(ws, { type: 'error', message: 'Error interno del servidor' });
      });
    });

    ws.on('close', () => handleDisconnect(ws));
    ws.on('error', (err) => console.error('[Signaling] Socket error:', err.message));
  });

  wss.on('error', (err) => {
    console.error('[Signaling] WebSocketServer error:', err.message);
  });

  console.log('[Signaling] ✓ WebSocket iniciado correctamente');

  return {
    isHostOnline: (hostId) => hostsById.has(hostId),
    getHostIp: (hostId) => hostIpById.get(hostId) || null,
    getHostStatus: (hostId) => hostStatusById.get(hostId) || null,
  };
}

module.exports = { attachSignaling };
