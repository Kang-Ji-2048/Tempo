package com.tempo.app.feature.live

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.net.Uri
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.framework.image.MPImage
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarkerResult
import com.tempo.app.BuildConfig
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.feature.audio.CueEvent
import com.tempo.app.feature.audio.CuePlayer
import com.tempo.app.feature.voice.VoiceConversationManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import javax.inject.Inject

enum class LiveConnection { DISCONNECTED, CONNECTING, LIVE, ERROR }

data class LiveUiState(
    val connection: LiveConnection = LiveConnection.DISCONNECTED,
    val statusMessage: String? = null,
    val sport: String? = null,
    val skill: String? = null,
    val level: String? = null,
    val thresholdDeg: Double? = null,
    val activeLesson: String? = null,
    val elbowDeg: Double? = null,
    val kneeDeg: Double? = null,
    val reps: Int = 0,
    val poseVisible: Boolean = false,
    val sentFps: Int = 0,
    val activeCueText: String = "Start the live drill to get form cues",
    val lastCueFocus: String? = null,
    val cooldownRemainingMs: Long = 0L,
    val totalCuesPlayed: Int = 0,
    val totalCuesSuppressed: Int = 0,
    val cuesHeldForVoice: Int = 0,
    val lastEventLog: String? = null,
) {
    val isStreaming: Boolean get() = connection == LiveConnection.LIVE
}

/** One detected pose: 33 x [x, y, z, visibility] in normalized, upright image coordinates. */
data class LivePose(val landmarks: List<FloatArray>, val aspect: Float, val timestampMs: Long)

/**
 * Live camera drill mode: streams on-device MediaPipe pose landmarks (~14 Hz) to
 * `ws://…/api/v1/live/stream`, which grades each rep against the athlete's active skill and returns
 * short cues. Form cues go through [CuePlayer] (10 s cooldown); voice answers are spoken immediately
 * by [VoiceConversationManager], and form cues are held while Thea is listening or talking.
 */
@HiltViewModel
class LiveViewModel @Inject constructor(
    private val cuePlayer: CuePlayer,
    private val voice: VoiceConversationManager,
    private val identity: PlayerIdentity,
    okHttpClient: OkHttpClient,
) : ViewModel() {

    private val _uiState = MutableStateFlow(LiveUiState())
    val uiState: StateFlow<LiveUiState> = _uiState.asStateFlow()

    private val _pose = MutableStateFlow<LivePose?>(null)
    /** Latest skeleton for the overlay; updated every analyzed frame, independent of streaming. */
    val pose: StateFlow<LivePose?> = _pose.asStateFlow()

    // Same auth interceptor as REST (it also runs for the WebSocket handshake), but no read timeout.
    private val wsClient = okHttpClient.newBuilder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()
    private val json = Json { ignoreUnknownKeys = true }
    private var socket: WebSocket? = null
    @Volatile private var lastSentMs = 0L
    @Volatile private var framesThisSecond = 0
    @Volatile private var fpsWindowStartMs = 0L

    init {
        viewModelScope.launch {
            cuePlayer.cueEvents.collect { event ->
                when (event) {
                    is CueEvent.Played -> _uiState.update {
                        it.copy(totalCuesPlayed = it.totalCuesPlayed + 1,
                            lastEventLog = "Cue played: \"${event.cueText}\"")
                    }
                    is CueEvent.Suppressed -> _uiState.update {
                        it.copy(totalCuesSuppressed = it.totalCuesSuppressed + 1,
                            lastEventLog = "Cue held: ${event.remainingCooldownMs / 1000 + 1}s cooldown left")
                    }
                }
            }
        }
        viewModelScope.launch {
            // A voice command ("switch me to advanced") changes athlete_memory: re-read the active skill.
            voice.exchanges.collect { exchange ->
                if (exchange.channel == "live") socket?.send("""{"type":"refresh"}""")
            }
        }
        viewModelScope.launch {
            while (true) {
                _uiState.update { it.copy(cooldownRemainingMs = cuePlayer.getCooldownRemainingMs()) }
                delay(250)
            }
        }
    }

    fun toggleLive() = if (socket == null) startLive() else stopLive()

    fun startLive() {
        if (socket != null) return
        val base = BuildConfig.BASE_URL.trimEnd('/').replaceFirst("http", "ws")
        val url = "$base/api/v1/live/stream?user_id=${Uri.encode(identity.userId)}"
        _uiState.update { it.copy(connection = LiveConnection.CONNECTING, statusMessage = "Connecting to Thea…") }
        socket = wsClient.newWebSocket(Request.Builder().url(url).build(), listener)
    }

    fun stopLive() {
        socket?.close(1000, "drill finished")
        socket = null
        cuePlayer.stop()
        _uiState.update { it.copy(connection = LiveConnection.DISCONNECTED, statusMessage = null, sentFps = 0) }
    }

    /** Called on the camera analyzer thread for every detected pose. */
    fun onPose(pose: LivePose) {
        _pose.value = pose
        val ws = socket ?: return
        if (_uiState.value.connection != LiveConnection.LIVE) return
        val now = SystemClock.elapsedRealtime()
        if (now - lastSentMs < SEND_INTERVAL_MS) return
        lastSentMs = now
        ws.send(encodePose(pose))
        framesThisSecond++
        if (now - fpsWindowStartMs >= 1000) {
            val fps = framesThisSecond
            framesThisSecond = 0
            fpsWindowStartMs = now
            _uiState.update { it.copy(sentFps = fps) }
        }
    }

    fun onPoseLost() {
        _pose.value = null
    }

    private fun encodePose(pose: LivePose): String = buildString(33 * 40) {
        append("""{"type":"pose","timestamp_ms":""").append(pose.timestampMs)
        append(""","aspect":""").append(pose.aspect).append(""","landmarks":[""")
        pose.landmarks.forEachIndexed { i, lm ->
            if (i > 0) append(',')
            append('[').append(lm[0]).append(',').append(lm[1]).append(',').append(lm[2]).append(',').append(lm[3]).append(']')
        }
        append("]}")
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            webSocket.send("""{"type":"hello"}""")
            _uiState.update { it.copy(connection = LiveConnection.LIVE, statusMessage = "Live: step into frame and swing") }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val msg = runCatching { json.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
            viewModelScope.launch { handle(msg) }
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, null)
            onClosed(code)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.w(TAG, "Live stream failed", t)
            if (socket === webSocket) socket = null
            _uiState.update {
                it.copy(connection = LiveConnection.ERROR, sentFps = 0,
                    // A rejected handshake (closed before accept) surfaces here as HTTP 401/403.
                    statusMessage = when (response?.code) {
                        401 -> "Sign in again to use live mode."
                        403 -> "This live session belongs to another player."
                        else -> "Live coaching disconnected (${t.message ?: "network"}). Tap Start to retry."
                    })
            }
        }

        private fun onClosed(code: Int) {
            socket = null
            _uiState.update {
                it.copy(connection = LiveConnection.DISCONNECTED, sentFps = 0, statusMessage = when (code) {
                    4401 -> "Sign in again to use live mode."
                    4403 -> "This live session belongs to another player."
                    else -> null
                })
            }
        }
    }

    private fun handle(msg: JsonObject) {
        fun text(key: String) = (msg[key] as? JsonPrimitive)?.contentOrNull
        fun number(key: String) = (msg[key] as? JsonPrimitive)?.doubleOrNull
        when (text("type")) {
            "session" -> _uiState.update {
                it.copy(sport = text("sport"), skill = text("skill"), level = text("level"),
                    thresholdDeg = number("threshold_deg"), activeLesson = text("active_lesson"))
            }
            "metrics" -> _uiState.update {
                it.copy(elbowDeg = number("elbow_deg"), kneeDeg = number("knee_deg"),
                    reps = (msg["reps"] as? JsonPrimitive)?.intOrNull ?: it.reps, poseVisible = true)
            }
            "cue" -> {
                val cue = text("cue") ?: return
                _uiState.update {
                    it.copy(activeCueText = cue, lastCueFocus = text("focus"),
                        reps = (msg["rep"] as? JsonPrimitive)?.intOrNull ?: it.reps,
                        poseVisible = text("focus") != "framing")
                }
                if (voice.isBusy) {
                    _uiState.update { it.copy(cuesHeldForVoice = it.cuesHeldForVoice + 1, lastEventLog = "Cue held while Thea talks") }
                } else {
                    cuePlayer.playCue(cueText = cue)
                }
            }
            else -> text("error")?.let { error -> _uiState.update { it.copy(lastEventLog = "Server: $error") } }
        }
    }

    override fun onCleared() {
        stopLive()
        super.onCleared()
    }

    companion object {
        private const val TAG = "LiveViewModel"
        private const val SEND_INTERVAL_MS = 70L // ~14 Hz
    }
}

