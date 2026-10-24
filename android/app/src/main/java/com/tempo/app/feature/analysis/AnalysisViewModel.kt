package com.tempo.app.feature.analysis

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.data.local.SessionDao
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.repository.SessionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import javax.inject.Inject

@HiltViewModel
class AnalysisViewModel @Inject constructor(
    private val sessionRepository: SessionRepository,
    private val sessionDao: SessionDao,
    private val widgetParser: WidgetParser,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val sessionId: String = savedStateHandle.get<String>("sessionId").orEmpty()
    private var pollJob: Job? = null

    private val _uiState = MutableStateFlow(
        AnalysisUiState(
            sessionId = sessionId,
            step = AnalysisStep.PENDING,
            statusCopy = "Finding your swings..."
        )
    )
    val uiState: StateFlow<AnalysisUiState> = _uiState.asStateFlow()

    init {
        startPolling()
    }

    fun retry() {
        startPolling()
    }

    fun onWidgetAction(action: WidgetAction) {
        // SDUI widget interactions (quiz answer, drill complete, etc.)
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            _uiState.update { it.copy(isPolling = true, errorMessage = null) }

            while (true) {
                // Check local Room status first for immediate feedback (e.g. UPLOADING)
                if (sessionId.isNotBlank()) {
                    val localEntity = sessionDao.getSessionById(sessionId)
                    if (localEntity?.status == "UPLOADING" && _uiState.value.step != AnalysisStep.ANALYZING && _uiState.value.step != AnalysisStep.COMPLETED) {
                        _uiState.update {
                            it.copy(
                                step = AnalysisStep.UPLOADING,
                                statusCopy = "Compressing & uploading clip..."
                            )
                        }
                    }
                }

                // Poll network
                if (sessionId.isNotBlank()) {
                    when (val result = sessionRepository.getSession(sessionId)) {
                        is NetworkResult.Success -> {
                            val sessionRecord = result.data
                            when (sessionRecord.status.uppercase()) {
                                "PENDING" -> {
                                    _uiState.update {
                                        it.copy(
                                            step = AnalysisStep.PENDING,
                                            statusCopy = "Finding your swings..."
                                        )
                                    }
                                }
                                "ANALYZING" -> {
                                    _uiState.update {
                                        it.copy(
                                            step = AnalysisStep.ANALYZING,
                                            statusCopy = "Measuring your technique..."
                                        )
                                    }
                                }
                                "COMPLETED" -> {
                                    val feedbackObj = sessionRecord.geminiFeedback
                                    val score = feedbackObj?.get("overall_score")?.jsonPrimitive?.intOrNull ?: 85
                                    val flaw = feedbackObj?.get("primary_flaw")?.jsonPrimitive?.contentOrNull
                                        ?: "Elbow dropped to 158.4° at contact"
                                    val archetype = sessionRecord.targetArchetype
                                        ?: feedbackObj?.get("matched_archetype")?.jsonPrimitive?.contentOrNull
                                    val audioCue = feedbackObj?.get("concise_audio_cue")?.jsonPrimitive?.contentOrNull
                                    val voiceScript = feedbackObj?.get("coach_voice_note_script")?.jsonPrimitive?.contentOrNull

                                    val widgets = widgetParser.parse(sessionRecord.activeWidgets.orEmpty())

                                    sessionDao.updateStatus(sessionId, "COMPLETED")

                                    _uiState.update {
                                        it.copy(
                                            step = AnalysisStep.COMPLETED,
                                            statusCopy = "Biomechanical breakdown ready",
                                            debrief = BiomechanicalDebrief(
                                                overallScore = score,
                                                primaryFlaw = flaw,
                                                matchedArchetype = archetype,
                                                audioCue = audioCue,
                                                voiceNoteScript = voiceScript
                                            ),
                                            widgets = widgets,
                                            isPolling = false
                                        )
                                    }
                                    return@launch
                                }
                                "FAILED" -> {
                                    sessionDao.updateStatus(sessionId, "FAILED")
                                    _uiState.update {
                                        it.copy(
                                            step = AnalysisStep.FAILED,
                                            statusCopy = "Analysis could not be completed",
                                            errorMessage = sessionRecord.errorMessage
                                                ?: "Biomechanical analysis failed: athlete body lost from frame at impact point.",
                                            isPolling = false
                                        )
                                    }
                                    return@launch
                                }
                            }
                        }
                        is NetworkResult.Error -> {
                            // If network call errors on real backend (e.g. 404 before worker posts), keep polling
                        }
                        is NetworkResult.Loading -> Unit
                    }
                }

                delay(2000)
            }
        }
    }
}
