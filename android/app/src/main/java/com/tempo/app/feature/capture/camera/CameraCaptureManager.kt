package com.tempo.app.feature.capture.camera

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CaptureRequest
import android.util.Range
import androidx.annotation.OptIn
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.tempo.app.feature.capture.analyzer.PosePreflightAnalyzer
import java.io.File
import java.util.concurrent.Executors

/**
 * Manages CameraX preview, 60fps/30fps query and negotiation,
 * real-time ImageAnalysis pre-flight checking, and 720p-1080p video recording to app cache.
 */
class CameraCaptureManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val onFpsDetermined: (Int) -> Unit,
    private val onRecordingStarted: () -> Unit,
    private val onRecordingFinalized: (File?) -> Unit,
    private val onRecordingError: (String) -> Unit,
) {
    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private var cameraProvider: ProcessCameraProvider? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var activeRecording: Recording? = null
    private var currentOutputFile: File? = null
    private var camera: Camera? = null

    var configuredFps: Int = 30
        private set

    @OptIn(ExperimentalCamera2Interop::class)
    fun startCamera(
        previewView: PreviewView,
        analyzer: PosePreflightAnalyzer,
    ) {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener({
            try {
                val provider = cameraProviderFuture.get()
                cameraProvider = provider
                provider.unbindAll()

                val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

                // 1. Query device support for 60fps vs 30fps
                val cameraInfo = provider.availableCameraInfos.firstOrNull {
                    cameraSelector.filter(listOf(it)).isNotEmpty()
                }

                val fpsRange = queryBestFpsRange(cameraInfo)
                configuredFps = fpsRange.upper
                onFpsDetermined(configuredFps)

                // 2. Build Preview with 60fps target if supported
                val previewBuilder = Preview.Builder()
                Camera2Interop.Extender(previewBuilder)
                    .setCaptureRequestOption(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, fpsRange)

                val preview = previewBuilder.build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }

                // 3. Configure 720p-1080p Recorder
                val qualitySelector = QualitySelector.fromOrderedList(
                    listOf(Quality.FHD, Quality.HD),
                )
                val recorder = Recorder.Builder()
                    .setQualitySelector(qualitySelector)
                    .setExecutor(ContextCompat.getMainExecutor(context))
                    .build()

                videoCapture = VideoCapture.withOutput(recorder)

                // 4. Configure ImageAnalysis for MediaPipe Preflight
                val imageAnalysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .build()
                    .also {
                        it.setAnalyzer(analysisExecutor, analyzer)
                    }

                // 5. Bind lifecycle
                camera = provider.bindToLifecycle(
                    lifecycleOwner,
                    cameraSelector,
                    preview,
                    videoCapture,
                    imageAnalysis,
                )
            } catch (e: Exception) {
                onRecordingError("Camera initialization failed: ${e.message}")
            }
        }, ContextCompat.getMainExecutor(context))
    }

    @OptIn(ExperimentalCamera2Interop::class)
    private fun queryBestFpsRange(cameraInfo: androidx.camera.core.CameraInfo?): Range<Int> {
        if (cameraInfo == null) return Range(30, 30)
        return try {
            val camera2Info = Camera2CameraInfo.from(cameraInfo)
            val availableRanges = camera2Info.getCameraCharacteristic(
                CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES,
            ) ?: emptyArray()

            // Find a range that supports 60fps, e.g. [60, 60] or [30, 60]
            val sixtyRange = availableRanges.firstOrNull { it.upper >= 60 }
            sixtyRange ?: availableRanges.firstOrNull { it.upper >= 30 } ?: Range(30, 30)
        } catch (_: Exception) {
            Range(30, 30)
        }
    }

    @SuppressLint("MissingPermission")
    fun startRecording(hasAudioPermission: Boolean) {
        val capture = videoCapture ?: return
        if (activeRecording != null) return

        val outputFile = File(
            context.cacheDir,
            "tempo_practice_${System.currentTimeMillis()}.mp4",
        )
        currentOutputFile = outputFile

        val outputOptions = FileOutputOptions.Builder(outputFile).build()
        val pendingRecording = capture.output.prepareRecording(context, outputOptions)

        if (hasAudioPermission) {
            try {
                pendingRecording.withAudioEnabled()
            } catch (_: SecurityException) {}
        }

        activeRecording = pendingRecording.start(ContextCompat.getMainExecutor(context)) { event ->
            when (event) {
                is VideoRecordEvent.Start -> {
                    onRecordingStarted()
                }
                is VideoRecordEvent.Finalize -> {
                    activeRecording = null
                    if (!event.hasError()) {
                        onRecordingFinalized(currentOutputFile)
                    } else {
                        onRecordingError("Recording failed: ${event.cause?.message ?: event.error}")
                        onRecordingFinalized(null)
                    }
                }
            }
        }
    }

    fun stopRecording() {
        activeRecording?.stop()
        activeRecording = null
    }

    fun release() {
        stopRecording()
        cameraProvider?.unbindAll()
        analysisExecutor.shutdown()
    }
}
