package com.tempo.app.feature.analysis

import com.tempo.app.feature.sdui.model.Widget

enum class AnalysisStep {
    UPLOADING,
    PENDING,
    ANALYZING,
    COMPLETED,
    FAILED
}

data class BiomechanicalDebrief(
    val overallScore: Int,
    val primaryFlaw: String,
    val matchedArchetype: String?,
    val audioCue: String? = null,
    val voiceNoteScript: String? = null
)

data class AnalysisUiState(
    val sessionId: String = "",
    val step: AnalysisStep = AnalysisStep.PENDING,
    val statusCopy: String = "Finding your swings...",
    val debrief: BiomechanicalDebrief? = null,
    val widgets: List<Widget> = emptyList(),
    val errorMessage: String? = null,
    val isPolling: Boolean = true
)
