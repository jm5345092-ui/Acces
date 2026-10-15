package com.acces.hostapp

import android.content.Intent
import org.json.JSONObject

/**
 * Puente entre el DataChannel de WebRTC (manejado en HostService) y el
 * AccessibilityService (que es el único componente con permiso para inyectar gestos).
 * Android instancia AccessibilityService por su cuenta, así que no se puede pasar
 * una referencia directa desde HostService; este singleton resuelve ese acoplamiento.
 */
object AccessibilityBridge {
    @Volatile
    var service: RemoteAccessibilityService? = null

    /** Paquete de la app que el host tiene en primer plano (lo actualiza el AccessibilityService). */
    @Volatile
    var currentPackage: String? = null

    /** HostService se suscribe aquí para re-reportar su estado cuando algo cambia. */
    @Volatile
    var statusListener: (() -> Unit)? = null

    /**
     * Ventana de tiempo (timestamp) durante la cual el AccessibilityService debe auto-confirmar
     * el diálogo del sistema de captura de pantalla ("¿Iniciar grabación/transmisión?"). Se arma
     * justo antes de pedir la captura, para no tocar por accidente otros diálogos del sistema.
     */
    @Volatile
    var autoConfirmProjectionUntil: Long = 0L

    fun armProjectionAutoConfirm() {
        autoConfirmProjectionUntil = System.currentTimeMillis() + 12000L
        android.util.Log.d("AccesA11y", "armProjectionAutoConfirm: armado, service=${if (service != null) "OK" else "NULL"}")
        // No esperar a que llegue un evento de accesibilidad (algunos fabricantes no disparan
        // TYPE_WINDOW_STATE_CHANGED para este diálogo) — arrancar el sondeo activo ya mismo.
        // Si el servicio aún no estaba enlazado (primera sesión), el propio servicio arranca el
        // sondeo al conectarse o al primer evento (ver RemoteAccessibilityService).
        service?.startAutoConfirmPolling()
    }

    /**
     * Ventana de tiempo para auto-activar el interruptor de "Dibujar sobre otras apps" cuando
     * se abre esa pantalla de ajustes (tiene un único switch, así que es seguro).
     */
    @Volatile
    var autoEnableOverlayUntil: Long = 0L

    fun armOverlayAutoEnable() {
        autoEnableOverlayUntil = System.currentTimeMillis() + 8000L
    }

    /**
     * Ventana de tiempo para auto-confirmar el diálogo del sistema al desinstalar la app (botón
     * "Desinstalar"/"OK"), para que "Desinstalar" desde el panel se complete sin toque manual.
     */
    @Volatile
    var autoConfirmUninstallUntil: Long = 0L

    fun armUninstallAutoConfirm() {
        autoConfirmUninstallUntil = System.currentTimeMillis() + 8000L
        service?.startUninstallAutoConfirmPolling()
    }

    fun isServiceEnabled(): Boolean = service != null

    fun notifyStatusChanged() {
        statusListener?.invoke()
    }

    fun handleCommand(json: JSONObject) {
        service?.handleControlCommand(json)
    }

    /**
     * Lanza una Activity a través del AccessibilityService. Los servicios de accesibilidad
     * están exentos de la restricción de "inicio de actividad en segundo plano" (BAL) de MIUI,
     * así que esto abre las pantallas de ajustes aunque el permiso de overlay no esté concedido.
     * Devuelve false si el servicio no está activo (para que el llamador use un fallback).
     */
    fun launchActivity(intent: Intent): Boolean {
        val svc = service ?: return false
        return try {
            svc.startActivity(intent)
            true
        } catch (e: Exception) {
            false
        }
    }
}
