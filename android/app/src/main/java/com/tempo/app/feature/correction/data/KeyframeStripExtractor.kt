package com.tempo.app.feature.correction.data

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import com.tempo.app.feature.correction.model.CachedVideoPoseTrack
import com.tempo.app.feature.correction.model.KeyframeComparison
import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.feature.correction.util.KinematicAngleCalculator
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.abs

@Singleton
class KeyframeStripExtractor @Inject constructor(
    @ApplicationContext private val context: Context,
    private val referenceLoader: ReferenceArchetypeLoader
) {

    suspend fun extractKeyframes(
        videoFile: File?,
        phases: List<KineticPhaseUiModel>,
        poseTrack: CachedVideoPoseTrack
    ): List<KeyframeComparison> = withContext(Dispatchers.IO) {
        val retriever = MediaMetadataRetriever()
        var hasValidRetriever = false
        if (videoFile != null && videoFile.exists() && videoFile.length() > 0L) {
            try {
                retriever.setDataSource(videoFile.absolutePath)
                hasValidRetriever = true
            } catch (e: Exception) {
                hasValidRetriever = false
            }
        }

        val comparisons = mutableListOf<KeyframeComparison>()

        try {
            for (phase in phases) {
                // 1. Extract frame bitmap at phase.timestampMs
                var bitmap: Bitmap? = null
                if (hasValidRetriever) {
                    try {
                        val timeUs = phase.timestampMs * 1000L
                        bitmap = retriever.getFrameAtTime(timeUs, MediaMetadataRetriever.OPTION_CLOSEST)
                    } catch (e: Exception) {
                        bitmap = null
                    }
                }

                // 2. Find closest athlete pose from cached track
                val athleteFrame = poseTrack.frames.minByOrNull { abs(it.timestampMs - phase.timestampMs) }
                val athleteLandmarks = athleteFrame?.landmarks

                // 3. Find matching reference phase landmarks
                val refPhase = referenceLoader.getPhaseReference(phase.phaseName)
                val refLandmarks = refPhase?.landmarks

                // 4. Compute joint deviations exceeding threshold
                val deviations = if (athleteLandmarks != null && refLandmarks != null) {
                    KinematicAngleCalculator.findDeviations(
                        athlete = athleteLandmarks,
                        reference = refLandmarks,
                        thresholdDeg = 10.0f
                    )
                } else {
                    emptyList()
                }

                comparisons.add(
                    KeyframeComparison(
                        phase = phase,
                        frameBitmap = bitmap,
                        athleteLandmarks = athleteLandmarks,
                        referenceLandmarks = refLandmarks,
                        deviations = deviations
                    )
                )
            }
        } finally {
            if (hasValidRetriever) {
                try {
                    retriever.release()
                } catch (e: Exception) {
                    // release
                }
            }
        }

        comparisons
    }
}
