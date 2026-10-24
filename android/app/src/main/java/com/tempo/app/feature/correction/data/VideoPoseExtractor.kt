package com.tempo.app.feature.correction.data

import android.content.Context
import android.media.MediaMetadataRetriever
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker
import com.tempo.app.feature.correction.model.CachedVideoPoseTrack
import com.tempo.app.feature.correction.model.FramePose
import com.tempo.app.feature.correction.model.PoseLandmarkPoint
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class VideoPoseExtractor @Inject constructor(
    @ApplicationContext private val context: Context,
    private val json: Json
) {

    suspend fun extractAndCacheLandmarks(
        videoFile: File,
        sessionId: String,
        sampleIntervalMs: Long = 50L
    ): CachedVideoPoseTrack = withContext(Dispatchers.IO) {
        val cacheFile = File(context.cacheDir, "measured_landmarks_v2_${sessionId.ifBlank { videoFile.nameWithoutExtension }}.json")
        if (cacheFile.exists() && cacheFile.length() > 0L) {
            try {
                val cachedJson = cacheFile.readText()
                return@withContext json.decodeFromString<CachedVideoPoseTrack>(cachedJson)
            } catch (e: Exception) {
                // If corrupted, re-extract
                cacheFile.delete()
            }
        }

        // Initialize MediaMetadataRetriever
        val retriever = MediaMetadataRetriever()
        var durationMs = 3000L
        try {
            retriever.setDataSource(videoFile.absolutePath)
            val durationStr = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
            durationMs = durationStr?.toLongOrNull() ?: 3000L
        } catch (e: Exception) {
            // fallback duration
        }

        // Attempt MediaPipe PoseLandmarker in VIDEO mode
        var poseLandmarker: PoseLandmarker? = null
        try {
            val baseOptions = BaseOptions.builder()
                .setModelAssetPath("pose_landmarker_lite.task")
                .build()

            val options = PoseLandmarker.PoseLandmarkerOptions.builder()
                .setBaseOptions(baseOptions)
                .setRunningMode(RunningMode.VIDEO)
                .setMinPoseDetectionConfidence(0.4f)
                .setMinPosePresenceConfidence(0.4f)
                .setMinTrackingConfidence(0.4f)
                .build()

            poseLandmarker = PoseLandmarker.createFromOptions(context, options)
        } catch (e: Exception) {
            poseLandmarker = null
        }

        val extractedFrames = mutableListOf<FramePose>()
        val totalSamples = (durationMs / sampleIntervalMs).toInt().coerceIn(10, 120)

        try {
            for (i in 0 until totalSamples) {
                val timeMs = if (totalSamples <= 1) 0L else i * (durationMs - 1).coerceAtLeast(0L) / (totalSamples - 1)
                val timeUs = timeMs * 1000L
                val frameBitmap = try {
                    retriever.getFrameAtTime(timeUs, MediaMetadataRetriever.OPTION_CLOSEST)
                } catch (e: Exception) {
                    null
                }

                var detectedPose: FramePose? = null
                if (frameBitmap != null && poseLandmarker != null) {
                    try {
                        val mpImage = BitmapImageBuilder(frameBitmap).build()
                        val result = poseLandmarker.detectForVideo(mpImage, timeMs)
                        val landmarks = result.landmarks().firstOrNull()
                        if (!landmarks.isNullOrEmpty()) {
                            detectedPose = FramePose(
                                timestampMs = timeMs,
                                landmarks = landmarks.map { lm ->
                                    PoseLandmarkPoint(
                                        x = lm.x(),
                                        y = lm.y(),
                                        z = lm.z(),
                                        visibility = lm.visibility().orElse(1.0f)
                                    )
                                }
                            )
                        }
                    } catch (e: Exception) {
                        // Continue to fallback
                    }
                }

                if (detectedPose != null) {
                    extractedFrames.add(detectedPose)
                }
            }
        } finally {
            try {
                poseLandmarker?.close()
                retriever.release()
            } catch (e: Exception) {
                // cleanup
            }
        }

        val finalFrames = extractedFrames

        val track = CachedVideoPoseTrack(
            videoPath = videoFile.absolutePath,
            durationMs = durationMs,
            frames = finalFrames
        )

        // Cache to disk
        try {
            val jsonText = json.encodeToString(CachedVideoPoseTrack.serializer(), track)
            cacheFile.writeText(jsonText)
        } catch (e: Exception) {
            // cache write failure non-fatal
        }

        track
    }

}
