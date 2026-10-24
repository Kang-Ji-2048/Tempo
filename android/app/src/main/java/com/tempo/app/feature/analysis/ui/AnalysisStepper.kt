package com.tempo.app.feature.analysis.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.analysis.AnalysisStep
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite

@Composable
fun AnalysisStepper(
    currentStep: AnalysisStep,
    statusCopy: String,
    modifier: Modifier = Modifier
) {
    val step1State = when (currentStep) {
        AnalysisStep.UPLOADING, AnalysisStep.PENDING -> StepItemState.ACTIVE
        AnalysisStep.ANALYZING, AnalysisStep.COMPLETED -> StepItemState.COMPLETED
        AnalysisStep.FAILED -> StepItemState.ERROR
    }

    val step2State = when (currentStep) {
        AnalysisStep.UPLOADING, AnalysisStep.PENDING -> StepItemState.UPCOMING
        AnalysisStep.ANALYZING -> StepItemState.ACTIVE
        AnalysisStep.COMPLETED -> StepItemState.COMPLETED
        AnalysisStep.FAILED -> StepItemState.ERROR
    }

    val step3State = when (currentStep) {
        AnalysisStep.COMPLETED -> StepItemState.COMPLETED
        AnalysisStep.FAILED -> StepItemState.ERROR
        else -> StepItemState.UPCOMING
    }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(SurfaceCharcoal)
            .border(1.dp, CardBorderSubtle, RoundedCornerShape(20.dp))
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Status copy badge banner
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(
                    if (currentStep == AnalysisStep.FAILED) ErrorRed.copy(alpha = 0.12f)
                    else AccentNeonVolt.copy(alpha = 0.12f)
                )
                .padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (currentStep == AnalysisStep.FAILED) {
                Icon(
                    imageVector = Icons.Rounded.Close,
                    contentDescription = null,
                    tint = ErrorRed,
                    modifier = Modifier.size(18.dp)
                )
            } else if (currentStep != AnalysisStep.COMPLETED) {
                CircularProgressIndicator(
                    strokeWidth = 2.dp,
                    color = AccentNeonVolt,
                    modifier = Modifier.size(16.dp)
                )
            } else {
                Icon(
                    imageVector = Icons.Rounded.Check,
                    contentDescription = null,
                    tint = AccentNeonVolt,
                    modifier = Modifier.size(18.dp)
                )
            }
            Spacer(Modifier.width(10.dp))
            Text(
                text = statusCopy,
                style = MaterialTheme.typography.bodyMedium.copy(
                    fontWeight = FontWeight.SemiBold,
                    color = if (currentStep == AnalysisStep.FAILED) ErrorRed else AccentNeonVolt
                )
            )
        }

        // Stepper Visual Row
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            StepNode(stepNumber = 1, label = "Swings", state = step1State, modifier = Modifier.weight(1f))
            StepConnector(isCompleted = step2State != StepItemState.UPCOMING)
            StepNode(stepNumber = 2, label = "Technique", state = step2State, modifier = Modifier.weight(1f))
            StepConnector(isCompleted = step3State == StepItemState.COMPLETED)
            StepNode(stepNumber = 3, label = "Debrief", state = step3State, modifier = Modifier.weight(1f))
        }
    }
}

enum class StepItemState {
    UPCOMING, ACTIVE, COMPLETED, ERROR
}

@Composable
private fun StepNode(
    stepNumber: Int,
    label: String,
    state: StepItemState,
    modifier: Modifier = Modifier
) {
    val bgColor by animateColorAsState(
        targetValue = when (state) {
            StepItemState.COMPLETED -> AccentNeonVolt
            StepItemState.ACTIVE -> AccentNeonVolt.copy(alpha = 0.18f)
            StepItemState.ERROR -> ErrorRed.copy(alpha = 0.18f)
            StepItemState.UPCOMING -> SurfaceVariantDark
        },
        label = "bgColor"
    )

    val borderColor by animateColorAsState(
        targetValue = when (state) {
            StepItemState.COMPLETED, StepItemState.ACTIVE -> AccentNeonVolt
            StepItemState.ERROR -> ErrorRed
            StepItemState.UPCOMING -> CardBorderSubtle
        },
        label = "borderColor"
    )

    val contentColor = when (state) {
        StepItemState.COMPLETED -> BackgroundOnyx
        StepItemState.ACTIVE -> AccentNeonVolt
        StepItemState.ERROR -> ErrorRed
        StepItemState.UPCOMING -> TextMuted
    }

    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(bgColor)
                .border(2.dp, borderColor, CircleShape),
            contentAlignment = Alignment.Center
        ) {
            when (state) {
                StepItemState.COMPLETED -> {
                    Icon(
                        imageVector = Icons.Rounded.Check,
                        contentDescription = null,
                        tint = BackgroundOnyx,
                        modifier = Modifier.size(18.dp)
                    )
                }
                StepItemState.ACTIVE -> {
                    Text(
                        text = "$stepNumber",
                        fontWeight = FontWeight.Bold,
                        color = contentColor,
                        fontSize = 14.sp
                    )
                }
                StepItemState.ERROR -> {
                    Icon(
                        imageVector = Icons.Rounded.Close,
                        contentDescription = null,
                        tint = ErrorRed,
                        modifier = Modifier.size(18.dp)
                    )
                }
                StepItemState.UPCOMING -> {
                    Text(
                        text = "$stepNumber",
                        fontWeight = FontWeight.SemiBold,
                        color = TextMuted,
                        fontSize = 13.sp
                    )
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(
            text = label,
            fontSize = 12.sp,
            fontWeight = if (state == StepItemState.ACTIVE) FontWeight.Bold else FontWeight.Medium,
            color = if (state == StepItemState.UPCOMING) TextMuted else TextPrimaryWhite
        )
    }
}

@Composable
private fun StepConnector(isCompleted: Boolean) {
    val color by animateColorAsState(
        targetValue = if (isCompleted) AccentNeonVolt else CardBorderSubtle,
        label = "connectorColor"
    )
    Box(
        modifier = Modifier
            .width(28.dp)
            .height(2.dp)
            .background(color)
    )
}
