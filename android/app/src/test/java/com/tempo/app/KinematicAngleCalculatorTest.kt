package com.tempo.app

import com.tempo.app.feature.correction.model.PoseLandmarkPoint
import com.tempo.app.feature.correction.util.KinematicAngleCalculator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class KinematicAngleCalculatorTest {

    @Test
    fun testRightAngleCalculation() {
        // Vertex at (0, 0), A at (0, 1), C at (1, 0) -> 90 degrees
        val a = PoseLandmarkPoint(x = 0f, y = 1f)
        val vertex = PoseLandmarkPoint(x = 0f, y = 0f)
        val c = PoseLandmarkPoint(x = 1f, y = 0f)

        val angle = KinematicAngleCalculator.calculateAngle(a, vertex, c)
        assertEquals(90.0f, angle, 0.1f)
    }

    @Test
    fun testStraightAngleCalculation() {
        // Full extension: A at (0.5, 0.3), Vertex at (0.5, 0.2), C at (0.5, 0.1) -> 180 degrees
        val a = PoseLandmarkPoint(x = 0.5f, y = 0.3f)
        val vertex = PoseLandmarkPoint(x = 0.5f, y = 0.2f)
        val c = PoseLandmarkPoint(x = 0.5f, y = 0.1f)

        val angle = KinematicAngleCalculator.calculateAngle(a, vertex, c)
        assertEquals(180.0f, angle, 0.1f)
    }

    @Test
    fun testDeviationDetectionExceedingThreshold() {
        // Create 33 dummy landmarks for reference (straight arm 180 deg)
        val refLandmarks = (0 until 33).map { idx ->
            when (idx) {
                KinematicAngleCalculator.RIGHT_SHOULDER -> PoseLandmarkPoint(0.5f, 0.3f)
                KinematicAngleCalculator.RIGHT_ELBOW -> PoseLandmarkPoint(0.5f, 0.2f)
                KinematicAngleCalculator.RIGHT_WRIST -> PoseLandmarkPoint(0.5f, 0.1f)
                else -> PoseLandmarkPoint(0.5f, 0.5f)
            }
        }

        // Athlete landmarks with bent elbow (flexed to 158 degrees -> ~22 deg deviation)
        val athLandmarks = (0 until 33).map { idx ->
            when (idx) {
                KinematicAngleCalculator.RIGHT_SHOULDER -> PoseLandmarkPoint(0.5f, 0.3f)
                KinematicAngleCalculator.RIGHT_ELBOW -> PoseLandmarkPoint(0.5f, 0.2f)
                KinematicAngleCalculator.RIGHT_WRIST -> PoseLandmarkPoint(0.46f, 0.11f) // tilted wrist
                else -> PoseLandmarkPoint(0.5f, 0.5f)
            }
        }

        val deviations = KinematicAngleCalculator.findDeviations(
            athlete = athLandmarks,
            reference = refLandmarks,
            thresholdDeg = 10.0f
        )

        assertTrue("Expected elbow deviation to be detected", deviations.any { it.jointName == "Right Elbow" })
        val elbowDev = deviations.first { it.jointName == "Right Elbow" }
        assertTrue("Expected deviation > 10 degrees", kotlin.math.abs(elbowDev.deltaDeg) >= 10.0f)
    }
}
