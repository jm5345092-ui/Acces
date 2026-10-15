package com.acces.hostapp

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.graphics.Point
import android.graphics.Rect
import android.util.DisplayMetrics
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject

/**
 * Ejecuta los gestos que llegan del técnico remoto. No navega el árbol de accesibilidad:
 * solo se usa canPerformGestures para inyectar toques/swipes, como haría un usuario real.
 * Coordenadas normalizadas (0..1) para no depender de la resolución exacta del Controller.
 */
class RemoteAccessibilityService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        AccessibilityBridge.service = this
        AccessibilityBridge.notifyStatusChanged()
        // Si se pidió la captura justo antes de que este servicio se enlazara (primera sesión),
        // la ventana de auto-confirmación puede seguir armada: arrancar el sondeo ahora.
        if (System.currentTimeMillis() < AccessibilityBridge.autoConfirmProjectionUntil) {
            startAutoConfirmPolling()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (AccessibilityBridge.service == this) {
            AccessibilityBridge.service = null
            AccessibilityBridge.currentPackage = null
            AccessibilityBridge.notifyStatusChanged()
        }
    }

    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())

    // Textos del botón "confirmar" del diálogo de captura, en varios idiomas (universal).
    private val confirmLabels = listOf(
        // Español
        "iniciar ahora", "comenzar ahora", "empezar ahora", "iniciar", "comenzar", "empezar",
        "iniciar grabación", "iniciar grabacion", "iniciar transmisión", "iniciar transmision",
        "aceptar", "permitir", "continuar", "grabar", "transmitir", "proyectar", "entendido",
        // Inglés
        "start now", "start recording", "start", "allow", "continue", "record", "cast", "got it", "ok",
        // Portugués
        "começar agora", "comecar agora", "iniciar agora", "começar", "comecar", "gravar", "permitir agora",
        // Desinstalar (para el otro auto-confirm)
        "desinstalar", "uninstall"
    )

    // Palabras del botón NEGATIVO (para descartarlo). Multi-idioma, para que el auto-confirm
    // funcione en cualquier dispositivo: se toca el botón que NO sea "cancelar/denegar".
    private val cancelLabels = listOf(
        "cancelar", "cancel", "denegar", "deny", "no permitir", "no gracias", "don't allow", "dont allow",
        "cerrar", "close", "nunca", "never", "rechazar", "reject", "atrás", "atras", "back"
    )

    /**
     * Recoge candidatos a BOTÓN: nodos tipo Button o clicables, CON texto corto. El límite de
     * longitud (<=30) es clave: excluye el TÍTULO/mensaje del diálogo (una frase larga que además
     * contiene palabras como "iniciar"), que antes se tocaba por error en vez del botón.
     */
    // Recoge nodos con TEXTO VISIBLE corto (node.text). Guiarse por el texto es lo universal: el
    // botón de aceptar SIEMPRE tiene texto ("Comenzar ahora", "Start now", "Permitir"…). Los
    // botones de la barra de navegación (Inicio/Atrás) NO tienen texto (solo contentDescription),
    // así que quedan fuera. El título/mensaje es una frase larga → fuera por longitud.
    private fun collectButtons(node: AccessibilityNodeInfo?, out: MutableList<AccessibilityNodeInfo>) {
        if (node == null) return
        val label = node.text?.toString()?.trim()
        if (!label.isNullOrBlank() && label.length in 1..30) out.add(node)
        for (i in 0 until node.childCount) collectButtons(node.getChild(i), out)
    }

    /**
     * Botón positivo del diálogo, guiándose SOLO por el texto (universal, cualquier idioma/marca).
     * Devuelve null si el botón de aceptar aún no está en pantalla — así el sondeo sigue esperando
     * (el diálogo tarda un momento en dibujar los botones) en vez de tocar algo equivocado.
     */
    private fun findPositiveButton(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val nodes = mutableListOf<AccessibilityNodeInfo>()
        collectButtons(root, nodes)
        // Solo un botón cuya etiqueta sea de CONFIRMACIÓN conocida (multi-idioma). Si no hay, se
        // devuelve null y el sondeo reintenta hasta que aparezca — NUNCA se toca otra cosa.
        for (b in nodes) {
            val t = b.text?.toString()?.trim()?.lowercase() ?: ""
            if (t.isNotEmpty() && confirmLabels.any { t == it || t.contains(it) }
                && cancelLabels.none { t == it || t.contains(it) }) return b
        }
        return null
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return

        // Auto-confirmar el diálogo de captura: se intenta en CUALQUIER evento (no solo
        // WINDOW_STATE_CHANGED) mientras la ventana esté armada, y se asegura que el sondeo
        // activo esté corriendo. Esto lo hace funcionar desde la PRIMERA vez, aunque el servicio
        // se acabara de enlazar o el fabricante no dispare WINDOW_STATE_CHANGED para el diálogo.
        if (System.currentTimeMillis() < AccessibilityBridge.autoConfirmProjectionUntil) {
            if (!autoConfirmPolling) startAutoConfirmPolling()
            // La ventana del EVENTO es la más fiable en MIUI (la lista de ventanas a veces no
            // incluye el diálogo de captura). Se intenta primero con la raíz del nodo del evento.
            if (tapConfirmInRoot(rootOf(event.source))) return
            tryAutoConfirmProjection()
        }

        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return
        val pkg = event.packageName?.toString()?.takeIf { it.isNotBlank() } ?: return

        // Auto-confirmar el diálogo de desinstalar (instalador de paquetes) mientras esté armado.
        if (System.currentTimeMillis() < AccessibilityBridge.autoConfirmUninstallUntil &&
            pkg.contains("packageinstall")
        ) {
            if (!tryAutoConfirmUninstall()) {
                mainHandler.postDelayed({ tryAutoConfirmUninstall() }, 300)
                mainHandler.postDelayed({ tryAutoConfirmUninstall() }, 800)
            }
            return
        }

        // Auto-activar el interruptor de "Dibujar sobre otras apps" cuando se abre su pantalla.
        if (System.currentTimeMillis() < AccessibilityBridge.autoEnableOverlayUntil &&
            (pkg == "com.android.settings" || pkg == "com.miui.securitycenter" || pkg == "android")
        ) {
            if (!tryAutoEnableSwitch()) {
                mainHandler.postDelayed({ tryAutoEnableSwitch() }, 300)
                mainHandler.postDelayed({ tryAutoEnableSwitch() }, 800)
            }
            return
        }

        // Ignora la propia UI del sistema para no reportar "barra de estado" como app abierta.
        if (pkg == "com.android.systemui") return
        if (pkg != AccessibilityBridge.currentPackage) {
            AccessibilityBridge.currentPackage = pkg
            AccessibilityBridge.notifyStatusChanged()
        }
    }

    private var autoConfirmPollRunnable: Runnable? = null
    @Volatile private var autoConfirmPolling = false
    // Momento (ms) en que se detectó por primera vez el diálogo de captura, para darle tiempo a
    // asentarse antes de tocar. Y la última posición leída del botón, para exigir que sea estable.
    private var projectionDialogSeenAt = 0L
    private var lastTargetRect: Rect? = null

    /**
     * Sondeo activo del árbol de accesibilidad cada 120ms mientras la ventana esté armada
     * (hasta 12s) — no depende de que llegue ningún evento de accesibilidad en particular, así
     * que funciona igual si el fabricante dispara WINDOW_STATE_CHANGED, WINDOW_CONTENT_CHANGED,
     * o ninguno de los dos para este diálogo.
     */
    fun startAutoConfirmPolling() {
        autoConfirmPollRunnable?.let { mainHandler.removeCallbacks(it) }
        projectionDialogSeenAt = 0L
        lastTargetRect = null
        autoConfirmPolling = true
        val runnable = object : Runnable {
            override fun run() {
                if (System.currentTimeMillis() >= AccessibilityBridge.autoConfirmProjectionUntil) {
                    autoConfirmPolling = false
                    return
                }
                if (tryAutoConfirmProjection()) {
                    autoConfirmPolling = false
                    return
                }
                // Sondeo muy rápido (40 ms): en cuanto el diálogo es interactivo, se toca al instante.
                mainHandler.postDelayed(this, 40)
            }
        }
        autoConfirmPollRunnable = runnable
        mainHandler.post(runnable)
    }

    private var uninstallPollRunnable: Runnable? = null

    /** Igual que el sondeo de captura, pero para el diálogo de desinstalar (instalador de paquetes). */
    fun startUninstallAutoConfirmPolling() {
        uninstallPollRunnable?.let { mainHandler.removeCallbacks(it) }
        val runnable = object : Runnable {
            override fun run() {
                if (System.currentTimeMillis() >= AccessibilityBridge.autoConfirmUninstallUntil) return
                if (tryAutoConfirmUninstall()) return
                mainHandler.postDelayed(this, 200)
            }
        }
        uninstallPollRunnable = runnable
        mainHandler.post(runnable)
    }

    /** Busca y toca el botón positivo del diálogo de desinstalar. Solo actúa en el instalador. */
    private fun tryAutoConfirmUninstall(): Boolean {
        if (System.currentTimeMillis() >= AccessibilityBridge.autoConfirmUninstallUntil) return false
        val root = rootInActiveWindow ?: return false
        val pkg = root.packageName?.toString() ?: ""
        // Solo el instalador de paquetes muestra este diálogo; evita tocar otros "OK" por error.
        if (!pkg.contains("packageinstaller") && !pkg.contains("packageinstall")) return false
        val target = findPositiveButton(root) ?: return false
        // Toque real (como en la captura): en MIUI el ACTION_CLICK no siempre funciona en el diálogo.
        val rect = Rect()
        target.getBoundsInScreen(rect)
        if (rect.width() > 0 && rect.height() > 0) {
            val path = Path().apply { moveTo(rect.exactCenterX(), rect.exactCenterY()) }
            val ok = dispatchGesture(
                GestureDescription.Builder()
                    .addStroke(GestureDescription.StrokeDescription(path, 0, 40))
                    .build(),
                null, null
            )
            if (ok) { AccessibilityBridge.autoConfirmUninstallUntil = 0L; return true }
        }
        var node: AccessibilityNodeInfo? = target
        while (node != null) {
            if (node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                AccessibilityBridge.autoConfirmUninstallUntil = 0L
                return true
            }
            node = node.parent
        }
        if (target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
            AccessibilityBridge.autoConfirmUninstallUntil = 0L
            return true
        }
        return false
    }

    /** Recopila las raíces de TODAS las ventanas visibles (no solo la activa). El diálogo de
     *  captura en Android 14 suele estar en una ventana aparte que rootInActiveWindow no devuelve. */
    private fun allWindowRoots(): List<AccessibilityNodeInfo> {
        val roots = mutableListOf<AccessibilityNodeInfo>()
        rootInActiveWindow?.let { roots.add(it) }
        try {
            for (w in windows) {
                val r = w.root ?: continue
                if (roots.none { it == r }) roots.add(r)
            }
        } catch (e: Exception) { /* windows no disponible */ }
        return roots
    }

    /** Sube hasta la raíz del árbol al que pertenece un nodo. */
    private fun rootOf(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        var n = node ?: return null
        while (true) { val p = n.parent ?: break; n = p }
        return n
    }

    /**
     * Busca el botón de confirmar (por TEXTO) en la raíz dada y lo toca con un TOQUE REAL
     * (dispatchGesture) — en MIUI el ACTION_CLICK no funciona sobre el diálogo de MediaProjection,
     * pero un toque real sí. Solo actúa en ventanas de SystemUI/android.
     */
    private fun tapGesture(cx: Float, cy: Float): Boolean {
        // Toque lo más INSTANTÁNEO posible (1 ms). El diálogo ya está asentado antes de llegar aquí
        // (ver el gate en tapConfirmInRoot), así que no hace falta un toque largo para "asegurarlo":
        // se dispara en cuanto los botones están estables, y el toque en sí es inmediato.
        val path = Path().apply { moveTo(cx, cy) }
        return dispatchGesture(
            GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 1)).build(),
            null, null
        )
    }

    /** Busca el botón negativo (Cancelar/Deny…) por texto — este SÍ es visible a la accesibilidad. */
    private fun findCancelButton(root: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        val nodes = mutableListOf<AccessibilityNodeInfo>()
        collectButtons(root, nodes)
        for (b in nodes) {
            val t = b.text?.toString()?.trim()?.lowercase() ?: ""
            if (t.isNotEmpty() && cancelLabels.any { t == it || t.contains(it) }) return b
        }
        return null
    }

    private fun tapConfirmInRoot(root: AccessibilityNodeInfo?): Boolean {
        if (root == null) return false
        val pkg = root.packageName?.toString() ?: ""
        if (pkg != "com.android.systemui" && pkg != "android") return false

        // --- Paso A: calcular DÓNDE habría que tocar (sin tocar todavía) ---
        val rootRect = Rect(); root.getBoundsInScreen(rootRect)
        if (rootRect.width() <= 0 || rootRect.height() <= 0) return false

        val target = Rect()
        val label: String

        // A1) Si el botón de confirmar ES visible a la accesibilidad (equipos donde no lo ocultan),
        //     se usa su posición directa.
        val positive = findPositiveButton(root)
        if (positive != null) {
            positive.getBoundsInScreen(target)
            if (target.width() <= 0 || target.height() <= 0) return false
            label = "boton visible '${positive.text}'"
        } else {
            // A2) Android 14 OCULTA el botón positivo a la accesibilidad, pero deja visible "Cancelar".
            //     Los dos botones van en la misma fila, simétricos respecto al centro de la ventana,
            //     así que el positivo está en la posición ESPEJO de Cancelar (mismo espacio de
            //     coordenadas de getBoundsInScreen, que es el que usa dispatchGesture).
            val cancel = findCancelButton(root) ?: return false
            val r = Rect(); cancel.getBoundsInScreen(r)
            if (r.width() <= 0 || r.height() <= 0) return false
            val centerX = rootRect.exactCenterX()
            val cancelCx = r.exactCenterX()
            if (kotlin.math.abs(cancelCx - centerX) < rootRect.width() * 0.08f) return false
            val cx = 2f * centerX - cancelCx    // espejo respecto al centro de la ventana
            val cy = r.exactCenterY()
            // El punto espejo DEBE caer dentro de la ventana del diálogo. Si no, las coordenadas
            // todavía están en un espacio transitorio (animación) — no tocar (tocaría fuera del
            // diálogo y MIUI lo DESCARTA sin conceder, que era exactamente el bug).
            if (cx < rootRect.left || cx > rootRect.right || cy < rootRect.top || cy > rootRect.bottom) return false
            target.set((cx - 3).toInt(), (cy - 3).toInt(), (cx + 3).toInt(), (cy + 3).toInt())
            label = "espejo cancel=$r root=$rootRect"
        }

        // GUARDA por PANTALLA REAL: el punto a tocar debe caer DENTRO de la pantalla física. Durante
        // la animación de entrada de MIUI, getBoundsInScreen devuelve coordenadas en un espacio más
        // alto que la pantalla (p. ej. y=2117 en una pantalla de 1650) y el toque caería FUERA,
        // cerrando el diálogo sin conceder. Esta comprobación detecta ese caso al instante (sin
        // depender del tiempo), así el gate de tiempo puede ser mínimo y el autoclick, más rápido.
        val screen = realDisplaySize()
        val tcx = target.exactCenterX(); val tcy = target.exactCenterY()
        if (tcx < 0f || tcx > screen.x.toFloat() || tcy < 0f || tcy > screen.y.toFloat()) {
            lastTargetRect = Rect(target); return false
        }

        // --- Paso B: única condición para tocar YA: que la ventana sea interactiva (con foco/activa) ---
        // La guarda de pantalla de arriba ya descarta las coordenadas transitorias de la animación
        // (el único caso que cerraba el diálogo), así que NO hace falta esperar tiempo ni confirmar
        // estabilidad entre lecturas: en cuanto el diálogo es interactivo y el botón está en pantalla,
        // se toca al instante. Esto hace el autoclick prácticamente inmediato al aparecer el diálogo.
        val win = try { root.window } catch (e: Exception) { null }
        if (win != null && !win.isFocused && !win.isActive) return false

        // --- Paso C: tocar de inmediato ---
        val cx = target.exactCenterX(); val cy = target.exactCenterY()
        android.util.Log.d("AccesA11y", "confirm $label -> tap @ $cx,$cy (instantaneo)")
        if (tapGesture(cx, cy)) {
            AccessibilityBridge.autoConfirmProjectionUntil = 0L
            projectionDialogSeenAt = 0L
            lastTargetRect = null
            return true
        }
        return false
    }

    private fun tryAutoConfirmProjection(): Boolean {
        if (System.currentTimeMillis() >= AccessibilityBridge.autoConfirmProjectionUntil) return false
        for (root in allWindowRoots()) { if (tapConfirmInRoot(root)) return true }
        return false
    }

    /** Textos visibles del árbol, para diagnosticar qué diálogo apareció si no se encuentra el botón. */
    private fun dumpTexts(node: AccessibilityNodeInfo?, depth: Int = 0): String {
        if (node == null || depth > 12) return ""
        val sb = StringBuilder()
        val t = node.text?.toString()
        val d = node.contentDescription?.toString()
        val cls = node.className?.toString()?.substringAfterLast('.')
        if (!t.isNullOrBlank() || !d.isNullOrBlank()) {
            sb.append("{$cls t='${t ?: ""}' d='${d ?: ""}' clk=${node.isClickable}}")
        }
        for (i in 0 until node.childCount) sb.append(dumpTexts(node.getChild(i), depth + 1))
        return sb.toString()
    }

    /** Busca un interruptor apagado en la pantalla actual y lo enciende. */
    private fun tryAutoEnableSwitch(): Boolean {
        if (System.currentTimeMillis() >= AccessibilityBridge.autoEnableOverlayUntil) return false
        val root = rootInActiveWindow ?: return false
        val sw = findUncheckedSwitch(root) ?: return false
        var node: AccessibilityNodeInfo? = sw
        while (node != null) {
            if (node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                AccessibilityBridge.autoEnableOverlayUntil = 0L
                return true
            }
            node = node.parent
        }
        if (sw.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
            AccessibilityBridge.autoEnableOverlayUntil = 0L
            return true
        }
        return false
    }

    private fun findUncheckedSwitch(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        val cls = node.className?.toString() ?: ""
        if (node.isCheckable && !node.isChecked &&
            (cls.contains("Switch") || cls.contains("CompoundButton"))
        ) {
            return node
        }
        for (i in 0 until node.childCount) {
            findUncheckedSwitch(node.getChild(i))?.let { return it }
        }
        return null
    }

    private fun findConfirmNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        val label = (node.text?.toString() ?: node.contentDescription?.toString())?.trim()?.lowercase()
        if (label != null && confirmLabels.any { label == it || label.contains(it) }) return node
        // Botón positivo estándar de un AlertDialog (fallback, ya acotado a SystemUI + tiempo).
        if (node.viewIdResourceName == "android:id/button1") return node
        for (i in 0 until node.childCount) {
            findConfirmNode(node.getChild(i))?.let { return it }
        }
        return null
    }

    override fun onInterrupt() = Unit

    /**
     * Tamaño REAL de la pantalla (incluye barras de estado/navegación), idéntico al que usa
     * ScreenCapturerAndroid para la captura. Usar resources.displayMetrics daría el área útil
     * de la app (sin barras) y desalinearía los toques verticalmente respecto al video.
     */
    private fun realDisplaySize(): Point {
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        return Point(metrics.widthPixels, metrics.heightPixels)
    }

    fun handleControlCommand(json: JSONObject) {
        val size = realDisplaySize()
        when (json.optString("type")) {
            "tap" -> dispatchTap(
                json.getDouble("xNorm").toFloat() * size.x,
                json.getDouble("yNorm").toFloat() * size.y
            )
            "swipe" -> dispatchSwipe(
                json.getDouble("x1Norm").toFloat() * size.x,
                json.getDouble("y1Norm").toFloat() * size.y,
                json.getDouble("x2Norm").toFloat() * size.x,
                json.getDouble("y2Norm").toFloat() * size.y,
                json.optLong("durationMs", 300)
            )
            // Trazo libre por varios puntos (para dibujar un patrón de desbloqueo, firmas, etc.).
            "gesture-path" -> dispatchPath(json, size)
            "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
            "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
            "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
        }
    }

    private fun dispatchTap(x: Float, y: Float) {
        // Toque muy corto (10 ms) para que responda al instante pero registre de forma fiable.
        val path = Path().apply { moveTo(x, y) }
        val stroke = GestureDescription.StrokeDescription(path, 0, 10)
        dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    }

    private fun dispatchSwipe(x1: Float, y1: Float, x2: Float, y2: Float, durationMs: Long) {
        val path = Path().apply {
            moveTo(x1, y1)
            lineTo(x2, y2)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs)
        dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    }

    /**
     * Trazo continuo que pasa por todos los puntos recibidos (points: [{xNorm,yNorm},...]).
     * Permite reproducir un patrón de desbloqueo o cualquier gesto que no sea una línea recta.
     */
    private fun dispatchPath(json: JSONObject, size: Point) {
        val pts = json.optJSONArray("points") ?: return
        if (pts.length() < 2) return
        val path = Path()
        val p0 = pts.getJSONObject(0)
        path.moveTo(p0.getDouble("xNorm").toFloat() * size.x, p0.getDouble("yNorm").toFloat() * size.y)
        for (i in 1 until pts.length()) {
            val p = pts.getJSONObject(i)
            path.lineTo(p.getDouble("xNorm").toFloat() * size.x, p.getDouble("yNorm").toFloat() * size.y)
        }
        val duration = json.optLong("durationMs", 500).coerceIn(50L, 60000L)
        val stroke = GestureDescription.StrokeDescription(path, 0, duration)
        dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    }

    /**
     * Recorre el árbol de accesibilidad de la ventana activa (mismo mecanismo que usa un
     * lector de pantalla) y devuelve cada texto visible con su posición normalizada, para
     * reconstruir la estructura de la pantalla como texto en el navegador.
     */
    fun extractScreenText(): JSONArray {
        val result = JSONArray()
        val root = rootInActiveWindow ?: run {
            android.util.Log.e("AccesA11yService", "extractScreenText: rootInActiveWindow es null")
            return result
        }
        val size = realDisplaySize()
        val rect = Rect()

        fun walk(node: AccessibilityNodeInfo?) {
            if (node == null) return
            val text = node.text?.toString()?.trim()?.takeIf { it.isNotEmpty() }
                ?: node.contentDescription?.toString()?.trim()?.takeIf { it.isNotEmpty() }
            if (text != null) {
                node.getBoundsInScreen(rect)
                if (rect.width() > 0 && rect.height() > 0) {
                    result.put(
                        JSONObject()
                            .put("text", text)
                            .put("xNorm", rect.left.toFloat() / size.x)
                            .put("yNorm", rect.top.toFloat() / size.y)
                            .put("wNorm", rect.width().toFloat() / size.x)
                            .put("hNorm", rect.height().toFloat() / size.y)
                    )
                }
            }
            for (i in 0 until node.childCount) walk(node.getChild(i))
        }

        walk(root)
        return result
    }
}
