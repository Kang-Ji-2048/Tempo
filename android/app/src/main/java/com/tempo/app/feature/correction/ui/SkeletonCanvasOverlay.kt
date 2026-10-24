package com.tempo.app.feature.correction.ui

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.unit.dp
import com.tempo.app.feature.correction.model.JointAngleDeviation
import com.tempo.app.feature.correction.model.PoseLandmarkPoint
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.WarningAmber

// Color tokens for dual-skeleton rendering
val ColorAthleteSkeleton = AccentNeonVolt // #CCFF00
val ColorReferenceSkeleton = Color(0xFF00E5FF) // Electric Cyan

// Standard MediaPipe Pose 33-landmark bone pairs
val POSE_CONNECTIONS = listOf(
    // Torso & Shoulders
    Pair(11, 12),
    Pair(11, 23),
    Pair(12, 24),
    Pair(23, 24),
    // Right Arm
    Pair(12, 14),
    Pair(14, 16),
    // Left Arm
    Pair(11, 13),
    Pair(13, 15),
    // Right Leg
    Pair(24, 26),
    Pair(26, 28),
    Pair(28, 30),
    Pair(28, 32),
    Pair(30, 32),
    // Left Leg
    Pair(23, 25),
    Pair(25, 27),
    Pair(27, 29),
    Pair(27, 31),
    Pair(29, 31),
    // Head / Face
    Pair(0, 1),
    Pair(1, 2),
    Pair(2, 3),
    Pair(3, 7),
    Pair(0, 4),
    Pair(4, 5),
    Pair(5, 6),
    Pair(6, 8),
    Pair(9, 10)
)

@Composable
fun SkeletonCanvasOverlay(
    athleteLandmarks: List<PoseLandmarkPoint>?,
    modifier: Modifier = Modifier,
    referenceLandmarks: List<PoseLandmarkPoint>? = null,
    deviations: List<JointAngleDeviation> = emptyList(),
    showLegend: Boolean = false
) {
    Canvas(modifier = modifier.fillMaxSize()) {
        val width = size.width
        val height = size.height

        // 1. Draw Reference Skeleton (Electric Cyan, slightly dashed or thinner)
        if (!referenceLandmarks.isNullOrEmpty() && referenceLandmarks.size >= 33) {
            drawSkeleton(
                landmarks = referenceLandmarks,
                boneColor = ColorReferenceSkeleton.copy(alpha = 0.85f),
                jointColor = ColorReferenceSkeleton,
                strokeWidthPx = 4.dp.toPx(),
                width = width,
                height = height
            )
        }

        // 2. Draw Athlete Skeleton (Neon Volt, dominant)
        if (!athleteLandmarks.isNullOrEmpty() && athleteLandmarks.size >= 33) {
            drawSkeleton(
                landmarks = athleteLandmarks,
                boneColor = ColorAthleteSkeleton.copy(alpha = 0.95f),
                jointColor = ColorAthleteSkeleton,
                strokeWidthPx = 5.dp.toPx(),
                width = width,
                height = height
            )
        }

        // 3. Draw Angle Deviation Badges on Joints
        for (deviation in deviations) {
            val jointPos = Offset(
                x = deviation.normalizedPosition.x * width,
                y = deviation.normalizedPosition.y * height
            )

            // Draw highlight ring on joint
            drawCircle(
                color = if (deviation.deltaDeg < 0) ErrorRed else WarningAmber,
                radius = 12.dp.toPx(),
                center = jointPos,
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3.dp.toPx())
            )

            // Draw callout badge
            val badgeText = "${deviation.jointName} Δ${if (deviation.deltaDeg > 0) "+" else ""}${String.format("%.1f°", deviation.deltaDeg)}"
            val badgeOffset = Offset(
                x = (jointPos.x + 20.dp.toPx()).coerceAtMost(width - 160.dp.toPx()),
                y = (jointPos.y - 18.dp.toPx()).coerceAtLeast(20.dp.toPx())
            )

            // Connecting indicator line
            drawLine(
                color = WarningAmber,
                start = jointPos,
                end = Offset(badgeOffset.x, badgeOffset.y + 12.dp.toPx()),
                strokeWidth = 2.dp.toPx()
            )

            // Badge Background
            drawRoundRect(
                color = BackgroundOnyx.copy(alpha = 0.92f),
                topLeft = badgeOffset,
                size = Size(150.dp.toPx(), 28.dp.toPx()),
                cornerRadius = CornerRadius(8.dp.toPx())
            )
            drawRoundRect(
                color = if (deviation.deltaDeg < 0) ErrorRed else WarningAmber,
                topLeft = badgeOffset,
                size = Size(150.dp.toPx(), 28.dp.toPx()),
                cornerRadius = CornerRadius(8.dp.toPx()),
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 1.5.dp.toPx())
            )

            // Native canvas text rendering
            val paint = Paint().apply {
                color = android.graphics.Color.WHITE
                textSize = 11.dp.toPx()
                isFakeBoldText = true
                isAntiAlias = true
            }
            drawContext.canvas.nativeCanvas.drawText(
                badgeText,
                badgeOffset.x + 8.dp.toPx(),
                badgeOffset.y + 18.dp.toPx(),
                paint
            )
        }
    }
}

private fun DrawScope.drawSkeleton(
    landmarks: List<PoseLandmarkPoint>,
    boneColor: Color,
    jointColor: Color,
    strokeWidthPx: Float,
    width: Float,
    height: Float
) {
    // Draw bones
    for ((idxA, idxB) in POSE_CONNECTIONS) {
        if (idxA < landmarks.size && idxB < landmarks.size) {
            val a = landmarks[idxA]
            val b = landmarks[idxB]
            if (a.visibility > 0.3f && b.visibility > 0.3f) {
                drawLine(
                    color = boneColor,
                    start = Offset(a.x * width, a.y * height),
                    end = Offset(b.x * width, b.y * height),
                    strokeWidth = strokeWidthPx,
                    cap = StrokeCap.Round
                )
            }
        }
    }

    // Draw joint vertices
    val jointRadius = (strokeWidthPx * 1.2f).coerceAtLeast(4.dp.toPx())
    for (i in listOf(11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28)) {
        if (i < landmarks.size) {
            val lm = landmarks[i]
            if (lm.visibility > 0.3f) {
                drawCircle(
                    color = jointColor,
                    radius = jointRadius,
                    center = Offset(lm.x * width, lm.y * height)
                )
                drawCircle(
                    color = BackgroundOnyx,
                    radius = jointRadius * 0.4f,
                    center = Offset(lm.x * width, lm.y * height)
                )
            }
        }
    }
}
