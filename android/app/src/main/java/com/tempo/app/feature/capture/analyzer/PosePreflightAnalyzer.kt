package com.tempo.app.feature.capture.analyzer

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.framework.image.MPImage
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarkerResult
import com.tempo.app.feature.capture.model.PreflightCheck
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.max
import kotlin.math.min

/**
 * Runs MediaPipe Pose Landmarker in LIVE_STREAM mode on preview frames to compute
 * real-time preflight checks (body visibility, lighting luminance, distance fraction).
 */
class PosePreflightAnalyzer(
    context: Context,
    private val onPreflightUpdated: (PreflightCheck) -> Unit,
) : ImageAnalysis.Analyzer {

    private val isProcessing = AtomicBoolean(false)
    private var lastLuminance = 0f
    private var poseLandmarker: PoseLandmarker? = null

    init {
        try {
            val baseOptions = BaseOptions.builder()
                .setModelAssetPath("pose_landmarker_lite.task")
                .build()

            val options = PoseLandmarker.PoseLandmarkerOptions.builder()
                .setBaseOptions(baseOptions)
                .setRunningMode(RunningMode.LIVE_STREAM)
                .setMinPoseDetectionConfidence(0.5f)
                .setMinPosePresenceConfidence(0.5f)
                .setMinTrackingConfidence(0.5f)
                .setResultListener(::onPoseResult)
                .setErrorListener { error ->
                    isProcessing.set(false)
                }
                .build()

            poseLandmarker = PoseLandmarker.createFromOptions(context, options)
        } catch (e: Exception) {
            // Pose landmarker fallback: if asset fails, allow app to proceed with simulated preflight
            poseLandmarker = null
        }
    }

    @OptIn(ExperimentalGetImage::class)
    override fun analyze(imageProxy: ImageProxy) {
        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val timestampMs = imageProxy.imageInfo.timestamp / 1_000_000

        // 1. Calculate lighting (mean luminance) from Y-plane
        val luminance = calculateMeanLuminance(imageProxy)
        lastLuminance = luminance

        // Throttle frame processing to prevent thread starvation
        if (!isProcessing.compareAndSet(false, true)) {
            imageProxy.close()
            return
        }

        val landmarker = poseLandmarker
        if (landmarker == null) {
            // Fallback if landmarker couldn't initialize: evaluate lighting only
            val lightingOk = luminance >= MIN_LUMINANCE
            val check = PreflightCheck(
                bodyVisible = true,
                lightingOk = lightingOk,
                distanceOk = true,
                bodyHeightFraction = 0.65f,
                meanLuminance = luminance,
                failureHint = if (!lightingOk) "Too dark — increase lighting on athlete" else null,
            )
            onPreflightUpdated(check)
            isProcessing.set(false)
            imageProxy.close()
            return
        }

        try {
            val bitmap = imageProxy.toBitmap()
            val rotatedBitmap = if (rotationDegrees != 0) {
                val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
                Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
            } else {
                bitmap
            }

            val mpImage: MPImage = BitmapImageBuilder(rotatedBitmap).build()
            landmarker.detectAsync(mpImage, timestampMs)
        } catch (e: Exception) {
            isProcessing.set(false)
        } finally {
            imageProxy.close()
        }
    }

    private fun onPoseResult(result: PoseLandmarkerResult, input: MPImage) {
        try {
            val allPoses = result.landmarks()
            if (allPoses.isEmpty()) {
                val lightingOk = lastLuminance >= MIN_LUMINANCE
                val hint = when {
                    !lightingOk -> "Too dark — increase lighting on athlete"
                    else -> "Step into frame so your full body is visible"
                }
                onPreflightUpdated(
                    PreflightCheck(
                        bodyVisible = false,
                        lightingOk = lightingOk,
                        distanceOk = false,
                        bodyHeightFraction = 0f,
                        meanLuminance = lastLuminance,
                        detectedLandmarksCount = 0,
                        failureHint = hint,
                    ),
                )
                return
            }

            val landmarks = allPoses[0]
            val count = landmarks.size

            // 1. Check Body Visibility: Essential landmarks must be detected and within bounds
            // Nose (0), Shoulders (11, 12), Hips (23, 24), Knees (25, 26), Ankles (27, 28)
            val headLandmark = landmarks.getOrNull(0)
            val leftShoulder = landmarks.getOrNull(11)
            val rightShoulder = landmarks.getOrNull(12)
            val leftHip = landmarks.getOrNull(23)
            val rightHip = landmarks.getOrNull(24)
            val leftKnee = landmarks.getOrNull(25)
            val rightKnee = landmarks.getOrNull(26)
            val leftAnkle = landmarks.getOrNull(27)
            val rightAnkle = landmarks.getOrNull(28)

            val essentialPresent = headLandmark != null &&
                (leftShoulder != null || rightShoulder != null) &&
                (leftHip != null || rightHip != null) &&
                (leftKnee != null || rightKnee != null) &&
                (leftAnkle != null || rightAnkle != null)

            // Ensure key landmarks are not cut off at screen edges
            val inFrame = landmarks.all { lm ->
                val x = lm.x()
                val y = lm.y()
                x in 0.02f..0.98f && y in 0.02f..0.98f
            }

            // Head and feet must be distinct
            val minY = landmarks.minOf { it.y() }
            val maxY = landmarks.maxOf { it.y() }
            val bodyHeight = (maxY - minY).coerceIn(0f, 1f)

            val bodyVisible = essentialPresent && inFrame && bodyHeight > 0.20f
            val lightingOk = lastLuminance >= MIN_LUMINANCE
            val distanceOk = bodyHeight in MIN_BODY_HEIGHT..MAX_BODY_HEIGHT

            val hint = when {
                !bodyVisible -> "Full body not visible — step into frame from head to feet"
                !lightingOk -> "Lighting too dark — face a light source or turn on lights"
                bodyHeight < MIN_BODY_HEIGHT -> "Move closer — body must fill 40–80% of frame (${(bodyHeight * 100).toInt()}%)"
                bodyHeight > MAX_BODY_HEIGHT -> "Step back — body is too close to frame (${(bodyHeight * 100).toInt()}%)"
                else -> null
            }

            onPreflightUpdated(
                PreflightCheck(
                    bodyVisible = bodyVisible,
                    lightingOk = lightingOk,
                    distanceOk = distanceOk,
                    bodyHeightFraction = bodyHeight,
                    meanLuminance = lastLuminance,
                    detectedLandmarksCount = count,
                    failureHint = hint,
                ),
            )
        } finally {
            isProcessing.set(false)
        }
    }

    private fun calculateMeanLuminance(imageProxy: ImageProxy): Float {
        val planes = imageProxy.planes
        if (planes.isEmpty()) return 100f
        val buffer = planes[0].buffer
        val limit = buffer.limit()
        if (limit == 0) return 100f

        var sum = 0L
        var count = 0
        // Sample every 32 bytes for instant computation
        val step = max(32, limit / 1024)
        var i = 0
        while (i < limit) {
            val byteVal = buffer.get(i).toInt() and 0xFF
            sum += byteVal
            count++
            i += step
        }
        return if (count > 0) sum.toFloat() / count else 100f
    }

    fun close() {
        try {
            poseLandmarker?.close()
        } catch (_: Exception) {}
        poseLandmarker = null
    }

    companion object {
        const val MIN_LUMINANCE = 45f
        const val MIN_BODY_HEIGHT = 0.40f
        const val MAX_BODY_HEIGHT = 0.80f
    }
}
