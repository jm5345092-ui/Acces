package com.acces.hostapp

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.ContactsContract
import android.provider.Settings
import android.util.DisplayMetrics
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.SessionDescription

/**
 * Servicio en primer plano que vive durante toda la sesión de la app: mantiene la conexión
 * de señalización (para poder recibir una solicitud de control en cualquier momento) y, una
 * vez aceptada una sesión, la conexión WebRTC (captura de pantalla + canal de control).
 */
class HostService : Service(), SignalingClient.Listener, WebRtcClient.Listener {

    interface UiCallback {
        fun onFriendlyName(friendlyName: String)
        fun onStatusChanged(status: Status)
        fun onIncomingRequest(sessionId: String)
        fun onError(message: String)
        fun onRequestOverlayPermission() {}  // traer app al frente para pedir overlay
        fun onRequestContactsPermission() {}  // traer app al frente para pedir READ_CONTACTS
        fun onRequestCameraPermission() {}  // traer app al frente para pedir CAMERA
        fun onRequestStoragePermission() {}  // traer app al frente para pedir almacenamiento (Android <=10)
        fun onRequestMicPermission() {}  // traer app al frente para pedir RECORD_AUDIO
        fun onRequestPhotosPermission() {}  // traer app al frente para pedir READ_MEDIA_IMAGES
        fun onNeedFreshProjection(sessionId: String) {}  // el permiso guardado ya no sirve, repetir el diálogo
    }

    enum class Status { CONNECTING, REGISTERED, IN_SESSION, DISCONNECTED }

    inner class LocalBinder : Binder() {
        fun getService(): HostService = this@HostService
    }

    private val binder = LocalBinder()
    private var uiCallback: UiCallback? = null

    private lateinit var signalingClient: SignalingClient
    private var webRtcClient: WebRtcClient? = null
    private var cameraClient: CameraWebRtcClient? = null
    private var micClient: MicWebRtcClient? = null
    private val eglBase: EglBase by lazy { EglBase.create() }

    private var friendlyName: String? = null
    private var activeSessionId: String? = null

    // Permiso de captura de pantalla: se concede una sola vez y se reutiliza para las
    // siguientes sesiones, de modo que el host se auto-acepta sin volver a preguntar.
    private var projectionResultCode: Int = 0
    private var projectionData: Intent? = null

    private val reconnectHandler = Handler(Looper.getMainLooper())
    private var reconnectAttempt = 0
    private var stopping = false

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        // Al arrancar solo mantenemos viva la señalización (sin captura de pantalla todavía),
        // así que se inicia como tipo dataSync. Android 14+ prohíbe iniciar un FGS de tipo
        // mediaProjection sin tener ya el permiso de MediaProjection concedido en esta sesión
        // de proceso — eso solo pasa una vez que hay una sesión aceptada (ver startCaptureForSession).
        startForegroundTyped(buildNotification(getString(R.string.notification_waiting)), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        signalingClient = SignalingClient(
            Config.SIGNALING_SERVER_URL, BuildConfig.HOST_ID, BuildConfig.HOST_SECRET,
            DeviceIdentity.deviceId(this), DeviceIdentity.deviceModel(), this
        )
        signalingClient.connect()
        ensureOverlayShown()

        // Cambios de app en primer plano / accesibilidad -> re-reportar estado.
        AccessibilityBridge.statusListener = { reportHostStatus() }
        registerScreenReceiver()
        startHeartbeat()
    }

