package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccessTime
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
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
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

private val ALL_DAYS = listOf(
    "Monday" to "Mon",
    "Tuesday" to "Tue",
    "Wednesday" to "Wed",
    "Thursday" to "Thu",
    "Friday" to "Fri",
    "Saturday" to "Sat",
    "Sunday" to "Sun"
)

private val TIME_OPTIONS = listOf(
    "07:00", "09:00", "12:00", "17:00", "18:00", "19:30", "20:00"
)

private val DURATION_OPTIONS = listOf(30, 45, 60, 90)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CheckInScheduleCard(
    widget: CheckInScheduleWidget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    var pickedSlot by rememberSaveable(widget.key, widget.selectedSlotId) {
        mutableStateOf(widget.selectedSlotId)
    }
    var selectedDays by rememberSaveable(widget.key, widget.daysOfWeek) {
        mutableStateOf(widget.daysOfWeek.toSet())
    }
    var selectedTime by rememberSaveable(widget.key, widget.targetTimeUtc) {
        mutableStateOf(widget.targetTimeUtc)
    }
    var selectedDuration by rememberSaveable(widget.key, widget.durationMinutes) {
        mutableIntStateOf(widget.durationMinutes)
    }
    var preferredChannel by rememberSaveable(widget.key, widget.preferredChannel) {
        mutableStateOf(widget.preferredChannel)
    }

    SduiCard(eyebrow = "Cadence Schedule", icon = Icons.Rounded.CalendarMonth, modifier = modifier) {
        Text(widget.title, style = MaterialTheme.typography.titleLarge)
        if (widget.subtitle.isNotBlank()) {
            Text(widget.subtitle, style = MaterialTheme.typography.bodyMedium, color = TextSecondarySilver)
        }

        // 1. If predefined slots exist, display slot picker row
        if (widget.slots.isNotEmpty()) {
            Text(
                "RECOMMENDED SLOTS",
                style = MaterialTheme.typography.labelSmall,
                color = AccentNeonVolt,
                letterSpacing = 1.sp
            )
            LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                items(widget.slots, key = { it.slotId }) { slot ->
                    SlotTile(slot = slot, selected = slot.slotId == pickedSlot) {
                        pickedSlot = slot.slotId
                        onAction(WidgetAction.SlotPicked(widgetId = widget.id, slotId = slot.slotId))
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        }

        // 2. Weekly Mon–Sun Day Chips Picker
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "TRAINING DAYS",
                style = MaterialTheme.typography.labelSmall,
                color = AccentNeonVolt,
                letterSpacing = 1.sp
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                ALL_DAYS.forEach { (fullName, shortLabel) ->
                    val isSelected = selectedDays.contains(fullName)
                    val bg by animateColorAsState(if (isSelected) AccentNeonVolt else SurfaceVariantDark, label = "dayBg")
                    val textColor = if (isSelected) BackgroundOnyx else TextPrimaryWhite
                    val borderColor by animateColorAsState(if (isSelected) AccentNeonVolt else CardBorderSubtle, label = "dayBorder")

                    Box(
                        modifier = Modifier
                            .size(42.dp)
                            .clip(CircleShape)
                            .background(bg)
                            .border(1.dp, borderColor, CircleShape)
                            .clickable {
                                val newSet = selectedDays.toMutableSet()
                                if (isSelected) {
                                    if (newSet.size > 1) newSet.remove(fullName)
                                } else {
                                    newSet.add(fullName)
                                }
                                selectedDays = newSet
                                onAction(
                                    WidgetAction.ScheduleChanged(
                                        widgetId = widget.id,
                                        daysOfWeek = newSet.toList(),
                                        targetTimeUtc = selectedTime,
                                        durationMinutes = selectedDuration,
                                        primingLeadMinutes = widget.primingLeadMinutes,
                                        preferredChannel = preferredChannel
                                    )
                                )
                            },
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = shortLabel,
                            color = textColor,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }

        // 3. Time Picker Selector
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.AccessTime, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(
                    "TARGET TIME (UTC)",
                    style = MaterialTheme.typography.labelSmall,
                    color = AccentNeonVolt,
                    letterSpacing = 1.sp
                )
            }
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(TIME_OPTIONS) { time ->
                    val isSelected = time == selectedTime
                    val bg by animateColorAsState(if (isSelected) AccentNeonVolt else SurfaceVariantDark, label = "timeBg")
                    val textColor = if (isSelected) BackgroundOnyx else TextPrimaryWhite
                    val shape = RoundedCornerShape(12.dp)

                    Box(
                        modifier = Modifier
                            .clip(shape)
                            .background(bg)
                            .border(1.dp, if (isSelected) AccentNeonVolt else CardBorderSubtle, shape)
                            .clickable {
                                selectedTime = time
                                onAction(
                                    WidgetAction.ScheduleChanged(
                                        widgetId = widget.id,
                                        daysOfWeek = selectedDays.toList(),
                                        targetTimeUtc = time,
                                        durationMinutes = selectedDuration,
                                        primingLeadMinutes = widget.primingLeadMinutes,
                                        preferredChannel = preferredChannel
                                    )
                                )
                            }
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = time,
                            color = textColor,
                            fontSize = 13.sp,
                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium
                        )
                    }
                }
            }
        }

        // 4. Session Duration Chips
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.Timer, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(
                    "SESSION DURATION",
                    style = MaterialTheme.typography.labelSmall,
                    color = AccentNeonVolt,
                    letterSpacing = 1.sp
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DURATION_OPTIONS.forEach { duration ->
                    val isSelected = duration == selectedDuration
                    val bg by animateColorAsState(if (isSelected) AccentNeonVolt else SurfaceVariantDark, label = "durBg")
                    val textColor = if (isSelected) BackgroundOnyx else TextPrimaryWhite
                    val shape = RoundedCornerShape(12.dp)

                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(shape)
                            .background(bg)
                            .border(1.dp, if (isSelected) AccentNeonVolt else CardBorderSubtle, shape)
                            .clickable {
                                selectedDuration = duration
                                onAction(
                                    WidgetAction.ScheduleChanged(
                                        widgetId = widget.id,
                                        daysOfWeek = selectedDays.toList(),
                                        targetTimeUtc = selectedTime,
                                        durationMinutes = duration,
                                        primingLeadMinutes = widget.primingLeadMinutes,
                                        preferredChannel = preferredChannel
                                    )
                                )
                            }
                            .padding(vertical = 8.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "${duration}m",
                            color = textColor,
                            fontSize = 13.sp,
                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium
                        )
                    }
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
