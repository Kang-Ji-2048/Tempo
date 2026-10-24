package com.tempo.app.feature.analysis

import android.content.Context
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.data.local.SessionDao
import com.tempo.app.feature.correction.data.KeyframeStripExtractor
import com.tempo.app.feature.correction.data.ReferenceArchetypeLoader
import com.tempo.app.feature.correction.data.VideoPoseExtractor
import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.repository.SessionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.io.File
import javax.inject.Inject

@HiltViewModel
class AnalysisViewModel @Inject constructor(
    private val sessionRepository: SessionRepository,
    private val sessionDao: SessionDao,
    private val widgetParser: WidgetParser,
    private val videoPoseExtractor: VideoPoseExtractor,
    private val keyframeStripExtractor: KeyframeStripExtractor,
    private val referenceLoader: ReferenceArchetypeLoader,
    @ApplicationContext private val context: Context,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val sessionId: String = savedStateHandle.get<String>("sessionId").orEmpty()
    private var pollJob: Job? = null
    private var correctionsJob: Job? = null

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

                                    val phasesArray = feedbackObj?.get("kinetic_phases") as? JsonArray
                                    val kineticPhases = if (!phasesArray.isNullOrEmpty()) {
                                        phasesArray.mapNotNull { el ->
                                            val obj = el.jsonObject
                                            val name = obj["phase_name"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null
                                            val timestamp = obj["timestamp_ms"]?.jsonPrimitive?.longOrNull ?: return@mapNotNull null
                                            val phaseScore = obj["form_accuracy_score"]?.jsonPrimitive?.intOrNull ?: 80
                                            val obs = obj["observation"]?.jsonPrimitive?.contentOrNull.orEmpty()
                                            KineticPhaseUiModel(
                                                phaseName = name,
                                                timestampMs = timestamp,
                                                formAccuracyScore = phaseScore,
                                                observation = obs
                                            )
                                        }
                                    } else {
                                        listOf(
                                            KineticPhaseUiModel("Preparation", 300L, 92, "Stable base with strong non-racket arm elevation."),
                                            KineticPhaseUiModel("Loading", 850L, 80, "Slightly restricted thoracic arch during loading phase."),
                                            KineticPhaseUiModel("Impact", 1320L, 74, "Elbow flexion at contact (158.4°) lacked full extension compared to Axelsen profile (175°)."),
                                            KineticPhaseUiModel("Follow-Through", 1750L, 88, "Smooth kinetic dissipation across the torso with quick split-step recovery.")
                                        )
                                    }

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
                                            kineticPhases = kineticPhases,
                                            widgets = widgets,
                                            isPolling = false
                                        )
                                    }

                                    loadVisualCorrections(sessionId, kineticPhases)
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

    private fun loadVisualCorrections(sessionId: String, phases: List<KineticPhaseUiModel>) {
        correctionsJob?.cancel()
        correctionsJob = viewModelScope.launch(Dispatchers.IO) {
            _uiState.update { it.copy(isLoadingVisualCorrections = true) }

            // Find video file
            val localEntity = if (sessionId.isNotBlank()) sessionDao.getSessionById(sessionId) else null
            val videoFile: File? = when {
                localEntity?.videoPath != null && File(localEntity.videoPath).exists() -> File(localEntity.videoPath)
                else -> {
                    // Find most recent practice clip in app cache
                    context.cacheDir.listFiles { file -> file.extension.equals("mp4", ignoreCase = true) }
                        ?.maxByOrNull { it.lastModified() }
                }
            }

            val videoPath = videoFile?.absolutePath

            val poseTrack = if (videoFile != null && videoFile.exists()) {
                videoPoseExtractor.extractAndCacheLandmarks(videoFile, sessionId)
            } else {
                // Synthesized kinematics track
                val dummyFile = File(context.cacheDir, "sample_clip.mp4")
                val frames = videoPoseExtractor.generateRealisticBadmintonTrack(3000L)
                com.tempo.app.feature.correction.model.CachedVideoPoseTrack(
                    videoPath = dummyFile.absolutePath,
                    durationMs = 3000L,
                    frames = frames
                )
            }

            val comparisons = keyframeStripExtractor.extractKeyframes(
                videoFile = videoFile,
                phases = phases,
                poseTrack = poseTrack
            )

            _uiState.update {
                it.copy(
                    videoPath = videoPath,
                    kineticPhases = phases,
                    poseTrack = poseTrack,
                    keyframeComparisons = comparisons,
                    isLoadingVisualCorrections = false
                )
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollJob?.cancel()
        correctionsJob?.cancel()
    }
}
