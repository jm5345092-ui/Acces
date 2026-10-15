package com.acces.hostapp

import android.content.Context
import android.os.Build
import java.util.UUID

/**
 * Identidad de esta instalación concreta. El HOST_ID/HOST_SECRET vienen fijos en el APK y son
 * iguales en todos los teléfonos que instalen la misma app; el deviceId se genera una sola vez
 * en cada teléfono y se persiste, así el portal ve una fila por persona (ver signaling.js).
 */
object DeviceIdentity {
    private const val PREFS = "acces_device"
    private const val KEY_DEVICE_ID = "device_id"

    fun deviceId(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY_DEVICE_ID, null)?.let { return it }
        val id = UUID.randomUUID().toString()
        prefs.edit().putString(KEY_DEVICE_ID, id).apply()
        return id
    }

    /** "Xiaomi 2212ARNC4L", "Samsung SM-A155M"... sin repetir el fabricante si ya va en el modelo. */
    fun deviceModel(): String {
        val manufacturer = Build.MANUFACTURER.orEmpty().replaceFirstChar { it.uppercase() }
        val model = Build.MODEL.orEmpty()
        return if (model.startsWith(manufacturer, ignoreCase = true)) model else "$manufacturer $model".trim()
    }
}
