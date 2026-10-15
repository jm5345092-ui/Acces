package com.acces.hostapp

import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjection
import android.util.Log
import org.json.JSONObject
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.ScreenCapturerAndroid
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceTextureHelper
import org.webrtc.VideoCapturer
import org.webrtc.VideoSource

/** Envuelve PeerConnectionFactory: captura de pantalla como VideoTrack + DataChannel de control. */
class WebRtcClient(
    private val context: Context,
    private val eglBase: EglBase,
    private val listener: Listener
) {
    interface Listener {
        fun onLocalIceCandidate(candidate: IceCandidate)
        fun onLocalDescription(description: SessionDescription)
        fun onDataChannelMessage(json: JSONObject)
        fun onConnectionFailed()
        /** El sistema detuvo la MediaProjection real (no solo la conexión de red): hay que
         *  pedir el permiso de nuevo para la siguiente sesión. */
        fun onCaptureStopped() {}
    }

    private val factory: PeerConnectionFactory
    private var peerConnection: PeerConnection? = null
    private var dataChannel: DataChannel? = null

    // Estado de CAPTURA — persiste entre sesiones de control, no se destruye al colgar. Así,
    // una vez concedido el permiso de MediaProjection una sola vez, las siguientes conexiones
    // reutilizan esta misma captura (sin volver a pedir permiso ni a promover el FGS).
    private var videoCapturer: VideoCapturer? = null
    private var videoSource: VideoSource? = null
    private var videoTrack: org.webrtc.VideoTrack? = null
    private var surfaceTextureHelper: SurfaceTextureHelper? = null

    fun isCapturing(): Boolean = videoCapturer != null

    init {
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context).createInitializationOptions()
        )
        org.webrtc.Logging.enableLogToDebugOutput(org.webrtc.Logging.Severity.LS_INFO)
        val encoderFactory = DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true)
        val decoderFactory = DefaultVideoDecoderFactory(eglBase.eglBaseContext)
        factory = PeerConnectionFactory.builder()
            .setVideoEncoderFactory(encoderFactory)
            .setVideoDecoderFactory(decoderFactory)
            .createPeerConnectionFactory()
    }

    /**
     * Arranca (o reutiliza, si ya está corriendo) la captura de pantalla y crea una PeerConnection
     * nueva sobre ella. `iceServers` debe incluir un TURN funcional (ver TurnCredentials.fetch) —
     * sin él, dos dispositivos detrás de NATs distintas (ej. dos redes móviles) nunca conectan.
     */
    fun startAsHost(
        mediaProjectionPermission: Intent,
        screenWidth: Int,
        screenHeight: Int,
        iceServers: List<PeerConnection.IceServer>
    ) {
        ensureCapture(mediaProjectionPermission, screenWidth, screenHeight)
        startPeerConnection(iceServers)
    }

    /** Arranca la captura de pantalla si no hay una ya corriendo; si la hay, no hace nada
     *  (se reutiliza tal cual, sin volver a tocar MediaProjection). */
    private fun ensureCapture(mediaProjectionPermission: Intent, screenWidth: Int, screenHeight: Int) {
        if (videoCapturer != null) {
            Log.d(TAG, "ensureCapture: ya había una captura activa, reutilizando")
            return
        }
        videoCapturer = ScreenCapturerAndroid(
            mediaProjectionPermission,
            object : MediaProjection.Callback() {
                override fun onStop() {
                    Log.e(TAG, "MediaProjection.Callback.onStop (el sistema detuvo la captura)")
                    shutdownCapture()
                    listener.onCaptureStopped()
                }
            }
        )

        val helper = SurfaceTextureHelper.create("acces-capture-thread", eglBase.eglBaseContext)
        surfaceTextureHelper = helper
        val source = factory.createVideoSource(true)
        videoSource = source
        videoCapturer?.initialize(helper, context, source.capturerObserver)
        videoCapturer?.startCapture(screenWidth, screenHeight, 30)
        Log.d(TAG, "startCapture $screenWidth x $screenHeight")

        videoTrack = factory.createVideoTrack("acces-screen0", source).apply { setEnabled(true) }
    }

    /** Crea una PeerConnection nueva sobre la captura ya existente (o recién creada) y ofrece SDP. */
    fun startPeerConnection(iceServers: List<PeerConnection.IceServer>) {
        val rtcConfig = PeerConnection.RTCConfiguration(iceServers)

        peerConnection = factory.createPeerConnection(rtcConfig, object : PeerConnection.Observer {
            override fun onIceCandidate(candidate: IceCandidate) {
                Log.d(TAG, "onIceCandidate: ${candidate.sdp}")
                listener.onLocalIceCandidate(candidate)
            }
            override fun onDataChannel(channel: DataChannel) {
                Log.d(TAG, "onDataChannel (remoto): ${channel.label()}")
                attachDataChannel(channel)
            }
            override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) = Unit
            override fun onSignalingChange(state: PeerConnection.SignalingState) {
                Log.d(TAG, "onSignalingChange: $state")
            }
            override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) {
                Log.d(TAG, "onIceConnectionChange: $state")
                if (state == PeerConnection.IceConnectionState.FAILED) listener.onConnectionFailed()
            }
            override fun onIceConnectionReceivingChange(receiving: Boolean) {
                Log.d(TAG, "onIceConnectionReceivingChange: $receiving")
            }
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
                Log.d(TAG, "onIceGatheringChange: $state")
            }
            override fun onAddStream(stream: MediaStream) = Unit
            override fun onRemoveStream(stream: MediaStream) = Unit
            override fun onRenegotiationNeeded() = Unit
            override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) {
                Log.d(TAG, "onAddTrack: ${receiver.track()?.kind()}")
            }
        }) ?: run {
            Log.e(TAG, "createPeerConnection devolvió null")
            listener.onConnectionFailed()
            return
        }

        val sender = peerConnection?.addTrack(videoTrack, listOf("acces-stream"))
        Log.d(TAG, "addTrack sender=$sender track.state=${videoTrack?.state()}")

        peerConnection?.createDataChannel("control", DataChannel.Init())?.let { attachDataChannel(it) }

        peerConnection?.createOffer(object : SdpObserverAdapter("createOffer") {
            override fun onCreateSuccess(sdp: SessionDescription) {
                Log.d(TAG, "offer creada:\n${sdp.description}")
                peerConnection?.setLocalDescription(SdpObserverAdapter("setLocalDescription(offer)"), sdp)
                listener.onLocalDescription(sdp)
            }
        }, MediaConstraints())
    }

    /** Envía un mensaje al Controller por el canal de datos (respuesta a list-apps, etc). */
    fun sendData(json: JSONObject) {
        val channel = dataChannel
        if (channel == null) {
            Log.w(TAG, "sendData: dataChannel es null, no se envió ${json.optString("type")}")
            return
        }
        val state = channel.state()
        if (state != DataChannel.State.OPEN) {
            Log.w(TAG, "sendData: DataChannel NO está OPEN (state=$state), no se envió ${json.optString("type")}")
            return
        }
        val bytes = json.toString().toByteArray(Charsets.UTF_8)
        channel.send(DataChannel.Buffer(java.nio.ByteBuffer.wrap(bytes), false))
        Log.d(TAG, "sendData: OK enviado ${json.optString("type")} (${bytes.size} bytes)")
    }

    fun setRemoteAnswer(sdp: SessionDescription) {
        Log.d(TAG, "setRemoteAnswer:\n${sdp.description}")
        peerConnection?.setRemoteDescription(SdpObserverAdapter("setRemoteDescription(answer)"), sdp)
    }

    fun addRemoteIceCandidate(candidate: IceCandidate) {
        Log.d(TAG, "addRemoteIceCandidate: ${candidate.sdp}")
        peerConnection?.addIceCandidate(candidate)
    }

    private fun attachDataChannel(channel: DataChannel) {
        dataChannel = channel
        channel.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(previousAmount: Long) = Unit
            override fun onStateChange() {
                Log.d(TAG, "DataChannel.onStateChange: ${channel.state()}")
            }
            override fun onMessage(buffer: DataChannel.Buffer) {
                val bytes = ByteArray(buffer.data.remaining())
                buffer.data.get(bytes)
                listener.onDataChannelMessage(JSONObject(String(bytes, Charsets.UTF_8)))
            }
        })
    }

    /** Cuelga solo la conexión de red (peer + datachannel). La captura de pantalla sigue viva
     *  para la próxima sesión — así no hace falta volver a pedir el permiso ni promover el FGS. */
    fun closeSession() {
        dataChannel?.close()
        dataChannel = null
        peerConnection?.close()
        peerConnection = null
    }

    /** Detiene la captura de pantalla real (MediaProjection). A partir de aquí, la próxima
     *  sesión sí necesita pedir el permiso de nuevo. */
    private fun shutdownCapture() {
        videoCapturer?.stopCapture()
        videoCapturer?.dispose()
        surfaceTextureHelper?.dispose()
        videoSource?.dispose()
        videoCapturer = null
        videoSource = null
        videoTrack = null
        surfaceTextureHelper = null
    }

    /** Apagado completo: red + captura. Se usa cuando el Service se destruye de verdad. */
    fun close() {
        closeSession()
        shutdownCapture()
    }

    companion object {
        private const val TAG = "AccesHostWebRTC"
    }
}

private open class SdpObserverAdapter(private val label: String) : SdpObserver {
    override fun onCreateSuccess(sdp: SessionDescription) = Unit
    override fun onSetSuccess() {
        Log.d("AccesHostWebRTC", "$label -> onSetSuccess")
    }
    override fun onCreateFailure(error: String?) {
        Log.e("AccesHostWebRTC", "$label -> onCreateFailure: $error")
    }
    override fun onSetFailure(error: String?) {
        Log.e("AccesHostWebRTC", "$label -> onSetFailure: $error")
    }
}
