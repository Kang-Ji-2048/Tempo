package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.sdui.model.CheckInScheduleWidget
import com.tempo.app.feature.sdui.model.ScheduleSlot
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.feature.sdui.ui.components.SduiCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun CheckInScheduleCard(
    widget: CheckInScheduleWidget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    var picked by rememberSaveable(widget.key, widget.selectedSlotId) { mutableStateOf(widget.selectedSlotId) }

    SduiCard(eyebrow = "Check-in", icon = Icons.Rounded.CalendarMonth, modifier = modifier) {
        Text(widget.title, style = MaterialTheme.typography.titleLarge)
        if (widget.subtitle.isNotBlank()) Text(widget.subtitle, style = MaterialTheme.typography.bodyMedium)

        LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            items(widget.slots, key = { it.slotId }) { slot ->
                SlotTile(slot = slot, selected = slot.slotId == picked) {
                    picked = slot.slotId
                    onAction(WidgetAction.SlotPicked(widgetId = widget.id, slotId = slot.slotId))
                }
            }
        }

        widget.reminderNote?.let { note ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.NotificationsActive, null, tint = TextSecondarySilver, modifier = Modifier.size(16.dp))
                Spacer(Modifier.size(8.dp))
                Text(note, color = TextSecondarySilver, fontSize = 13.sp)
            }
        }
    }
}

@Composable
private fun SlotTile(slot: ScheduleSlot, selected: Boolean, onClick: () -> Unit) {
    val fill by animateColorAsState(if (selected) AccentNeonVolt else SurfaceVariantDark, label = "slotFill")
    val border by animateColorAsState(
        when {
            selected -> AccentNeonVolt
            slot.recommended -> AccentNeonVolt.copy(alpha = 0.5f)
            else -> CardBorderSubtle
        },
        label = "slotBorder",
    )
    val scale by animateFloatAsState(if (selected) 1.04f else 1f, label = "slotScale")
    val shape = RoundedCornerShape(20.dp)
    val ink = if (selected) BackgroundOnyx else TextPrimaryWhite

    Box(contentAlignment = Alignment.TopCenter) {
        Column(
            modifier = Modifier
                .padding(top = 8.dp)
                .width(92.dp)
                .graphicsLayer { scaleX = scale; scaleY = scale }
                .clip(shape)
                .background(fill)
                .border(1.5.dp, border, shape)
                .clickable(onClick = onClick)
                .padding(vertical = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                slot.dayLabel,
                color = if (selected) BackgroundOnyx else TextSecondarySilver,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.2.sp,
            )
            Text(slot.timeLabel, color = ink, fontSize = 20.sp, fontWeight = FontWeight.Black)
        }
        if (slot.recommended) {
            Text(
                text = "BEST",
                color = BackgroundOnyx,
                fontSize = 9.sp,
                fontWeight = FontWeight.Black,
                letterSpacing = 1.sp,
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(AccentNeonVolt)
                    .padding(horizontal = 8.dp, vertical = 2.dp),
            )
        }
    }
}
