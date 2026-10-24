package com.tempo.app.feature.live

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.feature.audio.CueEvent
import com.tempo.app.feature.audio.CuePlayer
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LiveUiState(
    val isStreaming: Boolean = false,
    val heartRateBpm: Int? = null,
    val streamingFps: Int? = null,
    val activeCueText: String = "No cue triggered",
    val cooldownRemainingMs: Long = 0L,
    val canPlayCue: Boolean = true,
    val lastEventLog: String? = null,
    val isSuppressedLastAttempt: Boolean = false,
    val totalCuesPlayed: Int = 0,
    val totalCuesSuppressed: Int = 0
)

@HiltViewModel
class LiveViewModel @Inject constructor(
    private val cuePlayer: CuePlayer
) : ViewModel() {

    private val _uiState = MutableStateFlow(LiveUiState())
    val uiState: StateFlow<LiveUiState> = _uiState.asStateFlow()

    init {
        // Collect cue events from CuePlayer
        viewModelScope.launch {
            cuePlayer.cueEvents.collect { event ->
                when (event) {
                    is CueEvent.Played -> {
                        _uiState.update { current ->
                            current.copy(
                                lastEventLog = "🎧 CUE PLAYED: \"${event.cueText ?: "Audio Clip"}\" routed to earbuds (USAGE_MEDIA • SPEECH)",
                                isSuppressedLastAttempt = false,
                                totalCuesPlayed = current.totalCuesPlayed + 1,
                                activeCueText = event.cueText ?: current.activeCueText
                            )
                        }
                    }
                    is CueEvent.Suppressed -> {
                        val seconds = String.format(java.util.Locale.US, "%.1f", event.remainingCooldownMs / 1000f)
                        _uiState.update { current ->
                            current.copy(
                                lastEventLog = "🛑 CUE SUPPRESSED: Attempted within 15s gap! ${seconds}s cooldown remaining.",
                                isSuppressedLastAttempt = true,
                                totalCuesSuppressed = current.totalCuesSuppressed + 1
                            )
                        }
                    }
                }
            }
        }

        // 200ms ticker for responsive countdown chip
        viewModelScope.launch {
            while (true) {
                val remaining = cuePlayer.getCooldownRemainingMs()
                val canPlay = cuePlayer.canPlayCue()
                _uiState.update {
                    it.copy(
                        cooldownRemainingMs = remaining,
                        canPlayCue = canPlay
                    )
                }
                delay(200)
            }
        }
    }

    /**
     * Trigger coaching cue through CuePlayer.
     * Enforces the minimum 15-second gap between cues.
     */
    fun triggerCue(cueText: String, audioUrl: String? = null) {
        cuePlayer.playCue(audioUrl = audioUrl, cueText = cueText)
    }

    /**
     * Clears debounce window (allows immediate test).
     */
    fun resetCooldown() {
        cuePlayer.resetDebounce()
        _uiState.update {
            it.copy(
                cooldownRemainingMs = 0L,
                canPlayCue = true,
                lastEventLog = "Cooldown reset: next cue will play immediately."
            )
        }
    }

    override fun onCleared() {
        super.onCleared()
        cuePlayer.stop()
    }
}