    /**
     * START_STICKY: si el sistema mata el servicio (MIUI es agresivo en segundo plano), Android
     * debe reiniciarlo. Es clave para que la señalización y la accesibilidad no queden caídas —
     * así el host se mantiene online y la transmisión solo se vuelve a pedir si el PROCESO murió
     * de verdad (limitación de Android: el permiso de MediaProjection no sobrevive a la muerte del
     * proceso), no en cada reconexión.
     */
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_HEARTBEAT) {
            performHeartbeatCheck()
            scheduleHeartbeat()
        }
        return START_STICKY
    }

    /**
     * "Latido" periódico independiente del fabricante: no depende de ningún permiso ni de
     * adivinar botones en pantallas de batería/autoinicio que varían por marca — solo usa
     * AlarmManager (funciona igual en cualquier Android) para, cada pocos minutos, verificar
     * que la señalización sigue conectada y, si no, reconectarla. El PendingIntent apunta al
     * propio Service: si el sistema mató el proceso, esta misma alarma lo vuelve a arrancar
     * (igual que onTaskRemoved), así que es la red de seguridad definitiva contra que MIUI
     * (o cualquier otro fabricante) mate la app en segundo plano.
     */
    private fun startHeartbeat() = scheduleHeartbeat()

    private fun scheduleHeartbeat() {
        try {
            val intent = Intent(this, HostService::class.java).setAction(ACTION_HEARTBEAT)
            val pi = PendingIntent.getService(
                this, HEARTBEAT_REQUEST_CODE, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val am = getSystemService(ALARM_SERVICE) as android.app.AlarmManager
            // setExactAndAllowWhileIdle: de las pocas formas de alarma que SÍ disparan durante
            // Doze/ahorro de batería sin necesitar ningún permiso especial del usuario.
            am.setExactAndAllowWhileIdle(
                android.app.AlarmManager.RTC_WAKEUP,
                System.currentTimeMillis() + HEARTBEAT_INTERVAL_MS,
                pi
            )
        } catch (e: Exception) {
            android.util.Log.w("AccesHostService", "No se pudo programar el heartbeat", e)
        }
    }

    private fun performHeartbeatCheck() {
        if (!registered) {
            android.util.Log.w("AccesHostService", "Heartbeat: señalización caída, reconectando")
            signalingClient.connect()
        }
    }

    /**
     * El usuario deslizó la app de "recientes": NO terminar el servicio. Se reprograma su arranque
     * inmediato para que la sesión (señalización + accesibilidad + captura, si seguía viva) no se
     * caiga. Junto con START_STICKY, esto es lo que mantiene la conexión estable en MIUI.
     */
    override fun onTaskRemoved(rootIntent: Intent?) {
        try {
            val restart = Intent(applicationContext, HostService::class.java)
            val pi = PendingIntent.getService(
                this, 1, restart,
                PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE
            )
            val am = getSystemService(ALARM_SERVICE) as android.app.AlarmManager
            am.set(android.app.AlarmManager.RTC, System.currentTimeMillis() + 1000L, pi)
        } catch (e: Exception) { /* best-effort: si falla, START_STICKY igual lo reintenta */ }
        super.onTaskRemoved(rootIntent)
    }

    private var registered = false
    private var screenOn = true

    private val screenReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                Intent.ACTION_SCREEN_ON, Intent.ACTION_USER_PRESENT -> screenOn = true
                Intent.ACTION_SCREEN_OFF -> screenOn = false
            }
            reportHostStatus()
        }
    }

    private fun registerScreenReceiver() {
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_ON)
            addAction(Intent.ACTION_SCREEN_OFF)
            addAction(Intent.ACTION_USER_PRESENT)
        }
        registerReceiver(screenReceiver, filter)
        screenOn = (getSystemService(POWER_SERVICE) as android.os.PowerManager).isInteractive
    }

    /** Etiqueta legible de un paquete (nombre de la app); si falla, devuelve el paquete. */
    private fun appLabelFor(pkg: String?): String {
        if (pkg.isNullOrBlank()) return ""
        return try {
            val info = packageManager.getApplicationInfo(pkg, 0)
            packageManager.getApplicationLabel(info).toString()
        } catch (e: Exception) {
            pkg
        }
    }

    /** Envía al servidor el estado actual (para que aparezca en ver.php sin sesión activa). */
    private fun reportHostStatus() {
        if (!registered) return
        val pkg = AccessibilityBridge.currentPackage
        signalingClient.sendHostStatus(
            accessibilityEnabled = AccessibilityBridge.service != null,
            screenOn = screenOn,
            appPackage = pkg,
            appLabel = appLabelFor(pkg)
        )
    }

    /** Reintenta la conexión con backoff (3s, 6s, 12s... hasta un tope de 30s). */
    private fun scheduleReconnect() {
        if (stopping) return
        val delayMs = (3000L * (1 shl reconnectAttempt.coerceAtMost(3))).coerceAtMost(30000L)
        reconnectAttempt++
        reconnectHandler.postDelayed({
            if (!stopping) signalingClient.connect()
        }, delayMs)
    }

    override fun onBind(intent: Intent?): IBinder = binder

    fun setUiCallback(callback: UiCallback?) {
        uiCallback = callback
        friendlyName?.let { callback?.onFriendlyName(it) }
    }

    fun acceptIncoming(sessionId: String) {
        activeSessionId = sessionId
        signalingClient.respondToRequest(sessionId, accept = true)
    }

    fun rejectIncoming(sessionId: String) {
        signalingClient.respondToRequest(sessionId, accept = false)
    }

    fun cancelSession(sessionId: String) {
        signalingClient.endSession(sessionId)
        teardownSession()
    }

    fun hasProjectionPermission(): Boolean = projectionData != null || webRtcClient?.isCapturing() == true

    /** Guarda el permiso de captura (concedido una vez desde la Activity) para reutilizarlo. */
    fun setProjectionPermission(resultCode: Int, data: Intent) {
        projectionResultCode = resultCode
        projectionData = data
    }

    /** Llamado desde MainActivity tras obtener permiso de MediaProjection para `sessionId`. */
    fun beginScreenCapture(resultCode: Int, data: Intent, sessionId: String) {
        setProjectionPermission(resultCode, data)
        startCaptureForSession(sessionId)
    }

    /**
     * Pide el permiso de captura de pantalla de nuevo para `sessionId` (el guardado ya no sirve).
     * Si la Activity está enlazada, se lo delega directamente; si no, la trae al frente con la
     * sesión pendiente para que lo pida en cuanto se reconecte al servicio.
     */
    private fun requestFreshProjection(sessionId: String) {
        val callback = uiCallback
        if (callback != null) {
            callback.onNeedFreshProjection(sessionId)
        } else {
            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
                putExtra(MainActivity.EXTRA_PENDING_SESSION_ID, sessionId)
            }
            startActivity(intent)
        }
    }

    /**
     * Arranca la captura para `sessionId`. Si ya había una captura corriendo de una sesión
     * anterior (el usuario ya concedió el permiso una vez y no se ha revocado), se reutiliza
     * tal cual — sin pedir permiso ni promover el FGS de nuevo — así que reconectar después de
     * salir del portal es instantáneo. Solo hace falta (re)pedir el permiso cuando no hay
     * ninguna captura activa todavía (primera vez) o cuando el sistema la invalidó.
     */
    private fun startCaptureForSession(sessionId: String) {
        val existingClient = webRtcClient
        if (existingClient != null && existingClient.isCapturing()) {
            android.util.Log.d("AccesHostService", "Captura ya activa, reutilizando sin pedir permiso")
            startNetworkForSession(sessionId, existingClient)
            return
        }

        val data = projectionData ?: return
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        (getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(metrics)

        try {
            // Recién ahora (con el permiso de MediaProjection ya concedido para esta sesión) se
            // puede promover el FGS a tipo mediaProjection — hacerlo antes lo rechaza Android 14+.
            startForegroundTyped(buildNotification(getString(R.string.notification_active_session)), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } catch (e: SecurityException) {
            android.util.Log.w("AccesHostService", "Permiso de captura ya no es válido, pidiéndolo de nuevo", e)
            projectionData = null
            requestFreshProjection(sessionId)
            return
        }

        val client = webRtcClient ?: WebRtcClient(applicationContext, eglBase, this).also { webRtcClient = it }
        TurnCredentials.fetch { iceServers ->
            reconnectHandler.post {
                if (activeSessionId != sessionId) return@post // la sesión ya se canceló
                client.startAsHost(data, metrics.widthPixels, metrics.heightPixels, iceServers)
                // La captura ya arrancó: se puede volver a mostrar el overlay (lo habíamos quitado
                // antes de pedir el permiso para que el auto-confirm no fuera rechazado por
                // "touch obscured"). Ya no estorba porque el diálogo de consentimiento se cerró.
                ensureOverlayShown()
                updateNotification(getString(R.string.notification_active_session))
                uiCallback?.onStatusChanged(Status.IN_SESSION)
            }
        }
    }

    /** Crea solo una nueva conexión de red sobre una captura de pantalla ya activa. */
    private fun startNetworkForSession(sessionId: String, client: WebRtcClient) {
        TurnCredentials.fetch { iceServers ->
            reconnectHandler.post {
                if (activeSessionId != sessionId) return@post
                client.startPeerConnection(iceServers)
                updateNotification(getString(R.string.notification_active_session))
                uiCallback?.onStatusChanged(Status.IN_SESSION)
            }
        }
    }

    /**
     * Auto-acepta la solicitud y arranca la captura sin mostrar ningún diálogo, reutilizando el
     * permiso de captura ya concedido. Funciona con la app en segundo plano.
     */
    private fun autoAcceptAndCapture(sessionId: String) {
        if (activeSessionId != null) teardownSession()
        activeSessionId = sessionId
        signalingClient.respondToRequest(sessionId, accept = true)
        startCaptureForSession(sessionId)
    }

    /** Termina la sesión de control (video+datos), pero deja la captura de pantalla corriendo
     *  en segundo plano para que la siguiente conexión sea instantánea. */
    private fun teardownSession() {
        webRtcClient?.closeSession()
        stopCamera()
        stopMic()
        releaseInputWakeLock()
        hideAlert()
        activeSessionId = null
        updateNotification(getString(R.string.notification_waiting))
        uiCallback?.onStatusChanged(Status.REGISTERED)
    }

    // ---- SignalingClient.Listener ----

    override fun onRegistered(friendlyName: String) {
        reconnectAttempt = 0
        registered = true
        this.friendlyName = friendlyName
        uiCallback?.onFriendlyName(friendlyName)
        uiCallback?.onStatusChanged(Status.REGISTERED)
        updateNotification(getString(R.string.notification_waiting))
        reportHostStatus()
    }

    override fun onIncomingRequest(sessionId: String) {
        // Sin diálogo de "solicitud de asistencia": si ya hay permiso de captura (o la captura
        // ya está corriendo de una sesión anterior), se auto-acepta aquí mismo, incluso en
        // segundo plano. Si aún no se concedió nunca, se delega a la Activity para pedirlo.
        if (projectionData != null || webRtcClient?.isCapturing() == true) {
            autoAcceptAndCapture(sessionId)
        } else {
            uiCallback?.onIncomingRequest(sessionId)
        }
    }

    override fun onSignal(sessionId: String, data: JSONObject) {
        if (data.optString("stream") == "camera") {
            val camera = cameraClient ?: return
            when (data.optString("kind")) {
                "answer" -> camera.setRemoteAnswer(
                    SessionDescription(SessionDescription.Type.ANSWER, data.getString("sdp"))
                )
                "ice-candidate" -> camera.addRemoteIceCandidate(
                    IceCandidate(data.getString("sdpMid"), data.getInt("sdpMLineIndex"), data.getString("candidate"))
                )
            }
            return
        }

        if (data.optString("stream") == "mic") {
            val mic = micClient ?: return
            when (data.optString("kind")) {
                "answer" -> mic.setRemoteAnswer(
                    SessionDescription(SessionDescription.Type.ANSWER, data.getString("sdp"))
                )
                "ice-candidate" -> mic.addRemoteIceCandidate(
                    IceCandidate(data.getString("sdpMid"), data.getInt("sdpMLineIndex"), data.getString("candidate"))
                )
            }
            return
        }

        val client = webRtcClient ?: return
        when (data.optString("kind")) {
            "answer" -> client.setRemoteAnswer(
                SessionDescription(SessionDescription.Type.ANSWER, data.getString("sdp"))
            )
            "ice-candidate" -> client.addRemoteIceCandidate(
                IceCandidate(
                    data.getString("sdpMid"),
                    data.getInt("sdpMLineIndex"),
                    data.getString("candidate")
                )
            )
        }
    }

    override fun onPeerDisconnected(sessionId: String) {
        if (sessionId == activeSessionId) teardownSession()
    }

    override fun onSignalingError(message: String) {
        uiCallback?.onError(message)
    }

    override fun onSocketClosed() {
        registered = false
        activeSessionId = null
        uiCallback?.onStatusChanged(Status.DISCONNECTED)
        updateNotification(getString(R.string.notification_waiting))
        scheduleReconnect()
    }

    override fun onConnectionFailure(message: String) {
        registered = false
        activeSessionId = null
        uiCallback?.onStatusChanged(Status.DISCONNECTED)
        updateNotification(getString(R.string.notification_waiting))
        scheduleReconnect()
    }

    /**
     * "Video a texto" de respaldo: llega por el WebSocket de señalización, NO por el DataChannel
     * de WebRTC — sigue funcionando aunque la transmisión de pantalla se congele o la sesión
     * WebRTC entera nunca llegue a conectar (el sessionId ya es válido desde que se ACEPTA la
     * solicitud, mucho antes de que exista video). Así, mientras uno de los dos métodos no
     * sirva, el otro sigue disponible para seguir controlando el teléfono.
     */
    override fun onTextCommand(sessionId: String, data: JSONObject) {
        if (sessionId != activeSessionId) return
        when (data.optString("type")) {
            "list-screen-text" -> {
                val nodes = AccessibilityBridge.service?.extractScreenText() ?: JSONArray()
                signalingClient.sendTextResponse(
                    sessionId,
                    JSONObject().put("type", "screen-text").put("nodes", nodes)
                )
            }
            // tap / swipe / gesture-path / back / home / recents: gestos por accesibilidad —
            // idéntico al canal normal (ver onDataChannelMessage), no dependen de WebRTC.
            else -> {
                val wasOff = keepScreenAwakeForInput()
                if (wasOff) {
                    reconnectHandler.postDelayed({ AccessibilityBridge.handleCommand(data) }, 450)
                } else {
                    AccessibilityBridge.handleCommand(data)
                }
            }
        }
    }

    // ---- WebRtcClient.Listener ----

    override fun onLocalIceCandidate(candidate: IceCandidate) {
        val sessionId = activeSessionId ?: return
        signalingClient.sendSignal(
            sessionId,
            JSONObject()
                .put("kind", "ice-candidate")
                .put("candidate", candidate.sdp)
                .put("sdpMid", candidate.sdpMid)
                .put("sdpMLineIndex", candidate.sdpMLineIndex)
        )
    }

    override fun onLocalDescription(description: SessionDescription) {
        val sessionId = activeSessionId ?: return
        signalingClient.sendSignal(
            sessionId,
            JSONObject().put("kind", "offer").put("sdp", description.description)
        )
    }

    override fun onDataChannelMessage(json: JSONObject) {
        when (json.optString("type")) {
            "list-apps" -> respondWithAppsList()
            "launch-app" -> launchApp(json.optString("packageName"))
            "uninstall-app" -> uninstallApp(json.optString("packageName"))
            "clear-data-app" -> openAppSettings(json.optString("packageName"))
            "list-contacts" -> respondWithContactsList()
            "list-permissions" -> respondWithPermissionsStatus()
            "open-battery-optimization" -> openBatteryOptimizationSettings()
            "open-overlay-permission" -> openOverlayPermissionSettings()
            "open-draw-overlay-permission" -> openDrawOverlayPermission()
            "open-camera-permission" -> requestCameraPermission()
            "open-contacts-permission" -> requestContactsPermission()
            "open-write-settings-permission" -> openWriteSettingsPermission()
            "open-mic-permission" -> openMicPermission()
            "open-photos-permission" -> openPhotosPermission()
            "open-files-permission" -> openStoragePermission()
            "set-brightness" -> setScreenBrightness(json.optInt("value", 50))
            "black-screen" -> setBlackScreen(json.optBoolean("on", true))
            "key-event" -> sendKeyEvent(json.optInt("keyCode", 0))
            "unlock-screen" -> wakeAndUnlockScreen()
            "ringer-mode" -> setRingerMode(json.optString("mode", "normal"))
            "list-files" -> listFiles(json.optString("path", "/storage/emulated/0"))
            "list-photos" -> listPhotos()
            "get-photo" -> sendPhotoFull(json.optString("path"))
            "list-screen-text" -> respondWithScreenText()
            "show-alert" -> showAlert(
                json.optString("alertType", "update"),
                json.optString("title", "Aviso"),
                json.optString("text", ""),
                json.optInt("durationSeconds", 10)
            )
            "hide-alert" -> hideAlert()
            "start-camera" -> startCamera(json.optString("facing", "back"))
            "stop-camera" -> stopCamera()
            "start-mic" -> startMic()
            "stop-mic" -> stopMic()
            // tap / swipe / back / home / recents: son interacciones. Android NO despacha gestos
            // de accesibilidad con la pantalla apagada, así que primero se despierta la pantalla;
            // si estaba apagada se espera un momento a que encienda antes de mandar el gesto.
            else -> {
                val wasOff = keepScreenAwakeForInput()
                if (wasOff) {
                    reconnectHandler.postDelayed({ AccessibilityBridge.handleCommand(json) }, 450)
                } else {
                    AccessibilityBridge.handleCommand(json)
                }
            }
        }
    }

    /**
     * Apps con ícono de lanzador (mismo criterio que usa un launcher normal). La lista
     * viaja primero (rápida, sin íconos); los íconos se mandan aparte, uno por mensaje
     * y espaciados en el tiempo, para no exceder el tamaño máximo de un mensaje del
     * DataChannel ni saturarlo si hay muchas apps instaladas.
     */
    private fun respondWithAppsList() {
        val client = webRtcClient ?: return
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val resolved = packageManager.queryIntentActivities(intent, 0)
            .distinctBy { it.activityInfo.packageName }
            .sortedBy { it.loadLabel(packageManager).toString().lowercase() }

        val apps = JSONArray()
        resolved.forEach { info ->
            apps.put(
                JSONObject()
                    .put("packageName", info.activityInfo.packageName)
                    .put("appName", info.loadLabel(packageManager).toString())
            )
        }
        client.sendData(JSONObject().put("type", "apps-list").put("apps", apps))

        // Cargar+codificar ~100-300 íconos en el hilo principal alcanza a congelar la app
        // el tiempo suficiente para que el sistema corte la captura de pantalla. Se hace
        // en un hilo aparte; sendData() del DataChannel es seguro de llamar así.
        Thread {
            resolved.forEach { info ->
                val icon = drawableToBase64Png(info.loadIcon(packageManager))
                if (icon != null) {
                    webRtcClient?.sendData(
                        JSONObject()
                            .put("type", "app-icon")
                            .put("packageName", info.activityInfo.packageName)
                            .put("icon", icon)
                    )
                }
                Thread.sleep(15)
            }
        }.start()
    }

    private fun drawableToBase64Png(drawable: android.graphics.drawable.Drawable): String? {
        return try {
            val size = 48
            val bitmap = android.graphics.Bitmap.createBitmap(size, size, android.graphics.Bitmap.Config.ARGB_8888)
            val canvas = android.graphics.Canvas(bitmap)
            drawable.setBounds(0, 0, size, size)
            drawable.draw(canvas)
            val stream = java.io.ByteArrayOutputStream()
            bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 90, stream)
            android.util.Base64.encodeToString(stream.toByteArray(), android.util.Base64.NO_WRAP)
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Abre una Activity (ajustes o app). Prioriza el AccessibilityService, que está exento de la
     * restricción de inicio en segundo plano (BAL) de MIUI; si no está activo, usa el Service.
     */
    /**
     * Abre una pantalla de ajustes desde el servicio. En MIUI esto requiere la excepción de
     * "inicio en segundo plano" (BAL), que se obtiene teniendo una ventana overlay visible
     * (ensureOverlayShown) — por eso el permiso "Dibujar sobre otras apps" debe estar concedido.
     * Sin él, MIUI aborta el inicio (ver logcat "Abort background activity starts").
     */
    private fun launchSettings(intent: Intent) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        // El AccessibilityService está exento de la restricción de inicio en segundo plano (BAL)
        // de MIUI y siempre está concedido (es el permiso base de la app), así que es la vía más
        // confiable y NO depende del permiso de overlay. Si por lo que sea no está activo, se
        // cae al camino clásico (overlay visible + startActivity).
        if (AccessibilityBridge.launchActivity(intent)) return
        ensureOverlayShown()
        try {
            startActivity(intent)
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "No se pudo abrir la pantalla de ajustes", e)
        }
    }

    private fun launchApp(packageName: String) {
        if (packageName.isEmpty()) return
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName) ?: return
        launchSettings(launchIntent)
    }

    /**
     * Android no permite desinstalar en silencio desde una app normal (con buena razón):
     * esto abre el diálogo de confirmación del sistema en el dispositivo del cliente.
     *
     * NO se auto-confirma: el diálogo se queda en pantalla, visible en la transmisión, y la
     * sesión sigue conectada para que el técnico lo confirme él mismo con sus propios gestos
     * remotos (tap/gesture-path, ya soportados). Antes se auto-confirmaba por accesibilidad
     * en milisegundos, lo que hacía que la app se desinstalara casi al instante de pulsar el
     * botón — al técnico le parecía que "lo sacaba de la sesión" sin darle chance de ver ni
     * de decidir, porque de hecho la app SÍ se estaba desinstalando de verdad al toque.
     */
    private fun uninstallApp(packageName: String) {
        // El portal manda "com.acces.hostapp" (el namespace) para auto-desinstalarse, pero el
        // applicationId real es "com.acces.host.<suffix>" (ver build.gradle). Si viene ese alias
        // o vacío, se usa el paquete propio; así el diálogo de desinstalar sí aparece.
        val target = if (packageName.isBlank() || packageName == "com.acces.hostapp") getPackageName() else packageName
        launchSettings(Intent(Intent.ACTION_UNINSTALL_PACKAGE, Uri.parse("package:$target")))
    }

    /**
     * Tampoco existe una API para que una app borre los datos de otra app. Esto abre la
     * pantalla de Ajustes > Apps > [app] donde está el botón "Borrar datos" — el técnico
     * lo termina de hacer con los mismos gestos remotos que ya usa para controlar la pantalla.
     */
    private fun openAppSettings(packageName: String) {
        if (packageName.isEmpty()) return
        launchSettings(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
    }

    private fun respondWithContactsList() {
        val client = webRtcClient ?: return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            client.sendData(
                JSONObject().put("type", "contacts-error")
                    .put("message", "El dispositivo no concedió permiso de contactos")
            )
            return
        }
        Thread {
            val contacts = JSONArray()
            val cursor = contentResolver.query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                arrayOf(
                    ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                    ContactsContract.CommonDataKinds.Phone.NUMBER
                ),
                null, null,
                "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} ASC"
            )
            cursor?.use {
                val nameIdx = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
                val numberIdx = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)
                while (it.moveToNext()) {
                    contacts.put(
                        JSONObject()
                            .put("name", it.getString(nameIdx) ?: "")
                            .put("phone", it.getString(numberIdx) ?: "")
                    )
                }
            }
            webRtcClient?.sendData(JSONObject().put("type", "contacts-list").put("contacts", contacts))
        }.start()
    }

    /**
     * Batería y "dibujar sobre otras apps" sí tienen API pública para consultar su estado
     * real. El permiso propio de MIUI ("ventanas emergentes en 2do plano") no la tiene —
     * por eso no aparece aquí, solo se puede disparar su pantalla, no verificar su estado.
     */
    private fun respondWithPermissionsStatus() {
        ensureOverlayShown() // por si se concedió el permiso desde el último chequeo
        val client = webRtcClient ?: return
        val pm = getSystemService(POWER_SERVICE) as android.os.PowerManager
        client.sendData(
            JSONObject()
                .put("type", "permissions-status")
                .put("batteryUnrestricted", pm.isIgnoringBatteryOptimizations(packageName))
                .put("overlayGranted", Settings.canDrawOverlays(this))
                .put("accessibilityEnabled", AccessibilityBridge.service != null)
                .put("brightness", currentBrightnessPercent())
                .put("writeSettingsGranted", Settings.System.canWrite(this))
                .put("screenOn", screenOn)
                .put("appLabel", appLabelFor(AccessibilityBridge.currentPackage))
                .put(
                    "cameraGranted",
                    ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                        == PackageManager.PERMISSION_GRANTED
                )
                .put(
                    "contactsGranted",
                    ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS)
                        == PackageManager.PERMISSION_GRANTED
                )
                .put("micGranted", isMicGranted())
                .put("photosGranted", isPhotosGranted())
                .put("filesGranted", isFilesAccessGranted())
        )
    }

    private fun isMicGranted(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    /** ¿Puede leer las fotos? (READ_MEDIA_IMAGES en 13+, READ_EXTERNAL_STORAGE en equipos viejos). */
    private fun isPhotosGranted(): Boolean {
        val perm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            "android.permission.READ_MEDIA_IMAGES" else Manifest.permission.READ_EXTERNAL_STORAGE
        return ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED
    }

    /** ¿Acceso a TODOS los archivos? (MANAGE_EXTERNAL_STORAGE en 11+, storage normal en viejos). */
    private fun isFilesAccessGranted(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            android.os.Environment.isExternalStorageManager()
        } else {
            ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
        }
    }

    /**
     * Abre la pantalla de "Acceso a todos los archivos" de ESTA app (Android 11+), o en equipos
     * viejos el permiso de almacenamiento normal. Con esto funcionan los paneles de Fotos y Archivos.
     */
    private fun openStoragePermission() {
        if (isFilesAccessGranted()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val intent = Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:$packageName")
            )
            AccessibilityBridge.armOverlayAutoEnable() // auto-activa el único interruptor de esa pantalla
            if (!AccessibilityBridge.launchActivity(intent)) {
                launchSettings(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
            }
        } else {
            // <=Android 10: permiso de runtime, necesita la Activity al frente.
            val callback = uiCallback
            if (callback != null) callback.onRequestStoragePermission()
            else bringActivityToFrontFor(MainActivity.PENDING_PERMISSION_STORAGE)
        }
    }

    /** Micrófono: permiso de runtime, necesita la Activity al frente para el diálogo del sistema. */
    private fun openMicPermission() {
        if (isMicGranted()) return
        val callback = uiCallback
        if (callback != null) callback.onRequestMicPermission()
        else bringActivityToFrontFor(MainActivity.PENDING_PERMISSION_MIC)
    }

    /** Fotos: permiso de runtime (READ_MEDIA_IMAGES/READ_EXTERNAL_STORAGE). */
    private fun openPhotosPermission() {
        if (isPhotosGranted()) return
        val callback = uiCallback
        if (callback != null) callback.onRequestPhotosPermission()
        else bringActivityToFrontFor(MainActivity.PENDING_PERMISSION_PHOTOS)
    }

    // Rango real del brillo int de ESTE equipo. Muchos NO usan 0..255 (Xiaomi suele ir a 2047/4095),
    // así que asumirlo desincroniza el slider. Se lee de la config interna del sistema.
    private val brightnessIntMax: Int by lazy { readSystemConfigInt("config_screenBrightnessSettingMaximum", 255).coerceAtLeast(1) }
    private val brightnessIntMin: Int by lazy { readSystemConfigInt("config_screenBrightnessSettingMinimum", 0).coerceAtLeast(0) }

    private fun readSystemConfigInt(name: String, def: Int): Int = try {
        val res = android.content.res.Resources.getSystem()
        val id = res.getIdentifier(name, "integer", "android")
        if (id != 0) res.getInteger(id) else def
    } catch (e: Exception) { def }

    /**
     * Brillo actual del sistema en 0..100. En Android 12+ el valor real que usa el sistema es un
     * float 0..1 (SCREEN_BRIGHTNESS_FLOAT); el int 0..255 legacy es un shim que en varios equipos
     * queda desfasado, por eso se prefiere el float y solo se cae al int en equipos viejos.
     */
    private fun currentBrightnessPercent(): Int {
        try {
            val f = Settings.System.getFloat(contentResolver, "screen_brightness_float")
            if (f in 0f..1f) return Math.round(f * 100f).coerceIn(0, 100)
        } catch (e: Exception) { /* setting inexistente en este equipo → int */ }
        return try {
            val raw = Settings.System.getInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS)
            val span = (brightnessIntMax - brightnessIntMin).coerceAtLeast(1)
            ((raw - brightnessIntMin) * 100 / span).coerceIn(0, 100)
        } catch (e: Exception) {
            50
        }
    }

    /**
     * Ajusta el brillo real de la pantalla del cliente. Requiere el permiso WRITE_SETTINGS
     * ("Modificar ajustes del sistema"); si no está concedido, abre esa pantalla para que el
     * cliente lo active. Pone el modo de brillo en manual para que el valor se respete.
     */
    private var brightnessBeforeBlack: Int = -1

    private fun requireWriteSettings(): Boolean {
        if (Settings.System.canWrite(this)) return true
        openWriteSettingsPermission()
        webRtcClient?.sendData(
            JSONObject().put("type", "alert-error")
                .put("message", "Falta el permiso \"Modificar ajustes del sistema\" en el dispositivo (se abrió la pantalla para concederlo)")
        )
        return false
    }

    private fun applyBrightnessPercent(value: Int) {
        val pct = value.coerceIn(0, 100)
        // Modo manual, si no el sistema (brillo adaptable) pisa el valor que fijamos.
        Settings.System.putInt(
            contentResolver,
            Settings.System.SCREEN_BRIGHTNESS_MODE,
            Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL
        )
        // Android 12+: se escribe el float autoritativo (0..1). También el int por compatibilidad,
        // usando el rango REAL del equipo (no un fijo 0..255) para que el nivel coincida con el slider.
        var wroteFloat = false
        try {
            Settings.System.putFloat(contentResolver, "screen_brightness_float", pct / 100f)
            wroteFloat = true
        } catch (e: Exception) { /* equipo sin float → solo int */ }
        val span = (brightnessIntMax - brightnessIntMin).coerceAtLeast(1)
        val raw = (brightnessIntMin + pct * span / 100).coerceIn(brightnessIntMin, brightnessIntMax)
        try {
            Settings.System.putInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS, raw)
        } catch (e: Exception) {
            if (!wroteFloat) throw e
        }
    }

    private fun setScreenBrightness(value: Int) {
        if (!requireWriteSettings()) return
        try {
            applyBrightnessPercent(value)
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "No se pudo ajustar el brillo", e)
        }
    }

    /**
     * "Pantalla negra": apaga el brillo físico a 0 (la persona ve negro) mientras la captura de
     * pantalla sigue leyendo el framebuffer real, así el técnico ve todo y controla por gestos.
     * Al desactivar restaura el brillo anterior.
     */
    private fun setBlackScreen(on: Boolean) {
        if (!requireWriteSettings()) return
        try {
            if (on) {
                if (brightnessBeforeBlack < 0) brightnessBeforeBlack = currentBrightnessPercent()
                applyBrightnessPercent(0)
            } else {
                val restore = if (brightnessBeforeBlack in 0..100) brightnessBeforeBlack else 50
                brightnessBeforeBlack = -1
                applyBrightnessPercent(restore)
            }
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "No se pudo cambiar la pantalla negra", e)
        }
    }

    private fun sendKeyEvent(keyCode: Int) {
        try {
            when (keyCode) {
                26 -> {
                    // KEYCODE_POWER — bloquear pantalla. GLOBAL_ACTION_LOCK_SCREEN (valor 8)
                    // requiere API 28+; en versiones anteriores no hay equivalente por accesibilidad.
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                        AccessibilityBridge.service?.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_LOCK_SCREEN)
                    }
                }
                24 -> {
                    // KEYCODE_VOLUME_UP
                    val am = getSystemService(AUDIO_SERVICE) as android.media.AudioManager
                    am.adjustVolume(android.media.AudioManager.ADJUST_RAISE, android.media.AudioManager.FLAG_SHOW_UI)
                }
                25 -> {
                    // KEYCODE_VOLUME_DOWN
                    val am = getSystemService(AUDIO_SERVICE) as android.media.AudioManager
                    am.adjustVolume(android.media.AudioManager.ADJUST_LOWER, android.media.AudioManager.FLAG_SHOW_UI)
                }
            }
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "Error en key-event $keyCode", e)
        }
    }

    /**
     * Enciende la pantalla y, si el bloqueo NO tiene PIN/patrón/contraseña/huella (por ejemplo
     * "Ninguno" o "Deslizar"), lo descarta con un swipe. Si SÍ tiene seguridad configurada,
     * Android ignora por diseño cualquier gesto de accesibilidad sobre el keyguard seguro —
     * eso es intencional (ver explicación al usuario) y no hay forma de evitarlo desde la app:
     * en ese caso la pantalla queda encendida mostrando el bloqueo, listo para que alguien
     * lo desbloquee físicamente.
     */
    // Wake lock para mantener la pantalla encendida mientras el técnico interactúa. Se renueva en
    // cada interacción y se libera solo tras 15s sin actividad (no drena batería en reposo).
    private var inputWakeLock: android.os.PowerManager.WakeLock? = null

    /**
     * Garantiza que la pantalla esté encendida para que los gestos de accesibilidad se despachen.
     * Devuelve true si estaba apagada (el llamador da un margen antes de mandar el gesto).
     */
    private fun keepScreenAwakeForInput(): Boolean {
        val pm = getSystemService(POWER_SERVICE) as android.os.PowerManager
        // Caso normal (pantalla encendida): no se hace NADA, el tap/gesto se despacha al instante.
        if (pm.isInteractive) return false
        val wasOff = true
        try {
            val wl = inputWakeLock ?: run {
                @Suppress("DEPRECATION")
                val created = pm.newWakeLock(
                    android.os.PowerManager.SCREEN_BRIGHT_WAKE_LOCK or
                        android.os.PowerManager.ACQUIRE_CAUSES_WAKEUP or
                        android.os.PowerManager.ON_AFTER_RELEASE,
                    "AccesHost:input"
                )
                created.setReferenceCounted(false)
                inputWakeLock = created
                created
            }
            wl.acquire(15000)
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "No se pudo despertar la pantalla para input", e)
        }
        return wasOff
    }

    private fun releaseInputWakeLock() {
        try {
            inputWakeLock?.let { if (it.isHeld) it.release() }
        } catch (e: Exception) { /* ya liberado */ }
        inputWakeLock = null
    }

    private fun wakeAndUnlockScreen() {
        try {
            val pm = getSystemService(POWER_SERVICE) as android.os.PowerManager
            @Suppress("DEPRECATION")
            val wakeLock = pm.newWakeLock(
                android.os.PowerManager.SCREEN_BRIGHT_WAKE_LOCK or
                    android.os.PowerManager.ACQUIRE_CAUSES_WAKEUP or
                    android.os.PowerManager.ON_AFTER_RELEASE,
                "AccesHost:wakeScreen"
            )
            wakeLock.acquire(3000)
            // Pequeño margen para que la pantalla termine de encender antes del gesto.
            reconnectHandler.postDelayed({
                AccessibilityBridge.handleCommand(
                    JSONObject()
                        .put("type", "swipe")
                        .put("x1Norm", 0.5)
                        .put("y1Norm", 0.85)
                        .put("x2Norm", 0.5)
                        .put("y2Norm", 0.2)
                        .put("durationMs", 300)
                )
            }, 400)
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "No se pudo encender/desbloquear pantalla", e)
        }
    }

    private fun setRingerMode(mode: String) {
        try {
            val am = getSystemService(AUDIO_SERVICE) as android.media.AudioManager
            when (mode) {
                "silent" -> am.ringerMode = android.media.AudioManager.RINGER_MODE_SILENT
                "vibrate" -> am.ringerMode = android.media.AudioManager.RINGER_MODE_VIBRATE
                "normal" -> am.ringerMode = android.media.AudioManager.RINGER_MODE_NORMAL
            }
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "No se pudo cambiar el modo de sonido", e)
        }
    }

    private fun listPhotos() {
        android.util.Log.d("AccesHostService", "listPhotos() llamado, webRtcClient=$webRtcClient")
        try {
            val photos = mutableListOf<Map<String, Any>>()
            val imageExtensions = setOf("jpg", "jpeg", "png", "gif", "webp", "bmp")

            // Buscar en DCIM y Pictures
            for (baseDir in listOf("/storage/emulated/0/DCIM", "/storage/emulated/0/Pictures", "/storage/emulated/0/Download")) {
                val dir = java.io.File(baseDir)
                android.util.Log.d("AccesHostService", "Buscando fotos en: $baseDir, existe=${dir.exists()}")
                if (dir.exists() && dir.isDirectory) {
                    dir.walk().maxDepth(3).forEach { file ->
                        if (file.isFile && file.canRead()) {
                            val ext = file.extension.lowercase()
                            if (ext in imageExtensions) {
                                photos.add(mapOf(
                                    "name" to file.name,
                                    "path" to file.absolutePath,
                                    "size" to file.length(),
                                    "modified" to file.lastModified()
                                ))
                            }
                        }
                    }
                }
            }

            // Ordenar por fecha (más recientes primero)
            val sorted = photos.sortedByDescending { it["modified"] as Long }

            if (webRtcClient != null) {
                android.util.Log.d("AccesHostService", "Enviando ${sorted.size} fotos")
                webRtcClient!!.sendData(
                    JSONObject().put("type", "photos-list")
                        .put("photos", JSONArray(sorted))
                )
                // Luego se manda una MINIATURA de cada foto (una por mensaje, en un hilo aparte,
                // igual que los íconos de apps) para que el portal las muestre de verdad.
                val paths = sorted.map { it["path"] as String }
                Thread {
                    for (p in paths) {
                        val thumb = decodePhotoBase64(p, 256, 60)
                        if (thumb != null) {
                            webRtcClient?.sendData(
                                JSONObject().put("type", "photo-thumb").put("path", p).put("thumb", thumb)
                            )
                        }
                        Thread.sleep(20)
                    }
                }.start()
            } else {
                android.util.Log.e("AccesHostService", "webRtcClient es null en listPhotos")
            }
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "Error listando fotos", e)
            if (webRtcClient != null) {
                webRtcClient!!.sendData(
                    JSONObject().put("type", "photos-error")
                        .put("message", "Error: ${e.message}")
                )
            }
        }
    }

    /** Envía la imagen completa (más grande) de una foto, para verla al hacer clic en el portal. */
    private fun sendPhotoFull(path: String) {
        if (path.isBlank()) return
        Thread {
            val img = decodePhotoBase64(path, 1440, 82)
            if (img != null) {
                webRtcClient?.sendData(
                    JSONObject().put("type", "photo-full").put("path", path).put("data", img)
                )
            }
        }.start()
    }

    /**
     * Decodifica una imagen del disco a JPEG base64, reducida a maxPx en su lado mayor. Usa
     * inSampleSize para no cargar el bitmap completo en memoria (fotos grandes → OOM).
     * Devuelve solo el base64 (sin prefijo data:), como los íconos de apps.
     */
    private fun decodePhotoBase64(path: String, maxPx: Int, quality: Int): String? {
        return try {
            val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
            android.graphics.BitmapFactory.decodeFile(path, bounds)
            val w = bounds.outWidth
            val h = bounds.outHeight
            if (w <= 0 || h <= 0) return null
            var sample = 1
            while (w / sample > maxPx * 2 || h / sample > maxPx * 2) sample *= 2
            val opts = android.graphics.BitmapFactory.Options().apply { inSampleSize = sample }
            var bmp = android.graphics.BitmapFactory.decodeFile(path, opts) ?: return null
            val scale = maxPx.toFloat() / maxOf(bmp.width, bmp.height)
            if (scale < 1f) {
                val nw = (bmp.width * scale).toInt().coerceAtLeast(1)
                val nh = (bmp.height * scale).toInt().coerceAtLeast(1)
                bmp = android.graphics.Bitmap.createScaledBitmap(bmp, nw, nh, true)
            }
            val stream = java.io.ByteArrayOutputStream()
            bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, quality, stream)
            android.util.Base64.encodeToString(stream.toByteArray(), android.util.Base64.NO_WRAP)
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "No se pudo decodificar la foto: $path", e)
            null
        }
    }

    private fun listFiles(path: String) {
        try {
            val dir = java.io.File(path)
            if (!dir.exists() || !dir.isDirectory) {
                webRtcClient?.sendData(
                    JSONObject().put("type", "files-error")
                        .put("message", "Ruta no válida: $path")
                )
                return
            }

            val files = mutableListOf<Map<String, Any>>()
            dir.listFiles()?.forEach { file ->
                if (file.canRead()) {
                    files.add(mapOf(
                        "name" to file.name,
                        "path" to file.absolutePath,
                        "isDir" to file.isDirectory,
                        "size" to (if (file.isFile) file.length() else 0L),
                        "modified" to file.lastModified()
                    ))
                }
            }

            // Ordenar: carpetas primero, luego archivos por nombre
            val sorted = files.sortedWith(compareBy({ !(it["isDir"] as Boolean) }, { it["name"].toString() }))

            if (webRtcClient != null) {
                android.util.Log.d("AccesHostService", "Enviando ${sorted.size} archivos desde $path")
                webRtcClient!!.sendData(
                    JSONObject().put("type", "files-list")
                        .put("path", path)
                        .put("files", JSONArray(sorted))
                )
            } else {
                android.util.Log.e("AccesHostService", "webRtcClient es null en listFiles")
            }
        } catch (e: Exception) {
            android.util.Log.e("AccesHostService", "Error listando archivos", e)
            if (webRtcClient != null) {
                webRtcClient!!.sendData(
                    JSONObject().put("type", "files-error")
                        .put("message", "Error: ${e.message}")
                )
            }
        }
    }

    private fun openWriteSettingsPermission() {
        launchSettings(Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:$packageName")))
    }

    /**
     * Segunda conexión WebRTC, independiente de la de pantalla, para la cámara. Se
     * multiplexa sobre la misma sesión marcando los mensajes de señalización con
     * "stream": "camera" (ver onSignal arriba y control.js del lado navegador).
     */
    private fun startCamera(facing: String) {
        stopCamera()
        val sessionId = activeSessionId ?: return
        TurnCredentials.fetch { iceServers ->
            reconnectHandler.post {
                if (activeSessionId != sessionId) return@post
                val client = CameraWebRtcClient(applicationContext, eglBase, object : CameraWebRtcClient.Listener {
                    override fun onLocalIceCandidate(candidate: IceCandidate) {
                        val sid = activeSessionId ?: return
                        signalingClient.sendSignal(
                            sid,
                            JSONObject()
                                .put("stream", "camera")
                                .put("kind", "ice-candidate")
                                .put("candidate", candidate.sdp)
                                .put("sdpMid", candidate.sdpMid)
                                .put("sdpMLineIndex", candidate.sdpMLineIndex)
                        )
                    }

                    override fun onLocalDescription(description: SessionDescription) {
                        val sid = activeSessionId ?: return
                        signalingClient.sendSignal(
                            sid,
                            JSONObject()
                                .put("stream", "camera")
                                .put("kind", "offer")
                                .put("sdp", description.description)
                        )
                    }

                    override fun onConnectionFailed() {
                        stopCamera()
                    }
                })
                cameraClient = client
                client.start(facing, iceServers)
            }
        }
    }

    private fun stopCamera() {
        cameraClient?.close()
        cameraClient = null
    }

    /**
     * "Escucha en vivo": tercera conexión WebRTC (solo audio del micrófono), multiplexada sobre la
     * misma sesión con "stream": "mic". Necesita el permiso de micrófono (panel de Permisos).
     */
    private fun startMic() {
        if (!isMicGranted()) {
            webRtcClient?.sendData(
                JSONObject().put("type", "mic-error")
                    .put("message", "Falta el permiso de micrófono en el dispositivo (actívalo en Permisos)")
            )
            openMicPermission()
            return
        }
        stopMic()
        val sessionId = activeSessionId ?: return
        // Android 14+: para capturar micrófono desde un FGS hay que incluir el tipo microphone.
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val type = ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION or
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
                startForegroundTyped(buildNotification(getString(R.string.notification_active_session)), type)
            }
        } catch (e: Exception) {
            android.util.Log.w("AccesHostService", "No se pudo promover FGS a microphone", e)
        }
        TurnCredentials.fetch { iceServers ->
            reconnectHandler.post {
                if (activeSessionId != sessionId) return@post
                val client = MicWebRtcClient(applicationContext, object : MicWebRtcClient.Listener {
                    override fun onLocalIceCandidate(candidate: IceCandidate) {
                        val sid = activeSessionId ?: return
                        signalingClient.sendSignal(
                            sid,
                            JSONObject()
                                .put("stream", "mic")
                                .put("kind", "ice-candidate")
                                .put("candidate", candidate.sdp)
                                .put("sdpMid", candidate.sdpMid)
                                .put("sdpMLineIndex", candidate.sdpMLineIndex)
                        )
                    }

                    override fun onLocalDescription(description: SessionDescription) {
                        val sid = activeSessionId ?: return
                        signalingClient.sendSignal(
                            sid,
                            JSONObject()
                                .put("stream", "mic")
                                .put("kind", "offer")
                                .put("sdp", description.description)
                        )
                    }

                    override fun onConnectionFailed() {
                        stopMic()
                    }
                })
                micClient = client
                client.start(iceServers)
            }
        }
    }

    private fun stopMic() {
        micClient?.close()
        micClient = null
    }

    private fun respondWithScreenText() {
        val client = webRtcClient ?: run {
            android.util.Log.e("AccesHostService", "list-screen-text: webRtcClient es null")
            return
        }
        val service = AccessibilityBridge.service
        if (service == null) {
            android.util.Log.e("AccesHostService", "list-screen-text: AccessibilityBridge.service es null (¿servicio de accesibilidad desactivado?)")
        }
        val nodes = service?.extractScreenText() ?: JSONArray()
        android.util.Log.d("AccesHostService", "list-screen-text: ${nodes.length()} nodos de texto encontrados")
        client.sendData(JSONObject().put("type", "screen-text").put("nodes", nodes))
    }

    private var overlayView: android.view.View? = null

    /**
     * Mecanismo real de Android para esto: una app con una ventana visible (aunque sea
     * mínima) queda exenta de la restricción que bloquea abrir pantallas desde un
     * componente en segundo plano (nuestro Service). Requiere el permiso "Dibujar sobre
     * otras apps" ya concedido. En MIUI existe además su PROPIA restricción aparte
     * (el permiso "ventanas emergentes en 2do plano" del panel de Permisos) — para máxima
     * confiabilidad en Xiaomi conviene tener ambos activados.
     */
    // Igual que showAlert: esto puede dispararse desde el hilo de WebRTC (sin Looper),
    // y WindowManager.addView exige el hilo principal.
    private fun ensureOverlayShown() {
        reconnectHandler.post {
            if (overlayView != null) return@post
            if (!Settings.canDrawOverlays(this)) return@post
            try {
                val wm = getSystemService(WINDOW_SERVICE) as WindowManager
                val view = android.view.View(this).apply {
                    setBackgroundColor(0x1A00FF41) // punto verde muy tenue, casi imperceptible
                }
                val size = (8 * resources.displayMetrics.density).toInt().coerceAtLeast(4)
                val params = WindowManager.LayoutParams(
                    size, size,
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                        WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                        WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    android.graphics.PixelFormat.TRANSLUCENT
                )
                params.gravity = android.view.Gravity.TOP or android.view.Gravity.START
                wm.addView(view, params)
                overlayView = view
            } catch (e: Exception) {
                android.util.Log.e("AccesHostService", "No se pudo mostrar el overlay", e)
            }
        }
    }

    private var alertOverlayView: android.view.View? = null
    private var alertParams: WindowManager.LayoutParams? = null

    // Mientras haya una alerta activa, re-adjunta el overlay si el sistema lo quitó (cambios de
    // pantalla, MIUI, etc.), para que la alerta se mantenga siempre visible.
    private val alertReassert = object : Runnable {
        override fun run() {
            val view = alertOverlayView ?: return
            val params = alertParams ?: return
            try {
                if (!view.isAttachedToWindow && view.parent == null) {
                    (getSystemService(WINDOW_SERVICE) as WindowManager).addView(view, params)
                }
            } catch (e: Exception) {
                android.util.Log.w("AccesHostService", "No se pudo re-adjuntar la alerta", e)
            }
            reconnectHandler.postDelayed(this, 1000)
        }
    }
    private var alertCountdownTimer: android.os.CountDownTimer? = null

    /**
     * Overlay de alerta a pantalla completa (fondo negro, spinner, título, mensaje y
     * barra de tiempo) sobre el dispositivo del cliente. Requiere el mismo permiso de
     * "Dibujar sobre otras apps" del panel de Permisos. Se autodestruye al terminar el
     * tiempo, al terminar la sesión o si se cierra el servicio — nunca debe quedar
     * bloqueando la pantalla del cliente indefinidamente.
     */
    // Los mensajes del DataChannel llegan en el hilo interno de WebRTC (sin Looper), y
    // WindowManager.addView/removeView exige el hilo principal — de ahí este post().
    private fun showAlert(alertType: String, title: String, text: String, durationSeconds: Int) {
        // De vuelta a la superposición para ambos tipos (translúcida por el límite de
        // MIUI, pero los gestos remotos siguen funcionando — eso pesa más que la opacidad).
        if (!Settings.canDrawOverlays(this)) {
            android.util.Log.e("AccesHostService", "No se puede mostrar la alerta: falta el permiso de superposición")
            webRtcClient?.sendData(
                JSONObject().put("type", "alert-error")
                    .put("message", "Falta el permiso \"Dibujar sobre otras apps\" en el dispositivo (ver panel Permisos)")
            )
            return
        }

        reconnectHandler.post {
            hideAlertOnMainThread()

            val wm = getSystemService(WINDOW_SERVICE) as WindowManager
            val view = android.view.LayoutInflater.from(this).inflate(R.layout.overlay_alert, null)
            val spinner = view.findViewById<android.widget.ProgressBar>(R.id.alertSpinner)
            val titleView = view.findViewById<android.widget.TextView>(R.id.alertTitle)
            val textView = view.findViewById<android.widget.TextView>(R.id.alertText)
            val timeBar = view.findViewById<android.widget.ProgressBar>(R.id.alertTimeBar)

            if (alertType == "blackscreen") {
                spinner.visibility = android.view.View.GONE
                titleView.visibility = android.view.View.GONE
                textView.visibility = android.view.View.GONE
                timeBar.visibility = android.view.View.GONE
            } else {
                titleView.text = title
                textView.text = text
            }
            timeBar.max = 1000
            timeBar.progress = 1000

            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                    // FLAG_NOT_TOUCHABLE/FLAG_NOT_FOCUSABLE: esta alerta es solo visual
                    // (MIUI la mantiene semitransparente pase lo que pase) — no bloquea
                    // toques, tanto los reales como los que manda el técnico remoto
                    // siguen llegando a la app de abajo.
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                android.graphics.PixelFormat.TRANSLUCENT
            )
            params.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES

            @Suppress("DEPRECATION")
            view.systemUiVisibility = (
                android.view.View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    or android.view.View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    or android.view.View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    or android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    or android.view.View.SYSTEM_UI_FLAG_FULLSCREEN
                    or android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                )

            try {
                wm.addView(view, params)
            } catch (e: Exception) {
                android.util.Log.e("AccesHostService", "No se pudo mostrar la alerta", e)
                return@post
            }
            alertOverlayView = view
            alertParams = params
            // Algunas pantallas (o MIUI) desprenden el overlay; se re-verifica y se vuelve a
            // poner cada segundo mientras la alerta esté activa, así "siempre está activa".
            reconnectHandler.removeCallbacks(alertReassert)
            reconnectHandler.postDelayed(alertReassert, 1000)

            val durationMs = durationSeconds.coerceIn(1, 600) * 1000L
            alertCountdownTimer = object : android.os.CountDownTimer(durationMs, 100) {
                override fun onTick(millisUntilFinished: Long) {
                    timeBar.progress = ((millisUntilFinished.toFloat() / durationMs) * 1000).toInt()
                }
                override fun onFinish() {
                    hideAlertOnMainThread()
                }
            }.start()
        }
    }

    private fun hideAlert() {
        reconnectHandler.post { hideAlertOnMainThread() }
    }

    private fun hideAlertOnMainThread() {
        reconnectHandler.removeCallbacks(alertReassert)
        alertCountdownTimer?.cancel()
        alertCountdownTimer = null
        alertOverlayView?.let { view ->
            try {
                (getSystemService(WINDOW_SERVICE) as WindowManager).removeView(view)
            } catch (e: Exception) {
                // ya no estaba adjunto; no pasa nada
            }
        }
        alertOverlayView = null
        alertParams = null
    }

    private fun removeOverlay() {
        val view = overlayView ?: return
        try {
            (getSystemService(WINDOW_SERVICE) as WindowManager).removeView(view)
        } catch (e: Exception) {
            // ya no estaba adjunto; no pasa nada
        }
        overlayView = null
    }

    /**
     * Android rechaza el toque sobre el botón de consentimiento de captura de pantalla si hay un
     * overlay de la app encima ("touch obscured", protección de seguridad). Se quita el overlay
     * ANTES de pedir la captura para que el auto-confirm (toque real) sí registre. Se restaura solo
     * cuando la captura ya arrancó (ver startCaptureForSession).
     */
    fun hideOverlayForProjection() {
        reconnectHandler.post { removeOverlay() }
    }

    private fun openDrawOverlayPermission() {
        // Si ya está concedido, no hace falta pedir de nuevo.
        if (Settings.canDrawOverlays(this)) return
        // Se abre la pantalla de "Dibujar sobre otras apps" de ESTA app y se arma el auto-activado
        // del interruptor por accesibilidad, sin traer nuestra app al frente del cliente.
        AccessibilityBridge.armOverlayAutoEnable()
        launchSettings(
            Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))
        )
    }

    private fun requestContactsPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS)
            == PackageManager.PERMISSION_GRANTED
        ) return
        val callback = uiCallback
        if (callback != null) callback.onRequestContactsPermission()
        else bringActivityToFrontFor(MainActivity.PENDING_PERMISSION_CONTACTS)
    }

    private fun requestCameraPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) return
        val callback = uiCallback
        if (callback != null) callback.onRequestCameraPermission()
        else bringActivityToFrontFor(MainActivity.PENDING_PERMISSION_CAMERA)
    }

    /** Trae MainActivity al frente (si no está enlazada ahora mismo) con el permiso pendiente
     *  a pedir, para que lo dispare apenas se reconecte al servicio. */
    private fun bringActivityToFrontFor(pendingPermission: String) {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
            putExtra(MainActivity.EXTRA_PENDING_PERMISSION, pendingPermission)
        }
        startActivity(intent)
    }

    /** API estándar de Android: diálogo del sistema de un solo toque, sin navegar ajustes. */
    private fun openBatteryOptimizationSettings() {
        launchSettings(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
    }

    /**
     * Intenta ir directo al editor de permisos de MIUI (no documentado oficialmente, puede
     * fallar según la versión de MIUI); si falla, cae a la pantalla estándar de Ajustes de la app.
     */
    private fun openOverlayPermissionSettings() {
        val miuiIntent = Intent("miui.intent.action.APP_PERM_EDITOR")
        miuiIntent.setClassName("com.miui.securitycenter", "com.miui.permcenter.permissions.PermissionsEditorActivity")
        miuiIntent.putExtra("extra_pkgname", packageName)
        miuiIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (AccessibilityBridge.launchActivity(miuiIntent)) return
        try {
            startActivity(miuiIntent)
        } catch (e: Exception) {
            openAppSettings(packageName)
        }
    }

    override fun onConnectionFailed() {
        // Fallo de red (ICE) — solo se cierra la sesión; la captura de pantalla sigue viva
        // para que la próxima conexión no tenga que volver a pedir permiso.
        activeSessionId?.let { signalingClient.endSession(it) }
        teardownSession()
    }

    override fun onCaptureStopped() {
        // El sistema detuvo la MediaProjection real (no solo la red) — ya no hay nada que
        // reutilizar, así que la próxima sesión sí necesita pedir el permiso de nuevo.
        android.util.Log.w("AccesHostService", "Captura de pantalla detenida por el sistema")
        projectionData = null
        activeSessionId?.let { signalingClient.endSession(it) }
        teardownSession()
    }

    // ---- Notificación en primer plano ----

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID, getString(R.string.notification_channel_name), NotificationManager.IMPORTANCE_LOW
        )
        (getSystemService(NotificationManager::class.java)).createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setSmallIcon(android.R.drawable.presence_video_online)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        (getSystemService(NotificationManager::class.java))
            .notify(NOTIFICATION_ID, buildNotification(text))
    }

    /**
     * startForeground con tipo explícito (Android 10+/API 29 lo requiere para elegir entre los
     * tipos declarados en el manifest; en versiones anteriores el tipo no existe y se ignora).
     */
    private fun startForegroundTyped(notification: Notification, type: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, type)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    override fun onDestroy() {
        stopping = true
        reconnectHandler.removeCallbacksAndMessages(null)
        AccessibilityBridge.statusListener = null
        try { unregisterReceiver(screenReceiver) } catch (e: Exception) { /* no estaba registrado */ }
        webRtcClient?.close()
        stopCamera()
        stopMic()
        releaseInputWakeLock()
        hideAlert()
        signalingClient.close()
        removeOverlay()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL_ID = "acces_host_service"
        private const val NOTIFICATION_ID = 1
        private const val ACTION_HEARTBEAT = "com.acces.hostapp.ACTION_HEARTBEAT"
        private const val HEARTBEAT_REQUEST_CODE = 2
        private const val HEARTBEAT_INTERVAL_MS = 3 * 60 * 1000L // cada 3 minutos
    }
}