/**
 * CameraX analyzer running MediaPipe Pose Landmarker (LIVE_STREAM) on upright frames and reporting
 * the 33 normalized landmarks of the first detected person.
 */
class LivePoseAnalyzer(
    context: Context,
    private val onPose: (LivePose) -> Unit,
    private val onNoPose: () -> Unit,
) : ImageAnalysis.Analyzer {
    private val busy = AtomicBoolean(false)
    @Volatile private var frameAspect = 0.75f
    private val landmarker: PoseLandmarker? = try {
        PoseLandmarker.createFromOptions(
            context,
            PoseLandmarker.PoseLandmarkerOptions.builder()
                .setBaseOptions(BaseOptions.builder().setModelAssetPath("pose_landmarker_lite.task").build())
                .setRunningMode(RunningMode.LIVE_STREAM)
                .setMinPoseDetectionConfidence(0.5f)
                .setMinPosePresenceConfidence(0.5f)
                .setMinTrackingConfidence(0.5f)
                .setResultListener(::onResult)
                .setErrorListener { busy.set(false) }
                .build(),
        )
    } catch (e: Exception) {
        Log.e("LivePoseAnalyzer", "Pose landmarker unavailable", e)
        null
    }

    val isAvailable: Boolean get() = landmarker != null

    override fun analyze(image: ImageProxy) {
        val detector = landmarker
        if (detector == null || !busy.compareAndSet(false, true)) {
            image.close()
            return
        }
        try {
            val rotation = image.imageInfo.rotationDegrees
            val bitmap = image.toBitmap()
            val upright = if (rotation != 0) {
                Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height,
                    Matrix().apply { postRotate(rotation.toFloat()) }, true)
            } else bitmap
            frameAspect = upright.width.toFloat() / upright.height
            val mpImage: MPImage = BitmapImageBuilder(upright).build()
            detector.detectAsync(mpImage, SystemClock.uptimeMillis())
        } catch (e: Exception) {
            busy.set(false)
        } finally {
            image.close()
        }
    }

    private fun onResult(result: PoseLandmarkerResult, input: MPImage) {
        try {
            val person = result.landmarks().firstOrNull()
            if (person.isNullOrEmpty()) {
                onNoPose()
                return
            }
            onPose(LivePose(
                landmarks = person.map { lm ->
                    floatArrayOf(lm.x(), lm.y(), lm.z(), lm.visibility().orElse(0f))
                },
                aspect = frameAspect,
                timestampMs = result.timestampMs(),
            ))
        } finally {
            busy.set(false)
        }
    }

    fun close() {
        landmarker?.close()
    }
}
