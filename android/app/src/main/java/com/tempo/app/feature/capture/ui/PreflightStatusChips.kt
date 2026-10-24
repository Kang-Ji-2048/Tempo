package com.tempo.app.feature.capture.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material3.Icon
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
import com.tempo.app.feature.capture.model.PreflightCheck
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SuccessGreen
import com.tempo.app.ui.theme.TextPrimaryWhite

@Composable
fun PreflightStatusChips(
    check: PreflightCheck,
    fpsBadge: String,
    modifier: Modifier = Modifier,
    onDebugSimulatePass: (() -> Unit)? = null,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Status Chips row
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 1. Body Visible Chip
            StatusChip(
                label = if (check.bodyVisible) "Body Visible" else "Body Missing",
                passed = check.bodyVisible,
            )

            // 2. Lighting Chip
            StatusChip(
                label = if (check.lightingOk) "Lighting OK" else "Too Dark",
                passed = check.lightingOk,
            )

            // 3. Distance Chip
            StatusChip(
                label = if (check.distanceOk) "Distance OK" else "Distance",
                passed = check.distanceOk,
            )

            // 4. Actual FPS Badge
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(BackgroundOnyx.copy(alpha = 0.85f))
                    .border(1.dp, AccentNeonVolt.copy(alpha = 0.45f), RoundedCornerShape(50))
                    .clickable(enabled = onDebugSimulatePass != null) { onDebugSimulatePass?.invoke() }
                    .padding(horizontal = 10.dp, vertical = 6.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = fpsBadge,
                    color = AccentNeonVolt,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.8.sp,
                )
            }
        }

        // Plain language hint banner when not ready
        AnimatedVisibility(
            visible = !check.isReady && check.failureHint != null,
            enter = fadeIn(),
            exit = fadeOut(),
        ) {
            Row(
                modifier = Modifier
                    .clip(RoundedCornerShape(16.dp))
                    .background(BackgroundOnyx.copy(alpha = 0.90f))
                    .border(1.dp, ErrorRed.copy(alpha = 0.4f), RoundedCornerShape(16.dp))
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Rounded.Info,
                    contentDescription = null,
                    tint = ErrorRed,
                    modifier = Modifier.size(16.dp),
                )
                Spacer(Modifier.size(8.dp))
                Text(
                    text = check.failureHint ?: "",
                    color = TextPrimaryWhite,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}

@Composable
private fun StatusChip(
    label: String,
    passed: Boolean,
) {
    val tone by animateColorAsState(
        targetValue = if (passed) SuccessGreen else ErrorRed,
        label = "chipColor",
    )

    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(BackgroundOnyx.copy(alpha = 0.85f))
            .border(1.dp, tone.copy(alpha = 0.5f), RoundedCornerShape(50))
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(14.dp)
                .clip(CircleShape)
                .background(tone),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = if (passed) Icons.Rounded.Check else Icons.Rounded.Close,
                contentDescription = null,
                tint = BackgroundOnyx,
                modifier = Modifier.size(10.dp),
            )
        }
        Spacer(Modifier.size(6.dp))
        Text(
            text = label,
            color = TextPrimaryWhite,
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
