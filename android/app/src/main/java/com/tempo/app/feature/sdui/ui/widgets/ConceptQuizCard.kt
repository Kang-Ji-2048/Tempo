package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.spring
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.material.icons.rounded.Cancel
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Psychology
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.sdui.model.ConceptQuizWidget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.feature.sdui.ui.components.SduiCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SuccessGreen
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

private enum class OptionLook { IDLE, CORRECT, WRONG, DIMMED }

@Composable
fun ConceptQuizCard(
    widget: ConceptQuizWidget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    // Transient UI selection, seeded from server state so it survives feed replacement.
    var selected by rememberSaveable(widget.key) { mutableStateOf(widget.answeredIndex) }
    var answerTick by remember { mutableIntStateOf(0) }
    val shake = remember { Animatable(0f) }
    val pop = remember { Animatable(1f) }
    val haptics = LocalHapticFeedback.current
    val answered = selected
    val isCorrect = answered == widget.correctIndex

    LaunchedEffect(answerTick) {
        if (answerTick == 0) return@LaunchedEffect
        if (isCorrect) {
            pop.animateTo(1.06f, spring(dampingRatio = Spring.DampingRatioMediumBouncy))
            pop.animateTo(1f, spring(dampingRatio = Spring.DampingRatioMediumBouncy))
        } else {
            shake.animateTo(0f, keyframes {
                durationMillis = 420
                -18f at 50
                18f at 110
                -12f at 170
                12f at 230
                -6f at 290
                6f at 350
            })
        }
    }

    SduiCard(eyebrow = "Concept check", icon = Icons.Rounded.Psychology, modifier = modifier) {
        Text(widget.question, style = MaterialTheme.typography.titleLarge)

        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            widget.options.forEachIndexed { index, option ->
                val look = when {
                    answered == null -> OptionLook.IDLE
                    index == widget.correctIndex -> OptionLook.CORRECT
                    index == answered -> OptionLook.WRONG
                    else -> OptionLook.DIMMED
                }
                val animModifier = when {
                    look == OptionLook.CORRECT && index == answered ->
                        Modifier.graphicsLayer { scaleX = pop.value; scaleY = pop.value }
                    look == OptionLook.WRONG -> Modifier.graphicsLayer { translationX = shake.value }
                    else -> Modifier
                }
                QuizOption(
                    letter = ('A' + index).toString(),
                    text = option,
                    look = look,
                    enabled = answered == null,
                    modifier = animModifier,
                    onClick = {
                        selected = index
                        answerTick++
                        haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                        onAction(
                            WidgetAction.QuizAnswered(
                                widgetId = widget.actionId,
                                selectedIndex = index,
                                isCorrect = index == widget.correctIndex,
                            ),
                        )
                    },
                )
            }
        }

        AnimatedVisibility(visible = answered != null, enter = expandVertically() + fadeIn()) {
            QuizVerdict(isCorrect = isCorrect, explanation = widget.explanation)
        }
    }
}

@Composable
private fun QuizOption(
    letter: String,
    text: String,
    look: OptionLook,
    enabled: Boolean,
    modifier: Modifier,
    onClick: () -> Unit,
) {
    val accent = when (look) {
        OptionLook.CORRECT -> SuccessGreen
        OptionLook.WRONG -> ErrorRed
        else -> CardBorderSubtle
    }
    val border by animateColorAsState(accent, label = "optionBorder")
    val fill by animateColorAsState(
        if (look == OptionLook.CORRECT || look == OptionLook.WRONG) accent.copy(alpha = 0.14f) else SurfaceVariantDark,
        label = "optionFill",
    )
    val shape = RoundedCornerShape(18.dp)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .graphicsLayer { alpha = if (look == OptionLook.DIMMED) 0.45f else 1f }
            .clip(shape)
            .background(fill)
            .border(BorderStroke(1.5.dp, border), shape)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(30.dp)
                .clip(CircleShape)
                .background(if (look == OptionLook.IDLE || look == OptionLook.DIMMED) BackgroundOnyx else accent),
            contentAlignment = Alignment.Center,
        ) {
            when (look) {
                OptionLook.CORRECT -> Icon(Icons.Rounded.Check, null, tint = BackgroundOnyx, modifier = Modifier.size(18.dp))
                OptionLook.WRONG -> Icon(Icons.Rounded.Close, null, tint = BackgroundOnyx, modifier = Modifier.size(18.dp))
                else -> Text(letter, color = AccentNeonVolt, fontWeight = FontWeight.Bold, fontSize = 13.sp)
            }
        }
        Spacer(Modifier.size(12.dp))
        Text(text, color = TextPrimaryWhite, fontSize = 15.sp, lineHeight = 21.sp)
    }
}

@Composable
private fun QuizVerdict(isCorrect: Boolean, explanation: String) {
    val tone = if (isCorrect) SuccessGreen else ErrorRed
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(tone.copy(alpha = 0.10f))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                if (isCorrect) Icons.Rounded.CheckCircle else Icons.Rounded.Cancel,
                contentDescription = null,
                tint = tone,
                modifier = Modifier.size(20.dp),
            )
            Spacer(Modifier.size(8.dp))
            Text(
                text = if (isCorrect) "Nailed it!" else "Not quite",
                color = tone,
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp,
            )
        }
        Text(explanation, color = TextSecondarySilver, fontSize = 14.sp, lineHeight = 20.sp)
    }
}
