package com.tempo.app.feature.live

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.net.Uri
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.lifecycle.SavedStateHandle
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
import com.tempo.app.feature.audio.CuePlayer
import com.tempo.app.feature.voice.VoiceConversationManager
import com.tempo.app.feature.voice.VoiceState
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import javax.inject.Inject

enum class LiveConnection { DISCONNECTED, CONNECTING, LIVE, ERROR }

/** Rep phases from the server's RepTracker, shown as READY -> LOAD -> IMPACT -> RECOVER. */
enum class RepPhase(val label: String) {
    READY("READY"), PREPARATION("LOAD"), LOADING("LOAD"), IMPACT("IMPACT"), FOLLOW_THROUGH("RECOVER");

    companion object {
        fun of(raw: String?) = entries.firstOrNull { it.name == raw } ?: READY
    }
}

data class LastRepUi(
    val index: Int,
    val counted: Boolean,
    val quality: Int,
    val stroke: String,
    val proMatch: String?,
    val deviation: String?,
)

data class SetSummaryUi(val sessionId: String, val passed: Boolean, val summary: String, val unlockedNext: String?)

data class LiveUiState(
    val connection: LiveConnection = LiveConnection.DISCONNECTED,
    val statusMessage: String? = null,
    val sport: String? = null,
    val activeLesson: String? = null,
    val lessonIndex: Int? = null,
    val drillTitle: String? = null,
    val targetStroke: String? = null,
    val sequence: List<String> = emptyList(),
    val targetReps: Int = 10,
    val validReps: Int = 0,
    val totalReps: Int = 0,
    val thresholdDeg: Double? = null,
    val handedness: String? = null,
    val phase: RepPhase = RepPhase.READY,
    val elbowDeg: Double? = null,
    val kneeDeg: Double? = null,
    val heartRate: Int? = null,
    val sentFps: Int = 0,
    val subtitle: String = "Stand side-on, full body in frame. Thea is watching.",
    val lastRep: LastRepUi? = null,
    val driftMessage: String? = null,
    val isSaving: Boolean = false,
    val summary: SetSummaryUi? = null,
) {
    val isStreaming: Boolean get() = connection == LiveConnection.LIVE
}

/** One detected pose: 33 x [x, y, z, visibility] in normalized, upright image coordinates. */
data class LivePose(val landmarks: List<FloatArray>, val aspect: Float, val timestampMs: Long)

sealed interface LiveEvent {
    data class OpenSession(val sessionId: String) : LiveEvent
}

/**
 * Live coaching studio. Streams on-device MediaPipe pose (~14 Hz) to `/api/v1/live/stream` (v2), where
 * the server's RepTracker segments reps, grades them against the bound drill and fulfills the lesson.
 * Rep cues go through [CuePlayer] (10 s limit); Thea's voice replies and the set summary are spoken
 * immediately via [VoiceConversationManager].
 */
