package com.tempo.app

import com.tempo.app.feature.capture.CaptureViewModel
import com.tempo.app.feature.capture.model.CaptureUiState
import com.tempo.app.feature.capture.model.PreflightCheck
import com.tempo.app.feature.sdui.model.CapturePromptWidget
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File

class CapturePreflightTest {

    private lateinit var viewModel: CaptureViewModel

    @Before
    fun setUp() {
        viewModel = CaptureViewModel()
    }

    @Test
    fun preflightCheck_isReadyOnlyWhenAllThreePass() {
        // Neither passed
        val emptyCheck = PreflightCheck(bodyVisible = false, lightingOk = false, distanceOk = false)
        assertFalse(emptyCheck.isReady)

        // Only body visible
        val bodyOnly = PreflightCheck(bodyVisible = true, lightingOk = false, distanceOk = false)
        assertFalse(bodyOnly.isReady)

        // Body and lighting ok, but distance out of bounds
        val noDistance = PreflightCheck(bodyVisible = true, lightingOk = true, distanceOk = false, bodyHeightFraction = 0.25f)
        assertFalse(noDistance.isReady)

        // Distance in 40-80% frame, lighting ok, body visible
        val allPassed = PreflightCheck(
            bodyVisible = true,
            lightingOk = true,
            distanceOk = true,
            bodyHeightFraction = 0.65f,
            meanLuminance = 110f,
            failureHint = null,
        )
        assertTrue(allPassed.isReady)
    }

    @Test
    fun captureViewModel_handlesPromptUpdateAndFpsNegotiation() {
        val customPrompt = CapturePromptWidget(
            title = "Test Jump Smash Set",
            instruction = "Film from behind right",
            cameraHint = "Behind-right, 4m back",
            durationS = 20,
            id = "test_prompt_01",
        )

        viewModel.setPrompt(customPrompt)
        viewModel.onFpsDetermined(60)

        val state = viewModel.uiState.value
        assertTrue(state is CaptureUiState.Preflight)
        val preflightState = state as CaptureUiState.Preflight
        assertEquals("Test Jump Smash Set", preflightState.prompt.title)
        assertEquals(20, preflightState.prompt.durationS)
        assertEquals(60, preflightState.targetFps)
        assertEquals("60 FPS", preflightState.fpsBadge)
    }

    @Test
    fun captureViewModel_preflightUpdateUpdatesState() {
        val check = PreflightCheck(
            bodyVisible = true,
            lightingOk = true,
            distanceOk = true,
            bodyHeightFraction = 0.55f,
            meanLuminance = 95f,
            failureHint = null,
        )

        viewModel.onPreflightUpdated(check)
        val state = viewModel.uiState.value as CaptureUiState.Preflight
        assertTrue(state.preflight.isReady)
        assertEquals(0.55f, state.preflight.bodyHeightFraction, 0.001f)
    }

    @Test
    fun captureViewModel_recordingFinalizedTransitionsToReview() {
        val tempFile = File.createTempFile("test_clip_", ".mp4")
        tempFile.writeText("sample video clip bytes")

        viewModel.onRecordingFinalized(tempFile)
        val state = viewModel.uiState.value
        assertTrue("State should be Review", state is CaptureUiState.Review)
        val reviewState = state as CaptureUiState.Review
        assertEquals(tempFile.absolutePath, reviewState.videoPath)

        // Test use clip
        viewModel.useClip(tempFile.absolutePath)
        val savedState = viewModel.uiState.value
        assertTrue("State should be ClipSaved", savedState is CaptureUiState.ClipSaved)

        // Test retake
        viewModel.retake(tempFile.absolutePath)
        val retakeState = viewModel.uiState.value
        assertTrue("State should return to Preflight", retakeState is CaptureUiState.Preflight)

        tempFile.delete()
    }
}
