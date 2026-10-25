package com.tempo.app.feature.voice

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.CoachConverseRequestDto
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import com.tempo.app.feature.audio.applyTheaVoice
import com.tempo.app.feature.audio.ensureTheaVoice
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

/** What to tell the athlete when a Thea turn fails; distinguishes slow, signed-out, server and network errors. */
fun theaErrorMessage(e: Throwable): String = when (e) {
    is java.net.SocketTimeoutException -> "Thea is taking longer than usual to answer. Try again in a moment."
    is retrofit2.HttpException -> when (e.code()) {
        401 -> "Your session expired. Sign in again to talk to Thea."
        403 -> "Thea can only open your own account. Sign in again."
        in 500..599 -> "Thea hit a problem on the server (HTTP ${e.code()}). Try again shortly."
        else -> "Thea couldn't take that request (HTTP ${e.code()})."
    }
    is kotlinx.serialization.SerializationException -> "Thea replied in a format this app version can't read. Update the app."
    is java.io.IOException -> "Couldn't reach Tempo. Check the connection (adb reverse tcp:8000 tcp:8000) and try again."
    else -> "Something went wrong talking to Thea (${e.javaClass.simpleName})."
}

sealed interface VoiceState {
    data object Idle : VoiceState
    data class Listening(val partial: String = "") : VoiceState
    data class Thinking(val transcript: String) : VoiceState
    data class Speaking(val transcript: String, val reply: String) : VoiceState
    data class Error(val message: String) : VoiceState
}

/** One completed voice turn; screens refresh from [athleteMemory] because Thea's tools may have changed it. */
data class VoiceExchange(
    val channel: String,
    val transcript: String,
    val replyText: String,
    val speakText: String,
    val toolActions: List<String>,
    val athleteMemory: JsonObject?,
    val widgets: List<JsonObject>,
)

/**
 * Two-way voice loop with Coach Thea: SpeechRecognizer (speech-to-text) -> `POST /api/v1/coach/converse`
 * -> TextToSpeech of `speak_text` (on-device en-GB neural voice, USAGE_ASSISTANCE_NAVIGATION_GUIDANCE).
 *
 * Answers are spoken immediately: they bypass CuePlayer's form-cue cooldown, and live mode holds
 * automatic cues while [isBusy] so Thea never talks over herself.
 */
