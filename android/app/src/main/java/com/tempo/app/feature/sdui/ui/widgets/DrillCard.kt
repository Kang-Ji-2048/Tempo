package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.RecordVoiceOver
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.ripple
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.sdui.model.DrillCardWidget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.feature.sdui.ui.components.SduiCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun DrillCard(
    widget: DrillCardWidget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    var reps by rememberSaveable(widget.key) { mutableIntStateOf(0) }
    var logged by rememberSaveable(widget.key) { mutableStateOf(false) }
    val haptics = LocalHapticFeedback.current
    val target = widget.targetReps.coerceAtLeast(1)
    val hitTarget = reps >= target

    val increment = {
        if (!logged) {
            reps++
            haptics.performHapticFeedback(
                if (reps == target) HapticFeedbackType.LongPress else HapticFeedbackType.TextHandleMove,
            )
        }
    }

    SduiCard(eyebrow = "Prescribed drill", icon = Icons.Rounded.FitnessCenter, modifier = modifier, highlighted = hitTarget) {
        Text(widget.title, style = MaterialTheme.typography.titleLarge)
        Text(widget.instruction, style = MaterialTheme.typography.bodyMedium)
        FocusCue(widget.focusCue)

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            StepButton(Icons.Rounded.Remove, "Remove rep", enabled = reps > 0 && !logged) { reps-- }
            RepRing(reps = reps, target = target, onTap = increment)
            StepButton(Icons.Rounded.Add, "Add rep", enabled = !logged, primary = true, onClick = increment)
        }

        Button(
            onClick = {
                logged = true
                onAction(WidgetAction.DrillCompleted(widgetId = widget.id, repsCompleted = reps))
            },
            enabled = reps > 0 && !logged,
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = AccentNeonVolt,
                contentColor = BackgroundOnyx,
                disabledContainerColor = SurfaceVariantDark,
                disabledContentColor = TextMuted,
            ),
        ) {
            if (logged) {
                Icon(Icons.Rounded.CheckCircle, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.size(8.dp))
            }
            Text(
                text = when {
                    logged -> "Logged $reps reps"
                    hitTarget -> "Complete drill"
                    reps == 0 -> "Tap the ring to count reps"
                    else -> "Log $reps of $target reps"
                },
                fontWeight = FontWeight.Bold,
                fontSize = 15.sp,
            )
        }
    }
}

@Composable
private fun FocusCue(cue: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(AccentNeonVolt.copy(alpha = 0.08f))
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.RecordVoiceOver, null, tint = AccentNeonVolt, modifier = Modifier.size(18.dp))
        Spacer(Modifier.size(10.dp))
        Text(
            text = "“$cue”",
            color = TextPrimaryWhite,
            fontStyle = FontStyle.Italic,
            fontWeight = FontWeight.Medium,
            fontSize = 15.sp,
        )
    }
}

@Composable
private fun RepRing(reps: Int, target: Int, onTap: () -> Unit) {
    val progress by animateFloatAsState(
        targetValue = (reps / target.toFloat()).coerceAtMost(1f),
        animationSpec = spring(),
        label = "repProgress",
    )
    Box(
        modifier = Modifier
            .size(140.dp)
            .clip(CircleShape)
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = ripple(color = AccentNeonVolt),
                onClick = onTap,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(128.dp)) {
            val stroke = 12.dp.toPx()
            drawArc(SurfaceVariantDark, 0f, 360f, false, style = Stroke(stroke))
            drawArc(
                color = AccentNeonVolt,
                startAngle = -90f,
                sweepAngle = 360f * progress,
                useCenter = false,
                style = Stroke(stroke, cap = StrokeCap.Round),
            )
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            AnimatedContent(
                targetState = reps,
                transitionSpec = {
                    val up = targetState > initialState
                    (slideInVertically { if (up) it else -it } + fadeIn()) togetherWith
                        (slideOutVertically { if (up) -it else it } + fadeOut())
                },
                label = "repCount",
            ) { count ->
                Text(
                    text = "$count",
                    color = if (count >= target) AccentNeonVolt else TextPrimaryWhite,
                    fontSize = 40.sp,
                    fontWeight = FontWeight.Black,
                )
            }
            Text("of $target reps", color = TextSecondarySilver, fontSize = 12.sp)
        }
    }
}

@Composable
private fun StepButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    description: String,
    enabled: Boolean,
    primary: Boolean = false,
    onClick: () -> Unit,
) {
    FilledIconButton(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.size(52.dp),
        colors = IconButtonDefaults.filledIconButtonColors(
            containerColor = if (primary) AccentNeonVolt else SurfaceVariantDark,
            contentColor = if (primary) BackgroundOnyx else TextPrimaryWhite,
            disabledContainerColor = SurfaceVariantDark.copy(alpha = 0.5f),
            disabledContentColor = TextMuted,
        ),
    ) {
        Icon(icon, contentDescription = description)
    }
}
