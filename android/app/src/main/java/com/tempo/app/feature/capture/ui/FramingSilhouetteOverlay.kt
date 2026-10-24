package com.tempo.app.feature.capture.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.TextPrimaryWhite

/**
 * Framing guide overlay showing an athletic body-outline silhouette
 * and coach camera hint (e.g. "Film from behind-left, full body in frame").
 */
@Composable
fun FramingSilhouetteOverlay(
    cameraHint: String,
    isBodyInFrame: Boolean,
    modifier: Modifier = Modifier,
) {
    val silhouetteColor by animateColorAsState(
        targetValue = if (isBodyInFrame) AccentNeonVolt.copy(alpha = 0.85f) else Color.White.copy(alpha = 0.35f),
        label = "silhouetteColor",
    )

    Box(modifier = modifier.fillMaxSize()) {
        // Body outline silhouette canvas
        Canvas(modifier = Modifier.fillMaxSize()) {
            val width = size.width
            val height = size.height

            val centerX = width * 0.5f
            val topY = height * 0.16f
            val bottomY = height * 0.84f
            val bodySpan = bottomY - topY

            // 1. Head oval
            val headRadius = bodySpan * 0.08f
            val headCenter = Offset(centerX, topY + headRadius)
            drawCircle(
                color = silhouetteColor,
                radius = headRadius,
                center = headCenter,
                style = Stroke(
                    width = 3.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(16f, 12f)),
                ),
            )

            // 2. Torso, arms & legs silhouette path
            val path = Path().apply {
                val shoulderY = headCenter.y + headRadius + 16f
                val shoulderHalfWidth = bodySpan * 0.16f
                val hipY = shoulderY + bodySpan * 0.35f
                val hipHalfWidth = bodySpan * 0.12f
                val kneeY = hipY + bodySpan * 0.22f
                val footY = bottomY

                // Shoulders & Torso
                moveTo(centerX - shoulderHalfWidth, shoulderY)
                lineTo(centerX + shoulderHalfWidth, shoulderY)
                lineTo(centerX + hipHalfWidth, hipY)
                lineTo(centerX - hipHalfWidth, hipY)
                close()

                // Left Arm ready stance
                moveTo(centerX - shoulderHalfWidth, shoulderY)
                lineTo(centerX - shoulderHalfWidth * 1.4f, shoulderY + bodySpan * 0.20f)
                lineTo(centerX - shoulderHalfWidth * 1.1f, shoulderY + bodySpan * 0.35f)

                // Right Arm (racquet/throw reach)
                moveTo(centerX + shoulderHalfWidth, shoulderY)
                lineTo(centerX + shoulderHalfWidth * 1.4f, shoulderY + bodySpan * 0.20f)
                lineTo(centerX + shoulderHalfWidth * 1.1f, shoulderY + bodySpan * 0.35f)

                // Left Leg
                moveTo(centerX - hipHalfWidth * 0.8f, hipY)
                lineTo(centerX - hipHalfWidth * 0.9f, kneeY)
                lineTo(centerX - hipHalfWidth * 1.1f, footY)

                // Right Leg
                moveTo(centerX + hipHalfWidth * 0.8f, hipY)
                lineTo(centerX + hipHalfWidth * 0.9f, kneeY)
                lineTo(centerX + hipHalfWidth * 1.1f, footY)
            }

            drawPath(
                path = path,
                color = silhouetteColor,
                style = Stroke(
                    width = 3.dp.toPx(),
                    cap = StrokeCap.Round,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(16f, 12f)),
                ),
            )

            // Subtle bounding guide box (40% - 80% frame guide)
            val guideRectTop = height * 0.14f
            val guideRectHeight = height * 0.72f
            val guideRectWidth = width * 0.78f
            val guideRectLeft = (width - guideRectWidth) / 2

            drawRoundRect(
                color = if (isBodyInFrame) AccentNeonVolt.copy(alpha = 0.4f) else Color.White.copy(alpha = 0.15f),
                topLeft = Offset(guideRectLeft, guideRectTop),
                size = Size(guideRectWidth, guideRectHeight),
                cornerRadius = CornerRadius(28.dp.toPx(), 28.dp.toPx()),
                style = Stroke(
                    width = 2.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 16f)),
                ),
            )
        }

        // Camera positioning guidance pill
        if (cameraHint.isNotBlank()) {
            Row(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 80.dp, start = 20.dp, end = 20.dp)
                    .clip(RoundedCornerShape(50))
                    .background(BackgroundOnyx.copy(alpha = 0.82f))
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Rounded.Videocam,
                    contentDescription = null,
                    tint = AccentNeonVolt,
                    modifier = Modifier.size(18.dp),
                )
                Spacer(Modifier.size(8.dp))
                Text(
                    text = cameraHint,
                    color = TextPrimaryWhite,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}
