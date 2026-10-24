package com.tempo.app.feature.correction.model

import android.graphics.Bitmap
import androidx.compose.ui.geometry.Offset
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PoseLandmarkPoint(
    val x: Float,
    val y: Float,
    val z: Float = 0f,
    val visibility: Float = 1.0f
)

@Serializable
data class FramePose(
    @SerialName("timestamp_ms") val timestampMs: Long,
    val landmarks: List<PoseLandmarkPoint>
)

@Serializable
data class CachedVideoPoseTrack(
    @SerialName("video_path") val videoPath: String,
    @SerialName("duration_ms") val durationMs: Long,
    val frames: List<FramePose>
)

@Serializable
data class KineticPhaseUiModel(
    @SerialName("phase_name") val phaseName: String,
    @SerialName("timestamp_ms") val timestampMs: Long,
    @SerialName("form_accuracy_score") val formAccuracyScore: Int,
    val observation: String,
    @SerialName("joint_angles") val jointAngles: Map<String, Float> = emptyMap()
)

data class JointAngleDeviation(
    val jointName: String,
    val athleteDeg: Float,
    val referenceDeg: Float,
    val deltaDeg: Float,
    val landmarkIndex: Int,
    val normalizedPosition: Offset
)

data class KeyframeComparison(
    val phase: KineticPhaseUiModel,
    val frameBitmap: Bitmap?,
    val athleteLandmarks: List<PoseLandmarkPoint>?,
    val referenceLandmarks: List<PoseLandmarkPoint>?,
    val deviations: List<JointAngleDeviation>
)

@Serializable
data class ReferenceArchetypeData(
    val sport: String,
    @SerialName("stroke_type") val strokeType: String,
    @SerialName("archetype_name") val archetypeName: String,
    val phases: List<ReferencePhaseData>
)

@Serializable
data class ReferencePhaseData(
    @SerialName("phase_name") val phaseName: String,
    @SerialName("timestamp_ms") val timestampMs: Long,
    @SerialName("ideal_angles") val idealAngles: Map<String, Float> = emptyMap(),
    val tolerances: Map<String, Float> = emptyMap(),
    val landmarks: List<PoseLandmarkPoint>
)
