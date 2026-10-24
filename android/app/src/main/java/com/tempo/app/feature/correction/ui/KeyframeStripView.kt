package com.tempo.app.feature.correction.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.correction.model.KeyframeComparison
import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import com.tempo.app.ui.theme.WarningAmber

@Composable
fun KeyframeStripView(
    comparisons: List<KeyframeComparison>,
    onPhaseClicked: (KineticPhaseUiModel) -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier.fillMaxWidth()) {
        // Section Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = "KINETIC PHASE STRIP",
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.2.sp,
                    color = AccentNeonVolt
                )
                Text(
                    text = "Athlete vs. Pro Reference (Axelsen)",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimaryWhite
                )
            }

            // Dual Skeleton Legend
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(ColorAthleteSkeleton)
                )
                Text(text = "You", fontSize = 11.sp, color = TextSecondarySilver)

                Spacer(Modifier.width(4.dp))

                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(ColorReferenceSkeleton)
                )
                Text(text = "Pro", fontSize = 11.sp, color = TextSecondarySilver)
            }
        }

        Spacer(Modifier.height(12.dp))

        // Horizontally scrollable row of 4 phase cards
        LazyRow(
            contentPadding = PaddingValues(horizontal = 2.dp),
            horizontalArrangement = Arrangement.spacedBy(14.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            items(comparisons) { item ->
                PhaseKeyframeCard(
                    comparison = item,
                    onClick = { onPhaseClicked(item.phase) }
                )
            }
        }
    }
}

@Composable
fun PhaseKeyframeCard(
    comparison: KeyframeComparison,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val phase = comparison.phase
    val score = phase.formAccuracyScore
    val isImpact = phase.phaseName.startsWith("Imp", ignoreCase = true)

    val scoreColor = when {
        score >= 88 -> AccentNeonVolt
        score >= 75 -> WarningAmber
        else -> ErrorRed
    }

    Card(
        modifier = modifier
            .width(280.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(
            width = if (isImpact) 1.5.dp else 1.dp,
            color = if (isImpact) WarningAmber.copy(alpha = 0.8f) else CardBorderSubtle
        )
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            // Card Header: Phase Name & Form Accuracy Score
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = phase.phaseName,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimaryWhite
                    )
                    Text(
                        text = String.format("%.2fs", phase.timestampMs / 1000f),
                        fontSize = 12.sp,
                        color = TextMuted
                    )
                }

                // Form Accuracy Score Pill
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(scoreColor.copy(alpha = 0.16f))
                        .border(1.dp, scoreColor.copy(alpha = 0.6f), RoundedCornerShape(50))
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = "$score% Match",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = scoreColor
                    )
                }
            }

            Spacer(Modifier.height(10.dp))

            // Thumbnail Frame with Dual Skeleton Overlay + Angle Deviation Badges
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(4f / 5f)
                    .clip(RoundedCornerShape(14.dp))
                    .background(BackgroundOnyx)
            ) {
                // Background video frame bitmap
                if (comparison.frameBitmap != null) {
                    Image(
                        bitmap = comparison.frameBitmap.asImageBitmap(),
                        contentDescription = "Keyframe ${phase.phaseName}",
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Crop
                    )
                } else {
                    // Fallback subtle gradient if bitmap not rendered
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(SurfaceVariantDark)
                    )
                }

                // Dual Skeleton Overlay: Athlete (Neon Volt) + Reference (Electric Cyan)
                SkeletonCanvasOverlay(
                    athleteLandmarks = comparison.athleteLandmarks,
                    referenceLandmarks = comparison.referenceLandmarks,
                    deviations = comparison.deviations,
                    modifier = Modifier.fillMaxSize()
                )

                // High-visibility deviation alert badge in bottom if present
                if (comparison.deviations.isNotEmpty()) {
                    val primaryDev = comparison.deviations.first()
                    Box(
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .fillMaxWidth()
                            .background(BackgroundOnyx.copy(alpha = 0.88f))
                            .padding(horizontal = 10.dp, vertical = 6.dp)
                    ) {
                        Text(
                            text = "⚠ ${primaryDev.jointName}: ${String.format("%.1f°", primaryDev.athleteDeg)} vs ${String.format("%.1f°", primaryDev.referenceDeg)} ref",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = WarningAmber
                        )
                    }
                }
            }

            Spacer(Modifier.height(10.dp))

            // Granular observation excerpt
            Text(
                text = phase.observation,
                fontSize = 12.sp,
                lineHeight = 16.sp,
                color = TextSecondarySilver,
                maxLines = 3
            )
        }
    }
}
