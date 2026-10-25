package com.tempo.app.feature.voice

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
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
import androidx.compose.foundation.clickable
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
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

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
 * -> TextToSpeech of `speak_text` (USAGE_MEDIA / CONTENT_TYPE_SPEECH, so it routes to earbuds).
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
                language = Locale.US
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
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
    fun toggle(channel: String) {
        if (isBusy) cancel() else startListening(channel)
    }

    fun startListening(channel: String) {
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
                        CoachConverseRequestDto(userId = identity.userId.ifBlank { null }, message = transcript, channel = channel)
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
                _state.value = VoiceState.Error("Couldn't reach Thea. Check the connection and try again.")
            }
        }
    }

    private fun speak(text: String) {
        if (ttsReady) {
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, Bundle(), "thea_${System.currentTimeMillis()}")
        } else {
            settle()
        }
    }

    private fun settle() {
        scope.launch { if (_state.value is VoiceState.Speaking) _state.value = VoiceState.Idle }
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
            if (text.isBlank()) _state.value = VoiceState.Error("I didn't catch that. Tap the mic and try again.")
            else ask(text, activeChannel)
        }

        override fun onError(error: Int) {
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
@Composable
fun VoiceMicButton(
    channel: String,
    modifier: Modifier = Modifier,
    size: Dp = 64.dp,
    showCaption: Boolean = true,
    onExchange: (VoiceExchange) -> Unit = {},
    viewModel: VoiceViewModel = hiltViewModel(),
) {
    val manager = viewModel.manager
    val state by manager.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val latestOnExchange by rememberUpdatedState(onExchange)
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) manager.startListening(channel)
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
                .clickable {
                    val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                        PackageManager.PERMISSION_GRANTED
                    if (granted || manager.isBusy) manager.toggle(channel)
                    else permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                },
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
                    VoiceState.Idle -> "Talk to Thea" to "Ask a question or say \"switch me to intermediate\"."
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
