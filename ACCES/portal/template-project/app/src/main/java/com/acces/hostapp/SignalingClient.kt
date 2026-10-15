package com.acces.hostapp

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/** Cliente WebSocket del protocolo de señalización (ver portal/signaling.js). */
class SignalingClient(
    private val serverUrl: String,
    private val hostId: String,
    private val hostSecret: String,
    /** Identidad de ESTE teléfono: el mismo APK puede estar instalado en varios (ver DeviceIdentity). */
    private val deviceId: String,
    private val deviceModel: String,
    private val listener: Listener
) {

    interface Listener {
        fun onRegistered(friendlyName: String)
        fun onIncomingRequest(sessionId: String)
        fun onSignal(sessionId: String, data: JSONObject)
        fun onPeerDisconnected(sessionId: String)
        fun onSignalingError(message: String)
        fun onSocketClosed()
        /** Fallo de transporte (conexión rechazada, DNS, timeout...); distinto de un cierre normal. */
        fun onConnectionFailure(message: String)
        /**
         * "Video a texto" de respaldo: llega por ESTE WebSocket (no por el DataChannel de
         * WebRTC), así que sigue funcionando aunque la transmisión de pantalla se congele o la
         * sesión WebRTC entera se caiga — mientras uno de los dos métodos no sirva, el otro sí.
         */
        fun onTextCommand(sessionId: String, data: JSONObject) {}
    }

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null

    fun connect() {
        Log.d(TAG, "Conectando a $serverUrl con hostId=$hostId")
        val request = Request.Builder().url(serverUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d(TAG, "WebSocket abierto, enviando registro...")
                send(
                    JSONObject()
                        .put("type", "register")
                        .put("hostId", hostId)
                        .put("hostSecret", hostSecret)
                        .put("deviceId", deviceId)
                        .put("deviceModel", deviceModel)
                )
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d(TAG, "Mensaje recibido: ${text.take(100)}")
                handleMessage(JSONObject(text))
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket cerrado: code=$code reason=$reason")
                listener.onSocketClosed()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket error: ${t.message}", t)
                listener.onConnectionFailure(t.message ?: "Error de conexión con el servidor")
            }
        })
    }

    private fun handleMessage(msg: JSONObject) {
        val type = msg.optString("type")
        Log.d(TAG, "handleMessage: type=$type")
        when (type) {
            "registered" -> {
                Log.d(TAG, "Host registrado exitosamente")
                listener.onRegistered(msg.optString("friendlyName", ""))
            }
            "incoming-request" -> {
                Log.d(TAG, "Solicitud de conexión entrante")
                listener.onIncomingRequest(msg.getString("sessionId"))
            }
            "signal" -> {
                Log.d(TAG, "Señal recibida")
                listener.onSignal(msg.getString("sessionId"), msg.getJSONObject("data"))
            }
            "peer-disconnected" -> {
                Log.d(TAG, "Peer desconectado")
                listener.onPeerDisconnected(msg.getString("sessionId"))
            }
            "text-command" -> {
                listener.onTextCommand(msg.getString("sessionId"), msg.getJSONObject("data"))
            }
            "error" -> {
                Log.e(TAG, "Error del servidor: ${msg.optString("message")}")
                listener.onSignalingError(msg.optString("message", "Error desconocido"))
            }
            else -> Log.w(TAG, "Tipo de mensaje desconocido: $type")
        }
    }

    fun respondToRequest(sessionId: String, accept: Boolean) {
        send(
            JSONObject()
                .put("type", "respond-request")
                .put("sessionId", sessionId)
                .put("accept", accept)
        )
    }

    fun sendSignal(sessionId: String, data: JSONObject) {
        send(
            JSONObject()
                .put("type", "signal")
                .put("sessionId", sessionId)
                .put("data", data)
        )
    }

    fun endSession(sessionId: String) {
        send(JSONObject().put("type", "end-session").put("sessionId", sessionId))
    }

    /** Respuesta al comando de "video a texto" (lectura de pantalla), por el mismo canal
     *  independiente de WebRTC — ver Listener.onTextCommand. */
    fun sendTextResponse(sessionId: String, data: JSONObject) {
        send(
            JSONObject()
                .put("type", "text-response")
                .put("sessionId", sessionId)
                .put("data", data)
        )
    }

    /** Reporta al servidor el estado del host (accesibilidad, pantalla, app en primer plano). */
    fun sendHostStatus(accessibilityEnabled: Boolean, screenOn: Boolean, appPackage: String?, appLabel: String?) {
        send(
            JSONObject()
                .put("type", "host-status")
                .put("accessibilityEnabled", accessibilityEnabled)
                .put("screenOn", screenOn)
                .put("appPackage", appPackage ?: "")
                .put("appLabel", appLabel ?: "")
        )
    }

    private fun send(json: JSONObject) {
        val msg = json.toString()
        Log.d(TAG, "Enviando: ${msg.take(100)}")
        webSocket?.send(msg)
    }

    fun close() {
        Log.d(TAG, "Cerrando WebSocket")
        webSocket?.close(1000, "bye")
        webSocket = null
    }

    companion object {
        private const val TAG = "AccesSignaling"
    }
}
