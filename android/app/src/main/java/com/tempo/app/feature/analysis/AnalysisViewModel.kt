package com.tempo.app.feature.analysis

import android.content.Context
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkManager
import androidx.work.WorkInfo
import com.tempo.app.data.local.SessionDao
import com.tempo.app.feature.correction.data.KeyframeStripExtractor
import com.tempo.app.feature.correction.data.VideoPoseExtractor
import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.feature.ingestion.work.IngestionScheduler
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.repository.SessionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
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
    @ApplicationContext private val context: Context,
    savedStateHandle: SavedStateHandle
) : ViewModel() {
    private val sessionId = savedStateHandle.get<String>("sessionId").orEmpty()
    private var pollJob: Job? = null
    private var correctionsJob: Job? = null
    private val _uiState = MutableStateFlow(AnalysisUiState(sessionId = sessionId))
    val uiState = _uiState.asStateFlow()

    init { startPolling() }

    fun retry() {
        viewModelScope.launch {
            val local = sessionDao.getSessionById(sessionId)
            if (local?.status == "UPLOAD_FAILED") {
                sessionDao.updateStatus(sessionId, "UPLOADING")
                val enqueueOperation = IngestionScheduler.scheduleUpload(
                    context = context, sessionId = sessionId, videoPath = local.videoPath,
                    userId = local.userId, sport = local.sport, strokeType = local.strokeType,
                    targetArchetype = local.targetArchetype, userIntent = local.userIntent
                )
                withContext(Dispatchers.IO) {
                    // Wait until enqueue is observable, so an older failed attempt
                    // cannot be mistaken for the new retry.
                    enqueueOperation.result.get()
                }
            }
            startPolling()
        }
    }

    fun onWidgetAction(action: WidgetAction) {
        // Widget completion persistence is a separate feature.
    }

    private fun fail(message: String) {
        _uiState.update { it.copy(step = AnalysisStep.FAILED, statusCopy = "Session needs attention",
            errorMessage = message, isPolling = false) }
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            try {
                _uiState.update { it.copy(isPolling = true, errorMessage = null) }
                if (sessionId.isBlank()) { fail("Missing session ID. Record a new clip."); return@launch }
                val startedAt = android.os.SystemClock.elapsedRealtime()
                var errors = 0
                while (android.os.SystemClock.elapsedRealtime() - startedAt < 15 * 60_000L) {
                    val local = sessionDao.getSessionById(sessionId)
                    val work = withContext(Dispatchers.IO) {
                        WorkManager.getInstance(context).getWorkInfosByTag("session_upload_$sessionId").get()
                    }
                    // Prefer an active retry over historical failed work with the same tag.
                    val activeWork = work.any { !it.state.isFinished }
                    if (local?.status == "UPLOAD_FAILED" || (!activeWork &&
                            local?.status !in listOf("PENDING", "ANALYZING", "COMPLETED", "FAILED") &&
                            work.any { it.state in listOf(WorkInfo.State.FAILED, WorkInfo.State.CANCELLED) })) {
                        if (local != null && local.status != "UPLOAD_FAILED") {
                            sessionDao.markFailed(sessionId, "Upload was interrupted. Tap Retry to upload again.")
                        }
                        fail(local?.errorMessage ?: "Upload failed or was cancelled. Tap Retry to upload again.")
                        return@launch
                    }
                    if (activeWork || local?.status == "UPLOADING") {
                        _uiState.update { it.copy(step = AnalysisStep.UPLOADING,
                            statusCopy = "Waiting for network, compressing or uploading clip...") }
                        delay(2000)
                        continue
                    }
                    when (val result = sessionRepository.getSession(sessionId)) {
                        is NetworkResult.Success -> {
                            errors = 0
                            val record = result.data
                            when (record.status.uppercase()) {
                                "PENDING", "ANALYZING" -> _uiState.update { it.copy(
                                    step = if (record.status.uppercase() == "PENDING") AnalysisStep.PENDING else AnalysisStep.ANALYZING,
                                    statusCopy = "Measuring your technique...") }
                                "COMPLETED" -> {
                                    val feedback = record.geminiFeedback
                                    fun text(key: String) = (feedback?.get(key) as? JsonPrimitive)?.contentOrNull
                                    val phases = (feedback?.get("kinetic_phases") as? JsonArray).orEmpty().mapNotNull { element ->
                                        val obj = element as? JsonObject ?: return@mapNotNull null
                                        val name = (obj["phase_name"] as? JsonPrimitive)?.contentOrNull ?: return@mapNotNull null
                                        val timestamp = (obj["timestamp_ms"] as? JsonPrimitive)?.longOrNull?.takeIf { it >= 0 } ?: return@mapNotNull null
                                        KineticPhaseUiModel(name, timestamp,
                                            (obj["form_accuracy_score"] as? JsonPrimitive)?.intOrNull?.takeIf { it in 0..100 },
                                            (obj["observation"] as? JsonPrimitive)?.contentOrNull.orEmpty())
                                    }
                                    sessionDao.updateStatus(sessionId, "COMPLETED")
                                    _uiState.update { it.copy(step = AnalysisStep.COMPLETED, statusCopy = "Analysis ready",
                                        debrief = BiomechanicalDebrief(
                                            (feedback?.get("overall_score") as? JsonPrimitive)?.intOrNull?.takeIf { it in 0..100 },
                                            (text("primary_flaw") ?: "No diagnosis was returned.") +
                                        if (text("reference_status") != "validated") " Reference profiles are illustrative and unvalidated." else "",
                                            text("matched_archetype"), text("concise_audio_cue"), text("coach_voice_note_script")),
                                        kineticPhases = phases, widgets = widgetParser.parse(record.activeWidgets.orEmpty()), isPolling = false,
                                        feedbackNotice = when {
                                            com.tempo.app.BuildConfig.USE_MOCK_API -> "Demo results: these are sample coaching responses."
                                            text("coaching_status") != "live" -> "Live coaching is unavailable. Showing measured, rule-based feedback."
                                            else -> null
                                        }) }
                                    loadVisualCorrections(phases)
                                    return@launch
                                }
                                "FAILED" -> {
                                    sessionDao.updateStatus(sessionId, "FAILED")
                                    fail(record.errorMessage ?: "Analysis failed. Record a new clip.")
                                    return@launch
                                }
                                else -> { fail("Unknown session status: ${record.status}"); return@launch }
                            }
                        }
                        is NetworkResult.Error -> {
                            errors++
                            if (result.code in listOf(401, 403) || errors >= 5) {
                                fail(result.message ?: "Cannot retrieve this session. Check the backend connection and tap Retry.")
                                return@launch
                            }
                            _uiState.update { it.copy(statusCopy = "Reconnecting to the analysis service...") }
                        }
                        is NetworkResult.Loading -> Unit
                    }
                    delay(2000)
                }
                fail("Session timed out. Check the upload and backend, then tap Retry.")
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                fail("Cannot read upload status. Check local storage and tap Retry.")
            }
        }
    }

    private fun loadVisualCorrections(phases: List<KineticPhaseUiModel>) {
        correctionsJob?.cancel()
        correctionsJob = viewModelScope.launch(Dispatchers.IO) {
            _uiState.update { it.copy(isLoadingVisualCorrections = true) }
            try {
                val path = sessionDao.getSessionById(sessionId)?.videoPath
                val file = path?.let(::File)?.takeIf { it.exists() && it.length() > 0L }
                if (file == null) {
                    _uiState.update { it.copy(visualCorrectionMessage = "The video for this session is unavailable.") }
                    return@launch
                }
                val track = videoPoseExtractor.extractAndCacheLandmarks(file, sessionId)
                val comparisons = keyframeStripExtractor.extractKeyframes(file, phases, track)
                _uiState.update { it.copy(videoPath = file.absolutePath, poseTrack = track,
                    keyframeComparisons = comparisons, visualCorrectionMessage = when {
                        track.frames.isEmpty() -> "No reliable skeleton was detected in this clip."
                        phases.isEmpty() -> "Phase timing and scores were not returned. Video playback and detected pose are available."
                        else -> null
                    }) }
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) {
                _uiState.update { it.copy(visualCorrectionMessage = "Visual correction is unavailable for this clip.") }
            } finally {
                _uiState.update { it.copy(isLoadingVisualCorrections = false) }
            }
        }
    }
}
