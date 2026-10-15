package com.acces.hostapp

import android.content.Context
import android.util.Log
import org.webrtc.DataChannel
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription

/**
 * PeerConnection independiente del de pantalla/cámara, dedicado a transmitir SOLO el audio del
 * micrófono ("escucha en vivo"). Se multiplexa sobre la MISMA sesión de señalización marcando
 * los mensajes con "stream": "mic" (ver HostService.onSignal y host.js del lado navegador).
 */
class MicWebRtcClient(
    private val context: Context,
    private val listener: Listener
) {
    interface Listener {
        fun onLocalIceCandidate(candidate: IceCandidate)
        fun onLocalDescription(description: SessionDescription)
        fun onConnectionFailed()
    }

    private val factory: PeerConnectionFactory = PeerConnectionFactory.builder().createPeerConnectionFactory()
    private var peerConnection: PeerConnection? = null
    private var audioSource: org.webrtc.AudioSource? = null

    fun start(iceServers: List<PeerConnection.IceServer>) {
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

        // Constraints de captura: cancelación de eco/ruido desactivada para oír el ambiente tal cual.
        val audioConstraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("googEchoCancellation", "false"))
            mandatory.add(MediaConstraints.KeyValuePair("googNoiseSuppression", "false"))
            mandatory.add(MediaConstraints.KeyValuePair("googAutoGainControl", "false"))
        }
        val source = factory.createAudioSource(audioConstraints)
        audioSource = source
        val track = factory.createAudioTrack("acces-mic0", source)
        peerConnection?.addTrack(track, listOf("acces-mic-stream"))

        peerConnection?.createOffer(object : MicSdpObserverAdapter() {
            override fun onCreateSuccess(sdp: SessionDescription) {
                peerConnection?.setLocalDescription(MicSdpObserverAdapter(), sdp)
                listener.onLocalDescription(sdp)
            }
        }, MediaConstraints())
    }

    fun setRemoteAnswer(sdp: SessionDescription) {
        peerConnection?.setRemoteDescription(MicSdpObserverAdapter(), sdp)
    }

    fun addRemoteIceCandidate(candidate: IceCandidate) {
        peerConnection?.addIceCandidate(candidate)
    }

    fun close() {
        audioSource?.dispose()
        audioSource = null
        peerConnection?.close()
        peerConnection = null
    }

    companion object {
        private const val TAG = "AccesMicWebRTC"
    }
}

private open class MicSdpObserverAdapter : SdpObserver {
    override fun onCreateSuccess(sdp: SessionDescription) = Unit
    override fun onSetSuccess() = Unit
    override fun onCreateFailure(error: String?) = Unit
    override fun onSetFailure(error: String?) = Unit
}
