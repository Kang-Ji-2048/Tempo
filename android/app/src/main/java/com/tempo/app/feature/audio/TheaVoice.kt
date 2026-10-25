package com.tempo.app.feature.audio

import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import android.util.Log
import java.util.Locale

private const val TAG = "TheaVoice"

/**
 * Thea's on-device voice: the best installed British English neural voice (Google's `en-gb-x-*`
 * voices), never one that needs the network, with navigation-guidance attributes so cues duck
 * music and route to earbuds. Shared by the voice conversation and live cue players.
 */
fun TextToSpeech.applyTheaVoice() {
    val installed = voices.orEmpty().filter { voice ->
        TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in voice.features.orEmpty()
    }
    val ukVoice = installed.firstOrNull { voice ->
        voice.locale == Locale.UK &&
            !voice.isNetworkConnectionRequired &&
            (voice.quality >= Voice.QUALITY_VERY_HIGH || voice.name.contains("en-gb-x", ignoreCase = true))
    } ?: installed.firstOrNull { it.locale == Locale.UK && !it.isNetworkConnectionRequired }
        ?: installed.firstOrNull { it.locale == Locale.UK }
    language = Locale.UK
    ukVoice?.let { voice = it }
    setPitch(1.02f)
    setSpeechRate(1.03f)
    setAudioAttributes(
        AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
    )
    Log.i(
        TAG,
        "voice=${voice?.name} locale=${voice?.locale} quality=${voice?.quality} " +
            "network=${voice?.isNetworkConnectionRequired} candidates=${installed.count { it.locale == Locale.UK }}"
    )
}

/**
 * Google TTS can report an empty voice list while its engine is still warming up, leaving the
 * generic `en-GB-language` voice. Re-pick before speaking until a neural en-GB voice sticks.
 */
fun TextToSpeech.ensureTheaVoice() {
    if (voice?.name?.contains("en-gb-x", ignoreCase = true) != true) applyTheaVoice()
}
