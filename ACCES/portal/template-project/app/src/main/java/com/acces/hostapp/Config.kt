package com.acces.hostapp

object Config {
    /** Servidor de emparejamiento/señalización (inyectado desde build.gradle). */
    val SIGNALING_SERVER_URL = BuildConfig.SIGNALING_SERVER_URL

    /** Mismo servidor, por HTTPS, para pedir credenciales TURN frescas (ver /turn-credentials). */
    val SIGNALING_SERVER_HTTP_URL: String =
        SIGNALING_SERVER_URL.replace("wss://", "https://").replace("ws://", "http://")
}
