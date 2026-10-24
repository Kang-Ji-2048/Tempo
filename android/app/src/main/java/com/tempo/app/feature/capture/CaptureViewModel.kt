package com.tempo.app.feature.capture

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.feature.capture.model.CaptureUiState
import com.tempo.app.feature.capture.model.PreflightCheck
import com.tempo.app.feature.sdui.model.CapturePromptWidget
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

@HiltViewModel
class CaptureViewModel @Inject constructor(
    private val identity: com.tempo.app.data.PlayerIdentity
) : ViewModel() {
    private val _accessToken = MutableStateFlow("")
    val accessToken: StateFlow<String> = _accessToken.asStateFlow()
    fun setAccessToken(value: String) {
        _accessToken.value = value
        identity.accessToken = value
    }
    private val _playerId = MutableStateFlow(identity.playerId)
    val playerId: StateFlow<String> = _playerId.asStateFlow()
    fun setPlayerId(value: String) {
        _playerId.value = value.take(128)
        if (value.isNotBlank()) identity.playerId = value.take(128)
    }

    private var activePrompt = DEFAULT_PROMPT
    private var targetFps = 30
    private var countdownJob: Job? = null
    private var recordingJob: Job? = null

    var recordingStartMs: Long = 0L
        private set
    var recordingEndMs: Long = 0L
        private set

    private val _uiState = MutableStateFlow<CaptureUiState>(
        CaptureUiState.Preflight(
            prompt = activePrompt,
            targetFps = targetFps,
            fpsBadge = "$targetFps FPS",
        ),
    )
    val uiState: StateFlow<CaptureUiState> = _uiState.asStateFlow()

    fun setPrompt(prompt: CapturePromptWidget) {
        activePrompt = prompt
        _uiState.update { current ->
            when (current) {
                is CaptureUiState.Preflight -> current.copy(prompt = prompt)
                is CaptureUiState.CountingDown -> current.copy(prompt = prompt)
                is CaptureUiState.Recording -> current.copy(prompt = prompt)
                is CaptureUiState.Review -> current.copy(prompt = prompt)
                is CaptureUiState.ClipSaved -> current.copy(prompt = prompt)
                is CaptureUiState.PermissionRequired -> current
            }
        }
    }

    fun onPermissionsGranted() {
        _uiState.update {
            CaptureUiState.Preflight(
                prompt = activePrompt,
                targetFps = targetFps,
                fpsBadge = "$targetFps FPS",
            )
        }
    }

    fun onPermissionsDenied(missing: List<String>) {
        _uiState.value = CaptureUiState.PermissionRequired(missing)
    }

    fun onFpsDetermined(fps: Int) {
        targetFps = fps
        _uiState.update { current ->
            if (current is CaptureUiState.Preflight) {
                current.copy(targetFps = fps, fpsBadge = "$fps FPS")
            } else {
                current
            }
        }
    }

    fun onPreflightUpdated(check: PreflightCheck) {
        _uiState.update { current ->
            if (current is CaptureUiState.Preflight) {
                current.copy(preflight = check)
            } else {
                current
            }
        }
    }

    fun startCountdown(onStartCameraRecording: () -> Unit) {
        countdownJob?.cancel()
        countdownJob = viewModelScope.launch {
            _uiState.value = CaptureUiState.CountingDown(3, activePrompt, targetFps)
            for (i in 3 downTo 1) {
                _uiState.value = CaptureUiState.CountingDown(i, activePrompt, targetFps)
                delay(1000)
            }
            onStartCameraRecording()
        }
    }

    fun onRecordingStarted(onAutoStopCamera: () -> Unit) {
        countdownJob?.cancel()
        recordingJob?.cancel()
        recordingStartMs = System.currentTimeMillis()
        val duration = activePrompt.durationS.coerceAtLeast(5)

        recordingJob = viewModelScope.launch {
            _uiState.value = CaptureUiState.Recording(
                elapsedSeconds = 0,
                maxDurationSeconds = duration,
                prompt = activePrompt,
                targetFps = targetFps,
            )

            for (sec in 1..duration) {
                delay(1000)
                _uiState.update { current ->
                    if (current is CaptureUiState.Recording) {
                        current.copy(elapsedSeconds = sec)
                    } else {
                        current
                    }
                }
            }
            // Auto-stop at duration_s
            onAutoStopCamera()
        }
    }

    fun onRecordingFinalized(file: File?) {
        recordingJob?.cancel()
        recordingEndMs = System.currentTimeMillis()
        if (file != null && file.exists()) {
            _uiState.value = CaptureUiState.Review(file.absolutePath, activePrompt)
        } else {
            // If failed or empty, go back to preflight
            _uiState.value = CaptureUiState.Preflight(activePrompt, targetFps = targetFps, fpsBadge = "$targetFps FPS")
        }
    }

    fun retake(videoPath: String) {
        try {
            File(videoPath).delete()
        } catch (_: Exception) {}
        _uiState.value = CaptureUiState.Preflight(activePrompt, targetFps = targetFps, fpsBadge = "$targetFps FPS")
    }

    fun useClip(videoPath: String) {
        _uiState.value = CaptureUiState.ClipSaved(videoPath, activePrompt)
    }

    companion object {
        val DEFAULT_PROMPT = CapturePromptWidget(
            title = "Record 10 overhead clears",
            instruction = "Film from the side-rear so we can measure full reach and forearm pronation speed.",
            cameraHint = "Behind-left, 3m back, full body in frame",
            durationS = 15,
            id = "capture_clear_eval",
        )
    }
}