@Singleton
class VoiceConversationManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val tempoApi: TempoApi,
    private val identity: PlayerIdentity,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var activeChannel = "app"
    private var conversationJob: Job? = null
    /** When set, transcripts go here (e.g. Live's WebSocket voice_query) instead of HTTP converse. */
    private var transcriptHandler: ((String) -> Unit)? = null

    private val _handsFree = MutableStateFlow(false)
    /** Hands-free: after Thea finishes speaking, listen again automatically (continuous turns). */
    val handsFree: StateFlow<Boolean> = _handsFree.asStateFlow()

    fun setHandsFree(enabled: Boolean) {
        _handsFree.value = enabled
    }

    private val _state = MutableStateFlow<VoiceState>(VoiceState.Idle)
    val state: StateFlow<VoiceState> = _state.asStateFlow()

    private val _exchanges = MutableSharedFlow<VoiceExchange>(extraBufferCapacity = 4)
    val exchanges: SharedFlow<VoiceExchange> = _exchanges.asSharedFlow()

    /** Listening, waiting on Thea, or speaking her answer. */
    val isBusy: Boolean get() = _state.value is VoiceState.Listening || _state.value is VoiceState.Thinking ||
        _state.value is VoiceState.Speaking

    val isRecognitionAvailable: Boolean get() = SpeechRecognizer.isRecognitionAvailable(context)

    init {
        tts = TextToSpeech(context) { status ->
            if (status != TextToSpeech.SUCCESS) return@TextToSpeech
            tts?.apply {
                applyTheaVoice()
                setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) = Unit
                    override fun onDone(utteranceId: String?) = settle()
                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) = settle()
                })
            }
            ttsReady = true
        }
    }

    /** Toggle: start listening, or stop and discard the current turn. */
    fun toggle(channel: String, onTranscript: ((String) -> Unit)? = null) {
        if (isBusy) cancel() else startListening(channel, onTranscript)
    }

    fun startListening(channel: String, onTranscript: ((String) -> Unit)? = null) {
        transcriptHandler = onTranscript
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            _state.value = VoiceState.Error("Microphone permission is needed to talk to Thea.")
            return
        }
        if (!isRecognitionAvailable) {
            _state.value = VoiceState.Error("Speech recognition isn't available on this device.")
            return
        }
        tts?.stop()
        activeChannel = channel
        val sr = recognizer ?: SpeechRecognizer.createSpeechRecognizer(context).also { recognizer = it }
        sr.setRecognitionListener(listener)
        _state.value = VoiceState.Listening()
        sr.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        })
    }

    fun cancel() {
        _handsFree.value = false
        recognizer?.cancel()
        conversationJob?.cancel()
        tts?.stop()
        _state.value = VoiceState.Idle
    }

    /** Send already-transcribed (or typed) text through the same converse -> speak loop. */
    fun ask(text: String, channel: String = activeChannel) {
        val transcript = text.trim()
        if (transcript.isEmpty()) return
        activeChannel = channel
        conversationJob?.cancel()
        conversationJob = scope.launch {
            _state.value = VoiceState.Thinking(transcript)
            try {
                val response = withContext(Dispatchers.IO) {
                    tempoApi.converseWithCoach(
                        // No user_id: the server answers for the signed-in token, so a stale local id can't 403.
                        CoachConverseRequestDto(message = transcript, channel = channel)
                    )
                }
                val spoken = response.speakText?.takeIf { it.isNotBlank() } ?: response.replyText
                _state.value = VoiceState.Speaking(transcript, response.replyText)
                speak(spoken)
                _exchanges.emit(
                    VoiceExchange(channel, transcript, response.replyText, spoken, response.toolActionsTaken,
                        response.athleteMemory, response.dynamicWidgets)
                )
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "Converse failed", e)
                _state.value = VoiceState.Error(theaErrorMessage(e))
            }
        }
    }

    /**
     * A reply that arrived over another transport (Live's WebSocket voice_reply): speak it right away,
     * bypassing the form-cue cooldown, and publish it like an HTTP turn.
     */
    fun deliverReply(channel: String, transcript: String, replyText: String, speakText: String?,
                     toolActions: List<String>, athleteMemory: JsonObject?) {
        val spoken = speakText?.takeIf { it.isNotBlank() } ?: replyText
        _state.value = VoiceState.Speaking(transcript, replyText)
        speak(spoken)
        scope.launch { _exchanges.emit(VoiceExchange(channel, transcript, replyText, spoken, toolActions, athleteMemory, emptyList())) }
    }

    /** Speak a coach line immediately (e.g. a set summary) without a listening turn. */
    fun announce(text: String) {
        if (text.isBlank()) return
        _state.value = VoiceState.Speaking("", text)
        speak(text)
    }

    private fun speak(text: String) {
        if (ttsReady) {
            tts?.ensureTheaVoice()
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, Bundle(), "thea_${System.currentTimeMillis()}")
        } else {
            settle()
        }
    }

    private fun settle() {
        scope.launch {
            if (_state.value !is VoiceState.Speaking) return@launch
            _state.value = VoiceState.Idle
            if (_handsFree.value) startListening(activeChannel, transcriptHandler)
        }
    }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) = Unit
        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit
        override fun onEndOfSpeech() = Unit
        override fun onEvent(eventType: Int, params: Bundle?) = Unit

        override fun onPartialResults(partialResults: Bundle?) {
            val partial = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
            if (_state.value is VoiceState.Listening) _state.value = VoiceState.Listening(partial)
        }

        override fun onResults(results: Bundle?) {
            val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
            val handler = transcriptHandler
            when {
                text.isBlank() -> _state.value = VoiceState.Error("I didn't catch that. Tap the mic and try again.")
                handler != null -> {
                    _state.value = VoiceState.Thinking(text)
                    handler(text)
                }
                else -> ask(text, activeChannel)
            }
        }

        override fun onError(error: Int) {
            _handsFree.value = false  // silence or a failure ends hands-free mode
            _state.value = VoiceState.Error(
                when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT ->
                        "I didn't catch that. Tap the mic and try again."
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission is needed to talk to Thea."
                    SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Speech service is offline."
                    else -> "Voice input stopped (code $error). Tap the mic to retry."
                }
            )
        }
    }

    companion object {
        private const val TAG = "VoiceConversation"
    }
}

