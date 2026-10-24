package com.tempo.app.feature.audio.ui

import android.content.Context
import android.media.AudioAttributes as AndroidAudioAttributes
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Headphones
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.RecordVoiceOver
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.VolumeUp
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import kotlinx.coroutines.delay
import java.util.Locale
import kotlin.math.sin

/**
 * DebriefPlayer
 *
 * Plays 30-45s coach voice debrief using Media3 ExoPlayer loaded from [voiceNoteUrl],
 * falling back to Android TextToSpeech reading [voiceNoteScript] if no URL is provided
 * or if network playback fails.
 *
 * Configures AudioAttributes with (USAGE_MEDIA, CONTENT_TYPE_SPEECH) and audio focus handling,
 * which routes audio to Bluetooth earbuds by default on Android 12+ (Pixel 10 Pro).
 *
 * Features:
 * - Play/Pause tactile toggle button with accent glow
 * - Time position readout (e.g. 0:14 / 0:38)
 * - 36-bar dynamic waveform with interactive tap-to-seek and live animation
 * - Auto-offered indicator banner when analysis finishes
 * - Bluetooth earbud routing badge
 */
@Composable
fun DebriefPlayer(
    voiceNoteUrl: String?,
    voiceNoteScript: String?,
    modifier: Modifier = Modifier,
    autoOffer: Boolean = true
) {
    val context = LocalContext.current

    var isPlaying by remember { mutableStateOf(false) }
    var currentPositionMs by remember { mutableLongStateOf(0L) }
    var totalDurationMs by remember { mutableLongStateOf(38_000L) } // default 38s voice note
    var isUsingTts by remember { mutableStateOf(voiceNoteUrl.isNullOrBlank()) }
    var ttsEngine by remember { mutableStateOf<TextToSpeech?>(null) }
    var isTtsReady by remember { mutableStateOf(false) }
    var exoPlayer by remember { mutableStateOf<ExoPlayer?>(null) }
    var showAutoOfferBanner by remember { mutableStateOf(autoOffer) }

    // Waveform envelope representation (36 bars with realistic vocal speech profile)
    val baseWaveformAmplitudes = remember {
        floatArrayOf(
            0.22f, 0.35f, 0.48f, 0.72f, 0.88f, 0.65f, 0.94f, 0.82f,
            0.55f, 0.78f, 0.90f, 0.68f, 0.85f, 0.98f, 0.76f, 0.58f,
            0.82f, 0.92f, 0.71f, 0.89f, 0.95f, 0.60f, 0.74f, 0.88f,
            0.70f, 0.54f, 0.86f, 0.92f, 0.64f, 0.77f, 0.62f, 0.48f,
            0.40f, 0.32f, 0.24f, 0.18f
        )
    }

    // Dynamic wave animation for active playback
    val infiniteTransition = rememberInfiniteTransition(label = "WaveformPulse")
    val wavePhase by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 6.28318f,
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "WavePhase"
    )

    // Initialize audio engines
    DisposableEffect(voiceNoteUrl, voiceNoteScript) {
        var player: ExoPlayer? = null
        var tts: TextToSpeech? = null

        // Media3 ExoPlayer AudioAttributes for speech & earbud routing
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(C.USAGE_MEDIA)
            .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH)
            .build()

        if (!voiceNoteUrl.isNullOrBlank()) {
            try {
                player = ExoPlayer.Builder(context).build().apply {
                    setAudioAttributes(audioAttributes, /* handleAudioFocus = */ true)
                    setMediaItem(MediaItem.fromUri(voiceNoteUrl))
                    prepare()
                    addListener(object : Player.Listener {
                        override fun onPlaybackStateChanged(playbackState: Int) {
                            if (playbackState == Player.STATE_READY) {
                                if (duration > 0) totalDurationMs = duration
                            } else if (playbackState == Player.STATE_ENDED) {
                                isPlaying = false
                                currentPositionMs = totalDurationMs
                            }
                        }

                        override fun onIsPlayingChanged(playing: Boolean) {
                            isPlaying = playing
                        }

                        override fun onPlayerError(error: PlaybackException) {
                            Log.w("DebriefPlayer", "ExoPlayer failed ($error). Falling back to TTS.")
                            isUsingTts = true
                        }
                    })
                }
                exoPlayer = player
                isUsingTts = false
            } catch (e: Exception) {
                Log.e("DebriefPlayer", "Error creating ExoPlayer: ${e.message}", e)
                isUsingTts = true
            }
        } else {
            isUsingTts = true
        }

        // Initialize Android TextToSpeech as speech fallback
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.US)
                if (result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED) {
                    val ttsAttributes = AndroidAudioAttributes.Builder()
                        .setUsage(AndroidAudioAttributes.USAGE_MEDIA)
                        .setContentType(AndroidAudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                    tts?.setAudioAttributes(ttsAttributes)
                    isTtsReady = true
                }
            }
        }
        ttsEngine = tts

        onDispose {
            player?.stop()
            player?.release()
            exoPlayer = null
            tts?.stop()
            tts?.shutdown()
            ttsEngine = null
        }
    }

    // TTS Utterance progress handler to update progress and position
    LaunchedEffect(ttsEngine, isTtsReady) {
        ttsEngine?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {
                isPlaying = true
            }

            override fun onDone(utteranceId: String?) {
                isPlaying = false
                currentPositionMs = totalDurationMs
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                isPlaying = false
            }
        })
    }

    // Periodic position updater during playback
    LaunchedEffect(isPlaying, isUsingTts) {
        if (!isUsingTts) {
            while (isPlaying) {
                exoPlayer?.let { player ->
                    currentPositionMs = player.currentPosition
                    if (player.duration > 0) totalDurationMs = player.duration
                }
                delay(100)
            }
        } else if (isPlaying) {
            // Estimate progress for TTS reading
            val scriptWords = voiceNoteScript?.split("\\s+".toRegex())?.size ?: 60
            val estimatedDurationMs = (scriptWords * 350L).coerceIn(20_000L, 45_000L)
            totalDurationMs = estimatedDurationMs

            val start = System.currentTimeMillis() - currentPositionMs
            while (isPlaying && currentPositionMs < totalDurationMs) {
                currentPositionMs = (System.currentTimeMillis() - start).coerceAtMost(totalDurationMs)
                delay(100)
            }
            if (currentPositionMs >= totalDurationMs) {
                isPlaying = false
            }
        }
    }

    fun togglePlayPause() {
        showAutoOfferBanner = false
        if (isPlaying) {
            if (!isUsingTts && exoPlayer != null) {
                exoPlayer?.pause()
            } else {
                ttsEngine?.stop()
                isPlaying = false
            }
        } else {
            if (!isUsingTts && exoPlayer != null) {
                if (currentPositionMs >= totalDurationMs && totalDurationMs > 0) {
                    exoPlayer?.seekTo(0)
                    currentPositionMs = 0
                }
                exoPlayer?.play()
            } else {
                val textToSpeak = voiceNoteScript
                    ?: "Great practice session. Your contact height was explosive, but keep your elbow high at contact to increase smash angle."
                if (currentPositionMs >= totalDurationMs) {
                    currentPositionMs = 0
                }
                ttsEngine?.speak(
                    textToSpeak,
                    TextToSpeech.QUEUE_FLUSH,
                    null,
                    "debrief_utterance_${System.currentTimeMillis()}"
                )
                isPlaying = true
            }
        }
    }

    fun seekToFraction(fraction: Float) {
        val targetMs = (fraction * totalDurationMs).toLong()
        currentPositionMs = targetMs
        if (!isUsingTts && exoPlayer != null) {
            exoPlayer?.seekTo(targetMs)
        }
    }

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, if (isPlaying) AccentNeonVolt.copy(alpha = 0.6f) else CardBorderSubtle)
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Header: Auto-Offer badge and Earbud Routing indicator
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(36.dp)
                            .clip(CircleShape)
                            .background(AccentNeonVolt.copy(alpha = 0.16f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.RecordVoiceOver,
                            contentDescription = null,
                            tint = AccentNeonVolt,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(
                            text = "COACH VOICE DEBRIEF",
                            style = MaterialTheme.typography.labelSmall.copy(
                                letterSpacing = 1.2.sp,
                                fontWeight = FontWeight.Bold
                            ),
                            color = AccentNeonVolt
                        )
                        Text(
                            text = if (isUsingTts) "AI Coach Audio Synthesis" else "Studio Voice Breakdown",
                            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                            color = TextPrimaryWhite
                        )
                    }
                }

                // Bluetooth Earbuds Route Chip
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = SurfaceVariantDark,
                    border = BorderStroke(1.dp, CardBorderSubtle)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.Headphones,
                            contentDescription = "Bluetooth Earbuds",
                            tint = AccentNeonVolt,
                            modifier = Modifier.size(14.dp)
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(
                            text = "Earbuds",
                            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold),
                            color = TextSecondarySilver
                        )
                    }
                }
            }

            // Auto-Offer Banner (Prompts playback automatically when session analysis completes)
            AnimatedVisibility(
                visible = showAutoOfferBanner,
                enter = fadeIn(),
                exit = fadeOut()
            ) {
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = AccentNeonVolt.copy(alpha = 0.12f),
                    border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.4f)),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { togglePlayPause() }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.AutoAwesome,
                            contentDescription = null,
                            tint = AccentNeonVolt,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = "Auto-offered: Tap to listen to your 35s technique debrief",
                            style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold),
                            color = TextPrimaryWhite,
                            modifier = Modifier.weight(1f)
                        )
                        Text(
                            text = "PLAY",
                            style = MaterialTheme.typography.labelSmall.copy(
                                fontWeight = FontWeight.Black,
                                letterSpacing = 1.sp
                            ),
                            color = AccentNeonVolt
                        )
                    }
                }
            }

            // Coach Voice Script Preview Quote
            if (!voiceNoteScript.isNullOrBlank()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(BackgroundOnyx.copy(alpha = 0.6f))
                        .padding(12.dp)
                ) {
                    Text(
                        text = "\"$voiceNoteScript\"",
                        style = MaterialTheme.typography.bodySmall.copy(lineHeight = 18.sp),
                        color = TextSecondarySilver,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }

            // Waveform Amplitude Bar Scrubber
            val progressFraction = if (totalDurationMs > 0) {
                (currentPositionMs.toFloat() / totalDurationMs.toFloat()).coerceIn(0f, 1f)
            } else 0f

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(54.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(BackgroundOnyx)
                    .padding(horizontal = 8.dp, vertical = 6.dp)
                    .pointerInput(totalDurationMs) {
                        detectTapGestures { offset ->
                            val fraction = (offset.x / size.width).coerceIn(0f, 1f)
                            seekToFraction(fraction)
                        }
                    },
                contentAlignment = Alignment.Center
            ) {
                Row(
                    modifier = Modifier.fillMaxSize(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val barCount = baseWaveformAmplitudes.size
                    baseWaveformAmplitudes.forEachIndexed { index, baseAmp ->
                        val barFraction = index.toFloat() / barCount.toFloat()
                        val isPlayed = barFraction <= progressFraction

                        // Subtle animated breathing effect when playing
                        val pulseMultiplier = if (isPlaying) {
                            1f + 0.18f * sin(wavePhase + index * 0.35f).toFloat()
                        } else {
                            1f
                        }
                        val heightFraction = (baseAmp * pulseMultiplier).coerceIn(0.15f, 1f)

                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .fillMaxHeight(heightFraction)
                                .padding(horizontal = 1.5.dp)
                                .clip(RoundedCornerShape(2.dp))
                                .background(
                                    if (isPlayed) {
                                        AccentNeonVolt
                                    } else {
                                        SurfaceVariantDark
                                    }
                                )
                        )
                    }
                }
            }

            // Controls & Timing Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                // Play / Pause Circular Button
                Box(
                    modifier = Modifier
                        .size(54.dp)
                        .clip(CircleShape)
                        .background(AccentNeonVolt)
                        .clickable { togglePlayPause() },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = if (isPlaying) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                        contentDescription = if (isPlaying) "Pause Coach Debrief" else "Play Coach Debrief",
                        tint = BackgroundOnyx,
                        modifier = Modifier.size(30.dp)
                    )
                }

                // Time Position & Audio Spec
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "${formatTime(currentPositionMs)} / ${formatTime(totalDurationMs)}",
                        style = MaterialTheme.typography.titleMedium.copy(
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.5.sp
                        ),
                        color = TextPrimaryWhite
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        text = if (isUsingTts) "SPEECH • SYNTHESIZED" else "SPEECH • 48kHz AAC",
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold),
                        color = TextMuted
                    )
                }
            }
        }
    }
}

private fun formatTime(ms: Long): String {
    val totalSeconds = (ms / 1000).coerceAtLeast(0)
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    return String.format(Locale.US, "%d:%02d", minutes, seconds)
}
