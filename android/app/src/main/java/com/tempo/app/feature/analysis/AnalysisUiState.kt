package com.tempo.app.feature.analysis

import com.tempo.app.feature.correction.model.CachedVideoPoseTrack
import com.tempo.app.feature.correction.model.KeyframeComparison
import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.feature.sdui.model.Widget

enum class AnalysisStep {
    UPLOADING,
    PENDING,
    ANALYZING,
    COMPLETED,
    FAILED
}

data class BiomechanicalDebrief(
    val overallScore: Int?,
    val primaryFlaw: String,
    val matchedArchetype: String?,
    val audioCue: String? = null,
    val voiceNoteScript: String? = null,
    val voiceNoteUrl: String? = null
)

data class AnalysisUiState(
    val sessionId: String = "",
    val step: AnalysisStep = AnalysisStep.PENDING,
    val statusCopy: String = "Finding your swings...",
    val debrief: BiomechanicalDebrief? = null,
    val widgets: List<Widget> = emptyList(),
    val errorMessage: String? = null,
    val isPolling: Boolean = true,
    val videoPath: String? = null,
    val kineticPhases: List<KineticPhaseUiModel> = emptyList(),
    val poseTrack: CachedVideoPoseTrack? = null,
    val keyframeComparisons: List<KeyframeComparison> = emptyList(),
    val feedbackNotice: String? = null,
    val visualCorrectionMessage: String? = null,
    val isLoadingVisualCorrections: Boolean = false
)
