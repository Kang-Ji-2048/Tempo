package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.sdui.model.ChoiceOption
import com.tempo.app.feature.sdui.model.ChoiceWidget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.feature.sdui.ui.components.SduiCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun ChoiceCard(
    widget: ChoiceWidget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    var selection by remember(widget.key, widget.selectedOptionIds) { mutableStateOf(widget.selectedOptionIds.toSet()) }
    val submitted = widget.selectedOptionIds.isNotEmpty()

    SduiCard(eyebrow = "Your call", icon = Icons.Rounded.Tune, modifier = modifier) {
        Text(widget.title, style = MaterialTheme.typography.titleLarge)
        if (widget.subtitle.isNotBlank()) Text(widget.subtitle, style = MaterialTheme.typography.bodyMedium)

        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            widget.options.forEach { option ->
                ChoiceRow(option = option, selected = option.id in selection, multi = widget.multiSelect) {
                    if (widget.multiSelect) {
                        selection = if (option.id in selection) selection - option.id else selection + option.id
                    } else {
                        selection = setOf(option.id)
                        onAction(WidgetAction.ChoiceSelected(widgetId = widget.id, optionIds = listOf(option.id)))
                    }
                }
            }
        }

        if (widget.multiSelect) {
            Button(
                onClick = { onAction(WidgetAction.ChoiceSelected(widgetId = widget.id, optionIds = selection.toList())) },
                enabled = selection.isNotEmpty() && selection != widget.selectedOptionIds.toSet(),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(16.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = AccentNeonVolt,
                    contentColor = BackgroundOnyx,
                    disabledContainerColor = SurfaceVariantDark,
                    disabledContentColor = TextMuted,
                ),
            ) {
                Text(
                    text = if (submitted && selection == widget.selectedOptionIds.toSet()) "Saved" else "Confirm (${selection.size})",
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun ChoiceRow(option: ChoiceOption, selected: Boolean, multi: Boolean, onClick: () -> Unit) {
    val border by animateColorAsState(if (selected) AccentNeonVolt else CardBorderSubtle, label = "choiceBorder")
    val fill by animateColorAsState(
        if (selected) AccentNeonVolt.copy(alpha = 0.10f) else SurfaceVariantDark,
        label = "choiceFill",
    )
    val shape = RoundedCornerShape(18.dp)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(fill)
            .border(1.5.dp, border, shape)
            .clickable(onClick = onClick)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(44.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(BackgroundOnyx),
            contentAlignment = Alignment.Center,
        ) {
            Text(option.emoji ?: option.label.take(1), fontSize = 22.sp, color = AccentNeonVolt)
        }
        Spacer(Modifier.size(12.dp))
        Column(Modifier.weight(1f)) {
            Text(option.label, color = TextPrimaryWhite, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            option.description?.let { Text(it, color = TextSecondarySilver, fontSize = 13.sp) }
        }
        Indicator(selected = selected, multi = multi)
    }
}

@Composable
private fun Indicator(selected: Boolean, multi: Boolean) {
    val shape = if (multi) RoundedCornerShape(7.dp) else CircleShape
    val fill by animateColorAsState(if (selected) AccentNeonVolt else BackgroundOnyx, label = "indicator")
    Box(
        modifier = Modifier
            .size(24.dp)
            .clip(shape)
            .background(fill)
            .border(1.5.dp, if (selected) AccentNeonVolt else CardBorderSubtle, shape),
        contentAlignment = Alignment.Center,
    ) {
        if (selected) Icon(Icons.Rounded.Check, null, tint = BackgroundOnyx, modifier = Modifier.size(16.dp))
    }
}
