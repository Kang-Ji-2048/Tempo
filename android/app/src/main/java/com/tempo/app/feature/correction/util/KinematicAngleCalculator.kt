package com.tempo.app.feature.correction.util

import androidx.compose.ui.geometry.Offset
import com.tempo.app.feature.correction.model.JointAngleDeviation
import com.tempo.app.feature.correction.model.PoseLandmarkPoint
import kotlin.math.acos
import kotlin.math.abs
import kotlin.math.sqrt

object KinematicAngleCalculator {

    // Landmark indices from MediaPipe Pose (33 points)
    const val LEFT_SHOULDER = 11
    const val RIGHT_SHOULDER = 12
    const val LEFT_ELBOW = 13
    const val RIGHT_ELBOW = 14
    const val LEFT_WRIST = 15
    const val RIGHT_WRIST = 16
    const val LEFT_HIP = 23
    const val RIGHT_HIP = 24
    const val LEFT_KNEE = 25
    const val RIGHT_KNEE = 26
    const val LEFT_ANKLE = 27
    const val RIGHT_ANKLE = 28

    fun calculateAngle(
        a: PoseLandmarkPoint,
        vertex: PoseLandmarkPoint,
        c: PoseLandmarkPoint
    ): Float {
        val v1x = a.x - vertex.x
        val v1y = a.y - vertex.y
        val v2x = c.x - vertex.x
        val v2y = c.y - vertex.y

        val dot = v1x * v2x + v1y * v2y
        val mag1 = sqrt(v1x * v1x + v1y * v1y)
        val mag2 = sqrt(v2x * v2x + v2y * v2y)

        if (mag1 == 0f || mag2 == 0f) return 180f
        val cosTheta = (dot / (mag1 * mag2)).coerceIn(-1.0f, 1.0f)
        return Math.toDegrees(acos(cosTheta.toDouble())).toFloat()
    }

    fun findDeviations(
        athlete: List<PoseLandmarkPoint>,
        reference: List<PoseLandmarkPoint>,
        thresholdDeg: Float = 10.0f
    ): List<JointAngleDeviation> {
        if (athlete.size < 33 || reference.size < 33) return emptyList()

        val deviations = mutableListOf<JointAngleDeviation>()

        // 1. Right Elbow (Shoulder 12 - Elbow 14 - Wrist 16)
        val athRightElbow = calculateAngle(athlete[RIGHT_SHOULDER], athlete[RIGHT_ELBOW], athlete[RIGHT_WRIST])
        val refRightElbow = calculateAngle(reference[RIGHT_SHOULDER], reference[RIGHT_ELBOW], reference[RIGHT_WRIST])
        val deltaRightElbow = athRightElbow - refRightElbow
        if (abs(deltaRightElbow) >= thresholdDeg) {
            deviations.add(
                JointAngleDeviation(
                    jointName = "Right Elbow",
                    athleteDeg = athRightElbow,
                    referenceDeg = refRightElbow,
                    deltaDeg = deltaRightElbow,
                    landmarkIndex = RIGHT_ELBOW,
                    normalizedPosition = Offset(athlete[RIGHT_ELBOW].x, athlete[RIGHT_ELBOW].y)
                )
            )
        }

        // 2. Right Shoulder Abduction (Hip 24 - Shoulder 12 - Elbow 14)
        val athRightShoulder = calculateAngle(athlete[RIGHT_HIP], athlete[RIGHT_SHOULDER], athlete[RIGHT_ELBOW])
        val refRightShoulder = calculateAngle(reference[RIGHT_HIP], reference[RIGHT_SHOULDER], reference[RIGHT_ELBOW])
        val deltaRightShoulder = athRightShoulder - refRightShoulder
        if (abs(deltaRightShoulder) >= thresholdDeg) {
            deviations.add(
                JointAngleDeviation(
                    jointName = "Shoulder Abduction",
                    athleteDeg = athRightShoulder,
                    referenceDeg = refRightShoulder,
                    deltaDeg = deltaRightShoulder,
                    landmarkIndex = RIGHT_SHOULDER,
                    normalizedPosition = Offset(athlete[RIGHT_SHOULDER].x, athlete[RIGHT_SHOULDER].y)
                )
            )
        }

        // 3. Left Elbow (Shoulder 11 - Elbow 13 - Wrist 15)
        val athLeftElbow = calculateAngle(athlete[LEFT_SHOULDER], athlete[LEFT_ELBOW], athlete[LEFT_WRIST])
        val refLeftElbow = calculateAngle(reference[LEFT_SHOULDER], reference[LEFT_ELBOW], reference[LEFT_WRIST])
        val deltaLeftElbow = athLeftElbow - refLeftElbow
        if (abs(deltaLeftElbow) >= thresholdDeg) {
            deviations.add(
                JointAngleDeviation(
                    jointName = "Left Elbow",
                    athleteDeg = athLeftElbow,
                    referenceDeg = refLeftElbow,
                    deltaDeg = deltaLeftElbow,
                    landmarkIndex = LEFT_ELBOW,
                    normalizedPosition = Offset(athlete[LEFT_ELBOW].x, athlete[LEFT_ELBOW].y)
                )
            )
        }

        return deviations
    }
}
