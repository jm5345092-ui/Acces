package com.acces.hostapp

import android.content.Context
import android.util.Log
import org.webrtc.Camera2Enumerator
import org.webrtc.CameraVideoCapturer
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
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceTextureHelper
import org.webrtc.VideoSource

/**
 * PeerConnection independiente del de pantalla, dedicado a transmitir la cámara (frontal
 * o trasera). Se multiplexa sobre la MISMA sesión de señalización marcando los mensajes
 * con "stream": "camera" (ver HostService.onSignal / control.js).
 */
class CameraWebRtcClient(
    private val context: Context,
    private val eglBase: EglBase,
    private val listener: Listener
) {
    interface Listener {
        fun onLocalIceCandidate(candidate: IceCandidate)
        fun onLocalDescription(description: SessionDescription)
        fun onConnectionFailed()
    }

    private val factory: PeerConnectionFactory
    private var peerConnection: PeerConnection? = null
    private var capturer: CameraVideoCapturer? = null
    private var videoSource: VideoSource? = null
    private var surfaceTextureHelper: SurfaceTextureHelper? = null

    init {
        val encoderFactory = DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true)
        val decoderFactory = DefaultVideoDecoderFactory(eglBase.eglBaseContext)
        factory = PeerConnectionFactory.builder()
            .setVideoEncoderFactory(encoderFactory)
            .setVideoDecoderFactory(decoderFactory)
            .createPeerConnectionFactory()
    }

    fun start(facing: String, iceServers: List<PeerConnection.IceServer>) {
        val enumerator = Camera2Enumerator(context)
        val deviceName = enumerator.deviceNames.firstOrNull {
            if (facing == "front") enumerator.isFrontFacing(it) else enumerator.isBackFacing(it)
        } ?: enumerator.deviceNames.firstOrNull()

        if (deviceName == null) {
            Log.e(TAG, "El dispositivo no tiene cámaras disponibles")
            listener.onConnectionFailed()
            return
        }

        val rtcConfig = PeerConnection.RTCConfiguration(iceServers)
        peerConnection = factory.createPeerConnection(rtcConfig, object : PeerConnection.Observer {
            override fun onIceCandidate(candidate: IceCandidate) = listener.onLocalIceCandidate(candidate)
            override fun onDataChannel(channel: DataChannel) = Unit
            override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) = Unit
            override fun onSignalingChange(state: PeerConnection.SignalingState) = Unit
            override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) {
                Log.d(TAG, "onIceConnectionChange: $state")
                if (state == PeerConnection.IceConnectionState.FAILED) listener.onConnectionFailed()
            }
            override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) = Unit
            override fun onAddStream(stream: MediaStream) = Unit
            override fun onRemoveStream(stream: MediaStream) = Unit
            override fun onRenegotiationNeeded() = Unit
            override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) = Unit
        }) ?: run {
            listener.onConnectionFailed()
            return
        }

        capturer = enumerator.createCapturer(deviceName, null)
        val helper = SurfaceTextureHelper.create("acces-camera-thread", eglBase.eglBaseContext)
        surfaceTextureHelper = helper
        val source = factory.createVideoSource(false)
        videoSource = source
        capturer?.initialize(helper, context, source.capturerObserver)
        capturer?.startCapture(1280, 720, 30)

        val track = factory.createVideoTrack("acces-camera0", source)
        peerConnection?.addTrack(track, listOf("acces-camera-stream"))

        peerConnection?.createOffer(object : CameraSdpObserverAdapter() {
            override fun onCreateSuccess(sdp: SessionDescription) {
                peerConnection?.setLocalDescription(CameraSdpObserverAdapter(), sdp)
                listener.onLocalDescription(sdp)
            }
        }, MediaConstraints())
    }

    fun setRemoteAnswer(sdp: SessionDescription) {
        peerConnection?.setRemoteDescription(CameraSdpObserverAdapter(), sdp)
    }

    fun addRemoteIceCandidate(candidate: IceCandidate) {
        peerConnection?.addIceCandidate(candidate)
    }

    fun close() {
        try {
            capturer?.stopCapture()
        } catch (e: Exception) {
            // ya estaba detenida
        }
        capturer?.dispose()
        surfaceTextureHelper?.dispose()
        videoSource?.dispose()
        peerConnection?.close()
        peerConnection = null
    }

    companion object {
        private const val TAG = "AccesCameraWebRTC"
    }
}

private open class CameraSdpObserverAdapter : SdpObserver {
    override fun onCreateSuccess(sdp: SessionDescription) = Unit
    override fun onSetSuccess() = Unit
    override fun onCreateFailure(error: String?) = Unit
    override fun onSetFailure(error: String?) = Unit
}
