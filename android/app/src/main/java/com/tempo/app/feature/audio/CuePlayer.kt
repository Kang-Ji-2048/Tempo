package com.tempo.app.feature.audio

import android.content.Context
import android.media.AudioAttributes as AndroidAudioAttributes
import android.speech.tts.TextToSpeech
import android.util.Log
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

sealed interface CueEvent {
    data class Played(val audioUrl: String?, val cueText: String?, val timestampMs: Long) : CueEvent
    data class Suppressed(
        val reason: String,
        val elapsedMs: Long,
        val remainingCooldownMs: Long,
        val attemptedText: String?
    ) : CueEvent
}

/**
 * Singleton CuePlayer that plays short real-time audio cues for edge coaching.
 *
 * Rules:
 * - Minimum 15-second gap between cues (rate limiting). Any cue requested within 15s is suppressed.
 * - Routes audio to Bluetooth earbuds via AudioAttributes (USAGE_MEDIA, CONTENT_TYPE_SPEECH)
 *   with audio focus handling.
 * - Ready for live edge stream mode.
 */
@Singleton
class CuePlayer @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        const val TAG = "CuePlayer"
        const val MIN_CUE_INTERVAL_MS = 15_000L // 15 seconds gap between cues
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private var exoPlayer: ExoPlayer? = null
    private var textToSpeech: TextToSpeech? = null
    private var isTtsInitialized = false

    val rateLimiter = CueRateLimiter(MIN_CUE_INTERVAL_MS)

    private val _cueEvents = MutableSharedFlow<CueEvent>(replay = 1)
    val cueEvents: SharedFlow<CueEvent> = _cueEvents.asSharedFlow()

    init {
        initializeAudioEngines()
    }

    private fun initializeAudioEngines() {
        try {
            // Configure Media3 ExoPlayer with AudioAttributes for speech routing to Bluetooth earbuds
            val audioAttributes = AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH)
                .build()

            exoPlayer = ExoPlayer.Builder(context).build().apply {
                setAudioAttributes(audioAttributes, /* handleAudioFocus = */ true)
                addListener(object : Player.Listener {
                    override fun onPlaybackStateChanged(playbackState: Int) {
                        if (playbackState == Player.STATE_ENDED) {
                            Log.d(TAG, "Cue clip playback ended")
                        }
                    }
                })
            }

            // Fallback TextToSpeech engine configured with SPEECH audio attributes
            textToSpeech = TextToSpeech(context) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    val result = textToSpeech?.setLanguage(Locale.US)
                    if (result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED) {
                        val ttsAudioAttributes = AndroidAudioAttributes.Builder()
                            .setUsage(AndroidAudioAttributes.USAGE_MEDIA)
                            .setContentType(AndroidAudioAttributes.CONTENT_TYPE_SPEECH)
                            .build()
                        textToSpeech?.setAudioAttributes(ttsAudioAttributes)
                        isTtsInitialized = true
                        Log.d(TAG, "CuePlayer TTS initialized with speech audio attributes")
                    }
                }
            }
        } catch (t: Throwable) {
            Log.e(TAG, "Error initializing CuePlayer audio engines: ${t.message}", t)
        }
    }

    /**
     * Plays a short coaching cue.
     *
     * @param audioUrl Optional remote or local URL for the cue audio clip.
     * @param cueText Optional fallback text synthesized via TextToSpeech if no audioUrl.
     * @return true if the cue was played; false if suppressed due to the 15s rate-limit.
     */
    fun playCue(
        audioUrl: String? = null,
        cueText: String? = null,
        currentTimeMs: Long = System.currentTimeMillis()
    ): Boolean {
        return when (val result = rateLimiter.attemptPlay(currentTimeMs)) {
            is CueRateLimitResult.Suppressed -> {
                Log.w(
                    TAG,
                    "Cue SUPPRESSED! Only ${result.elapsedMs}ms elapsed since last cue. Cooldown remaining: ${result.remainingCooldownMs}ms"
                )
                scope.launch {
                    _cueEvents.emit(
                        CueEvent.Suppressed(
                            reason = "Minimum 15s interval not elapsed",
                            elapsedMs = result.elapsedMs,
                            remainingCooldownMs = result.remainingCooldownMs,
                            attemptedText = cueText ?: audioUrl
                        )
                    )
                }
                false
            }
            is CueRateLimitResult.Allowed -> {
                Log.i(TAG, "Playing cue: text='$cueText', url='$audioUrl'")

                if (!audioUrl.isNullOrBlank()) {
                    playAudioUrl(audioUrl)
                } else if (!cueText.isNullOrBlank()) {
                    speakText(cueText)
                }

                scope.launch {
                    _cueEvents.emit(
                        CueEvent.Played(
                            audioUrl = audioUrl,
                            cueText = cueText,
                            timestampMs = currentTimeMs
                        )
                    )
                }
                true
            }
        }
    }

    private fun playAudioUrl(url: String) {
        exoPlayer?.let { player ->
            try {
                player.stop()
                player.clearMediaItems()
                player.setMediaItem(MediaItem.fromUri(url))
                player.prepare()
                player.play()
            } catch (e: Exception) {
                Log.e(TAG, "Failed playing cue audio url: ${e.message}", e)
            }
        }
    }

    private fun speakText(text: String) {
        if (isTtsInitialized && textToSpeech != null) {
            textToSpeech?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "cue_${System.currentTimeMillis()}")
        } else {
            Log.w(TAG, "TTS not ready for cue text: $text")
        }
    }

    /** Returns true if a cue can be played immediately without being suppressed. */
    fun canPlayCue(currentTimeMs: Long = System.currentTimeMillis()): Boolean {
        return rateLimiter.canPlay(currentTimeMs)
    }

    /** Returns the cooldown remaining in milliseconds until the next cue can play. */
    fun getCooldownRemainingMs(currentTimeMs: Long = System.currentTimeMillis()): Long {
        return rateLimiter.getCooldownRemainingMs(currentTimeMs)
    }

    /** Resets the 15-second debounce window (useful for unit tests or starting new practice sets). */
    fun resetDebounce() {
        rateLimiter.reset()
    }

    fun stop() {
        exoPlayer?.stop()
        textToSpeech?.stop()
    }

    fun release() {
        stop()
        exoPlayer?.release()
        exoPlayer = null
        textToSpeech?.shutdown()
        textToSpeech = null
        isTtsInitialized = false
    }
}