@HiltViewModel
class LiveViewModel @Inject constructor(
    private val cuePlayer: CuePlayer,
    private val voice: VoiceConversationManager,
    private val identity: PlayerIdentity,
    okHttpClient: OkHttpClient,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val boundNodeId: String? = savedStateHandle.get<String>("node_id")
    private val boundDrillId: String? = savedStateHandle.get<String>("drill_id")

    private val _uiState = MutableStateFlow(LiveUiState())
    val uiState: StateFlow<LiveUiState> = _uiState.asStateFlow()

    private val _pose = MutableStateFlow<LivePose?>(null)
    /** Latest skeleton for the overlay; updated every analyzed frame, independent of streaming. */
    val pose: StateFlow<LivePose?> = _pose.asStateFlow()

    private val _events = MutableSharedFlow<LiveEvent>(extraBufferCapacity = 2)
    val events: SharedFlow<LiveEvent> = _events.asSharedFlow()

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
    private var pendingQuestion: String? = null

    fun startLive() {
        if (socket != null) return
        val base = BuildConfig.BASE_URL.trimEnd('/').replaceFirst("http", "ws")
        val url = "$base/api/v1/live/stream?user_id=${Uri.encode(identity.userId)}"
        _uiState.update { it.copy(connection = LiveConnection.CONNECTING, statusMessage = "Connecting to Thea…", summary = null) }
        socket = wsClient.newWebSocket(Request.Builder().url(url).build(), listener)
    }

    fun stopLive() {
        socket?.close(1000, "left live mode")
        socket = null
        cuePlayer.stop()
        _uiState.update { it.copy(connection = LiveConnection.DISCONNECTED, statusMessage = null, sentFps = 0) }
    }

    /** "Finish & Save Set": the server persists the set, progresses the curriculum and replies drill_fulfilled. */
    fun finishSet() {
        val ws = socket ?: return
        _uiState.update { it.copy(isSaving = true, subtitle = "Saving your set…") }
        ws.send("""{"type":"complete_session"}""")
    }

    /** Talk to Thea mid-set: the transcript goes over the live socket so her tools can change the drill. */
    fun askThea(transcript: String) {
        val ws = socket
        if (ws == null) {
            voice.ask(transcript, channel = "live")
            return
        }
        pendingQuestion = transcript
        ws.send(buildJsonObject { put("type", "voice_query"); put("text", transcript) }.toString())
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
        append("""{"type":"keypoints","timestamp_ms":""").append(pose.timestampMs)
        append(""","aspect":""").append(pose.aspect).append(""","landmarks":[""")
        pose.landmarks.forEachIndexed { i, lm ->
            if (i > 0) append(',')
            append('[').append(lm[0]).append(',').append(lm[1]).append(',').append(lm[2]).append(',').append(lm[3]).append(']')
        }
        append("]}")
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            if (boundNodeId != null || boundDrillId != null) {
                webSocket.send(buildJsonObject {
                    put("type", "start_drill"); boundNodeId?.let { put("node_id", it) }; boundDrillId?.let { put("drill_id", it) }
                }.toString())
            } else {
                webSocket.send("""{"type":"hello"}""")
            }
            _uiState.update { it.copy(connection = LiveConnection.LIVE, statusMessage = null) }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val msg = runCatching { json.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
            viewModelScope.launch { handle(msg) }
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, null)
            socket = null
            _uiState.update {
                it.copy(connection = LiveConnection.DISCONNECTED, sentFps = 0, statusMessage = when (code) {
                    4401 -> "Sign in again to use live mode."
                    4403 -> "This live session belongs to another player."
                    else -> null
                })
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.w(TAG, "Live stream failed", t)
            if (socket === webSocket) socket = null
            _uiState.update {
                it.copy(connection = LiveConnection.ERROR, sentFps = 0, isSaving = false,
                    // A rejected handshake (closed before accept) surfaces here as HTTP 401/403.
                    statusMessage = when (response?.code) {
                        401 -> "Sign in again to use live mode."
                        403 -> "This live session belongs to another player."
                        else -> "Lost connection to Thea. Check adb reverse / Wi-Fi and tap Reconnect."
                    })
            }
        }
    }

    private fun handle(msg: JsonObject) {
        fun text(key: String) = (msg[key] as? JsonPrimitive)?.contentOrNull
        fun number(key: String) = (msg[key] as? JsonPrimitive)?.doubleOrNull
        fun int(key: String) = (msg[key] as? JsonPrimitive)?.intOrNull
        when (text("type")) {
            "session" -> _uiState.update {
                it.copy(sport = text("sport"), activeLesson = text("active_lesson"),
                    drillTitle = text("drill_title") ?: text("active_lesson"), targetStroke = text("target_stroke"),
                    sequence = (msg["sequence"] as? JsonArray)?.mapNotNull { e -> (e as? JsonPrimitive)?.contentOrNull }.orEmpty(),
                    targetReps = int("target_reps") ?: it.targetReps, validReps = int("valid_reps") ?: it.validReps,
                    totalReps = int("reps") ?: it.totalReps, thresholdDeg = number("threshold_deg"),
                    handedness = text("handedness") ?: it.handedness)
            }
            "phase_update" -> {
                val angles = msg["live_angles"] as? JsonObject
                _uiState.update {
                    it.copy(phase = RepPhase.of(text("phase")),
                        elbowDeg = (angles?.get("elbow_deg") as? JsonPrimitive)?.doubleOrNull ?: it.elbowDeg,
                        kneeDeg = (angles?.get("knee_deg") as? JsonPrimitive)?.doubleOrNull ?: it.kneeDeg)
                }
            }
            "metrics" -> _uiState.update {
                it.copy(elbowDeg = number("elbow_deg"), kneeDeg = number("knee_deg"),
                    phase = RepPhase.of(text("phase")), validReps = int("valid_reps") ?: it.validReps,
                    totalReps = int("reps") ?: it.totalReps)
            }
            "rep_completed" -> {
                val cue = text("cue_text").orEmpty()
                val drift = (msg["drift"] as? JsonObject)?.let { (it["message"] as? JsonPrimitive)?.contentOrNull }
                _uiState.update {
                    it.copy(validReps = int("valid_reps") ?: it.validReps, totalReps = int("rep_index") ?: it.totalReps,
                        targetReps = int("target_reps") ?: it.targetReps, subtitle = cue,
                        driftMessage = drift ?: it.driftMessage, phase = RepPhase.READY,
                        lastRep = LastRepUi(int("rep_index") ?: 0,
                            (msg["rep_counted"] as? JsonPrimitive)?.booleanOrNull ?: false, int("quality_score") ?: 0,
                            text("detected_stroke").orEmpty(), text("pro_match"), text("primary_deviation")))
                }
                val shouldSpeak = (msg["should_speak"] as? JsonPrimitive)?.booleanOrNull ?: true
                if (shouldSpeak && !voice.isBusy) cuePlayer.playCue(cueText = drift ?: cue)
            }
            "voice_reply" -> {
                val reply = text("reply_text").orEmpty()
                _uiState.update { it.copy(subtitle = reply) }
                voice.deliverReply("live", pendingQuestion.orEmpty(), reply, text("speak_text"),
                    (msg["tool_actions_taken"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty(),
                    msg["updated_memory"] as? JsonObject)
                pendingQuestion = null
            }
            "drill_fulfilled" -> {
                val sessionId = text("session_id") ?: return
                val summary = text("summary_speak").orEmpty()
                _uiState.update {
                    it.copy(isSaving = false, subtitle = summary, validReps = int("valid_reps") ?: it.validReps,
                        summary = SetSummaryUi(sessionId, (msg["passed"] as? JsonPrimitive)?.booleanOrNull ?: false,
                            summary, text("unlocked_next_node")))
                }
                cuePlayer.stop()
                voice.announce(summary)
            }
            "cue" -> {
                val cue = text("cue") ?: return
                _uiState.update { it.copy(subtitle = cue) }
                if (!voice.isBusy) cuePlayer.playCue(cueText = cue)
            }
            else -> text("error")?.let { error -> Log.w(TAG, "Live server: $error") }
        }
    }

    fun openSummary() {
        val id = _uiState.value.summary?.sessionId ?: return
        viewModelScope.launch { _events.emit(LiveEvent.OpenSession(id)) }
    }

    fun isVoiceBusy(): Boolean = voice.isBusy || voice.state.value is VoiceState.Thinking

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
