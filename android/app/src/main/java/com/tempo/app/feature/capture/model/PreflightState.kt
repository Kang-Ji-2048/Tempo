package com.tempo.app.feature.capture.model

import com.tempo.app.feature.sdui.model.CapturePromptWidget

/**
 * Result of real-time pose and environment pre-flight checks on preview frames.
 */
data class PreflightCheck(
    val bodyVisible: Boolean = false,
    val lightingOk: Boolean = false,
    val distanceOk: Boolean = false,
    val bodyHeightFraction: Float = 0f,
    val meanLuminance: Float = 0f,
    val detectedLandmarksCount: Int = 0,
    val failureHint: String? = "Position yourself in front of the camera",
) {
    val isReady: Boolean
        get() = bodyVisible && lightingOk && distanceOk
}

/**
 * UI State machine for the sports capture experience.
 */
sealed interface CaptureUiState {
    data class PermissionRequired(val missingPermissions: List<String>) : CaptureUiState

    data class Preflight(
        val prompt: CapturePromptWidget,
        val preflight: PreflightCheck = PreflightCheck(),
        val targetFps: Int = 30,
        val fpsBadge: String = "30 FPS",
    ) : CaptureUiState

    data class CountingDown(
        val count: Int,
        val prompt: CapturePromptWidget,
        val targetFps: Int = 30,
    ) : CaptureUiState

    data class Recording(
        val elapsedSeconds: Int,
        val maxDurationSeconds: Int,
        val prompt: CapturePromptWidget,
        val targetFps: Int = 30,
    ) : CaptureUiState

    data class Review(
        val videoPath: String,
        val prompt: CapturePromptWidget,
    ) : CaptureUiState

    data class ClipSaved(
        val videoPath: String,
        val prompt: CapturePromptWidget,
    ) : CaptureUiState
}
