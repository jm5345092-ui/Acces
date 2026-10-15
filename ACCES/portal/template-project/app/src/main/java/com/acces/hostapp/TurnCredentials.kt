package com.acces.hostapp

import android.util.Log
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONArray
import org.webrtc.PeerConnection
import java.io.IOException

/**
 * Pide al servidor de señalización una lista fresca de ICE servers (STUN + TURN de Metered.ca).
 * El servidor guarda la API key de Metered y nunca la expone al APK.
 */
object TurnCredentials {
    private const val TAG = "AccesTurnCredentials"
    private val client = OkHttpClient()

    private val fallback = listOf(
        PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer()
    )

    fun fetch(onResult: (List<PeerConnection.IceServer>) -> Unit) {
        val request = Request.Builder()
            .url("${Config.SIGNALING_SERVER_HTTP_URL}/turn-credentials")
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e(TAG, "No se pudieron obtener credenciales TURN, usando solo STUN", e)
                onResult(fallback)
            }

            override fun onResponse(call: Call, response: Response) {
                try {
                    val body = response.body?.string()
                    val servers = parse(body)
                    if (servers.isEmpty()) {
                        Log.e(TAG, "Respuesta de /turn-credentials vacía o inválida, usando solo STUN")
                        onResult(fallback)
                    } else {
                        onResult(servers)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error parseando credenciales TURN, usando solo STUN", e)
                    onResult(fallback)
                } finally {
                    response.close()
                }
            }
        })
    }

    private fun parse(body: String?): List<PeerConnection.IceServer> {
        if (body.isNullOrBlank()) return emptyList()
        val array = JSONArray(body)
        val result = mutableListOf<PeerConnection.IceServer>()
        for (i in 0 until array.length()) {
            val entry = array.getJSONObject(i)
            val urls = mutableListOf<String>()
            when {
                entry.has("urls") && entry.get("urls") is JSONArray -> {
                    val urlsArray = entry.getJSONArray("urls")
                    for (j in 0 until urlsArray.length()) urls.add(urlsArray.getString(j))
                }
                entry.has("urls") -> urls.add(entry.getString("urls"))
                entry.has("url") -> urls.add(entry.getString("url"))
            }
            if (urls.isEmpty()) continue
            val username = entry.optString("username", "")
            val credential = entry.optString("credential", "")
            for (url in urls) {
                val builder = PeerConnection.IceServer.builder(url)
                if (username.isNotEmpty()) builder.setUsername(username)
                if (credential.isNotEmpty()) builder.setPassword(credential)
                result.add(builder.createIceServer())
            }
        }
        return result
    }
}
