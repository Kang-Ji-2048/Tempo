package com.tempo.app.feature.audio

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import com.tempo.app.BuildConfig
import com.tempo.app.data.PlayerIdentity
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Coach voice for live drills: streams ElevenLabs speech from the backend's `GET /api/v1/tts`
 * (the ElevenLabs key never leaves the server). When the backend has no key, the request fails,
 * or there is no token, [speak] hands the text to `onFallback` so the caller uses on-device TTS.
 */
@Singleton
class CoachVoice @Inject constructor(
    @ApplicationContext private val context: Context,
    private val identity: PlayerIdentity,
) {
    private var onDone: (() -> Unit)? = null
    private var onFallback: ((String) -> Unit)? = null
    private var pendingText: String? = null

    private val player: ExoPlayer by lazy {
        // Start after ~250 ms of audio instead of ExoPlayer's 2.5 s default, so cues feel live.
        val loadControl = DefaultLoadControl.Builder()
            .setBufferDurationsMs(1_000, 30_000, 250, 500)
            .build()
        ExoPlayer.Builder(context).setLoadControl(loadControl).build().apply {
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(C.USAGE_MEDIA)
                    .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH)
                    .build(),
                /* handleAudioFocus = */ true
            )
            addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(playbackState: Int) {
                    if (playbackState == Player.STATE_ENDED) finish()?.let { it.first?.invoke() }
                }

                override fun onPlayerError(error: PlaybackException) {
                    Log.w(TAG, "ElevenLabs voice unavailable, using on-device TTS: ${error.errorCodeName}")
                    val (_, fallback, text) = finish() ?: return
                    if (text != null) fallback?.invoke(text)
                }
            })
        }
    }

    /** Speak [text]; a newer call replaces the current line without firing its callbacks. */
    fun speak(text: String, onDone: () -> Unit = {}, onFallback: (String) -> Unit) {
        val token = identity.accessToken
        if (token.isBlank()) {
            onFallback(text)
            return
        }
        this.onDone = onDone
        this.onFallback = onFallback
        pendingText = text
        val uri = Uri.parse(BuildConfig.BASE_URL + "api/v1/tts").buildUpon()
            .appendQueryParameter("text", text)
            .build()
        val http = DefaultHttpDataSource.Factory()
            .setConnectTimeoutMs(3_000)
            .setReadTimeoutMs(8_000)
            .setDefaultRequestProperties(mapOf("Authorization" to "Bearer $token"))
        player.apply {
            stop()
            setMediaSource(ProgressiveMediaSource.Factory(http).createMediaSource(MediaItem.fromUri(uri)))
            prepare()
            play()
        }
    }

    fun stop() {
        finish()
        player.stop()
    }

    fun release() {
        stop()
        player.release()
    }

    /** Clears the current line's callbacks and returns them, or null if nothing was playing. */
    private fun finish(): Triple<(() -> Unit)?, ((String) -> Unit)?, String?>? {
        val text = pendingText ?: return null
        val result = Triple(onDone, onFallback, text)
        onDone = null
        onFallback = null
        pendingText = null
        return result
    }

    companion object {
        private const val TAG = "CoachVoice"
    }
}