@HiltViewModel
class VoiceViewModel @Inject constructor(val manager: VoiceConversationManager) : ViewModel() {
    override fun onCleared() {
        // The manager is app-wide; don't leave a turn running for a screen that's gone.
        if (manager.isBusy) manager.cancel()
    }
}

/**
 * Prominent mic for talking to Thea. Asks for RECORD_AUDIO on first tap, shows what was heard and
 * Thea's reply, and calls [onExchange] after each answer so the screen can refresh from memory.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun VoiceMicButton(
    channel: String,
    modifier: Modifier = Modifier,
    size: Dp = 64.dp,
    showCaption: Boolean = true,
    onExchange: (VoiceExchange) -> Unit = {},
    /** Route transcripts somewhere other than HTTP converse (Live sends them over its WebSocket). */
    onTranscript: ((String) -> Unit)? = null,
    viewModel: VoiceViewModel = hiltViewModel(),
) {
    val manager = viewModel.manager
    val state by manager.state.collectAsStateWithLifecycle()
    val handsFree by manager.handsFree.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val latestOnExchange by rememberUpdatedState(onExchange)
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) manager.startListening(channel, onTranscript)
    }

    LaunchedEffect(manager, channel) {
        manager.exchanges.collect { if (it.channel == channel) latestOnExchange(it) }
    }

    val pulse by rememberInfiniteTransition(label = "micPulse").animateFloat(
        initialValue = 1f, targetValue = 1.12f,
        animationSpec = infiniteRepeatable(tween(650), RepeatMode.Reverse), label = "micScale",
    )
    val listening = state is VoiceState.Listening

    Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(size)
                .scale(if (listening) pulse else 1f)
                .clip(CircleShape)
                .background(if (listening) ErrorRed else AccentNeonVolt)
                .combinedClickable(
                    onClick = {
                        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                            PackageManager.PERMISSION_GRANTED
                        if (granted || manager.isBusy) manager.toggle(channel, onTranscript)
                        else permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    },
                    onLongClick = {
                        // Long-press: hands-free conversation (keeps listening after each answer).
                        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                            PackageManager.PERMISSION_GRANTED
                        if (!granted) {
                            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        } else if (handsFree) {
                            manager.cancel()
                        } else {
                            manager.setHandsFree(true)
                            if (!manager.isBusy) manager.startListening(channel, onTranscript)
                        }
                    },
                ),
            contentAlignment = Alignment.Center,
        ) {
            when (state) {
                is VoiceState.Thinking -> CircularProgressIndicator(
                    color = BackgroundOnyx, strokeWidth = 3.dp, modifier = Modifier.size(size * 0.45f),
                )
                else -> Icon(
                    imageVector = when (state) {
                        is VoiceState.Listening -> Icons.Rounded.Stop
                        is VoiceState.Speaking -> Icons.Rounded.GraphicEq
                        else -> Icons.Rounded.Mic
                    },
                    contentDescription = if (listening) "Stop listening" else "Talk to Coach Thea",
                    tint = BackgroundOnyx,
                    modifier = Modifier.size(size * 0.5f),
                )
            }
        }
        if (showCaption) {
            Spacer(Modifier.width(14.dp))
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                val (headline, detail) = when (val s = state) {
                    VoiceState.Idle -> (if (handsFree) "Hands-free on" else "Talk to Thea") to
                        "Tap to ask, long-press for hands-free. Try \"switch me to intermediate\"."
                    is VoiceState.Listening -> "Listening…" to s.partial.ifBlank { "Go ahead, I'm listening." }
                    is VoiceState.Thinking -> "You said" to "\"${s.transcript}\""
                    is VoiceState.Speaking -> "Thea" to s.reply
                    is VoiceState.Error -> "Voice" to s.message
                }
                Text(
                    headline.uppercase(),
                    style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                    color = if (state is VoiceState.Error) ErrorRed else AccentNeonVolt,
                )
                Text(
                    detail,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (state is VoiceState.Speaking) TextPrimaryWhite else TextSecondarySilver,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
