package com.tempo.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccessTime
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Notifications
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
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
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.feature.schedule.ScheduleViewModel
import com.tempo.app.feature.thea.CourtFinderCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.ErrorRed
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

private val CHANNEL_OPTIONS = listOf(
    "whatsapp" to "WhatsApp",
    "push" to "Push Notification",
    "sms" to "SMS"
)

@Composable
fun ScheduleScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: ScheduleViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    androidx.compose.runtime.LaunchedEffect(Unit) {
        viewModel.loadSchedule()
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        // Header
        Column {
            Text(
                text = "SAINT (THEA) CADENCE",
                style = MaterialTheme.typography.labelLarge,
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Practice Schedule",
                style = MaterialTheme.typography.displayLarge
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Set weekly training slots for automatic priming and reminders",
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondarySilver
            )
        }

        // Active Cadence Summary Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "CURRENT CADENCE",
                        style = MaterialTheme.typography.labelLarge,
                        color = AccentNeonVolt
                    )
                    Switch(
                        checked = uiState.isActive,
                        onCheckedChange = { viewModel.toggleActive(it) },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = BackgroundOnyx,
                            checkedTrackColor = AccentNeonVolt,
                            uncheckedThumbColor = TextMuted,
                            uncheckedTrackColor = SurfaceVariantDark
                        )
                    )
                }
                Spacer(modifier = Modifier.height(8.dp))
                val daysSummary = if (uiState.daysOfWeek.isEmpty()) "No days set" else uiState.daysOfWeek.map { it.take(3) }.joinToString(", ")
                val localFormatted = formatUtcTimeToLocal(uiState.targetTimeUtc)
                Text(
                    text = "$daysSummary @ ${uiState.targetTimeUtc} UTC ($localFormatted)",
                    style = MaterialTheme.typography.titleLarge
                )
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = "${uiState.sport.replaceFirstChar { it.uppercase() }} ${uiState.strokeType.replace('_', ' ')} • ${uiState.durationMinutes} min sessions",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondarySilver
                )
                Spacer(modifier = Modifier.height(12.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Rounded.NotificationsActive,
                        contentDescription = null,
                        tint = AccentNeonVolt,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        text = "Channel: ${uiState.preferredChannel.uppercase()} (${uiState.primingLeadMinutes}m lead)",
                        style = MaterialTheme.typography.bodyMedium,
                        color = AccentNeonVolt
                    )
                }
            }
        }

        // Weekly Day Picker Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.CalendarMonth, null, tint = AccentNeonVolt, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("TRAINING DAYS", style = MaterialTheme.typography.titleMedium)
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    ALL_DAYS.forEach { (fullName, shortLabel) ->
                        val isSelected = uiState.daysOfWeek.contains(fullName)
                        val bg by animateColorAsState(if (isSelected) AccentNeonVolt else SurfaceVariantDark, label = "dayBg")
                        val textColor = if (isSelected) BackgroundOnyx else TextPrimaryWhite
                        val borderColor by animateColorAsState(if (isSelected) AccentNeonVolt else CardBorderSubtle, label = "dayBorder")

                        Box(
                            modifier = Modifier
                                .size(42.dp)
                                .clip(CircleShape)
                                .background(bg)
                                .border(1.dp, borderColor, CircleShape)
                                .clickable { viewModel.toggleDay(fullName) },
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

                // Time Selection
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.AccessTime, null, tint = AccentNeonVolt, modifier = Modifier.size(16.dp))
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
                            val isSelected = time == uiState.targetTimeUtc
                            val bg by animateColorAsState(if (isSelected) AccentNeonVolt else SurfaceVariantDark, label = "timeBg")
                            val textColor = if (isSelected) BackgroundOnyx else TextPrimaryWhite
                            val shape = RoundedCornerShape(12.dp)

                            Box(
                                modifier = Modifier
                                    .clip(shape)
                                    .background(bg)
                                    .border(1.dp, if (isSelected) AccentNeonVolt else CardBorderSubtle, shape)
                                    .clickable { viewModel.setTime(time) }
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

                // Duration Selection
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Timer, null, tint = AccentNeonVolt, modifier = Modifier.size(16.dp))
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
                            val isSelected = duration == uiState.durationMinutes
                            val bg by animateColorAsState(if (isSelected) AccentNeonVolt else SurfaceVariantDark, label = "durBg")
                            val textColor = if (isSelected) BackgroundOnyx else TextPrimaryWhite
                            val shape = RoundedCornerShape(12.dp)

                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(shape)
                                    .background(bg)
                                    .border(1.dp, if (isSelected) AccentNeonVolt else CardBorderSubtle, shape)
                                    .clickable { viewModel.setDuration(duration) }
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

                // Channel Selection
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Notifications, null, tint = AccentNeonVolt, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text(
                            "REMINDER CHANNEL",
                            style = MaterialTheme.typography.labelSmall,
                            color = AccentNeonVolt,
                            letterSpacing = 1.sp
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CHANNEL_OPTIONS.forEach { (channelKey, label) ->
                            val isSelected = channelKey == uiState.preferredChannel
                            val bg by animateColorAsState(if (isSelected) AccentNeonVolt else SurfaceVariantDark, label = "chanBg")
                            val textColor = if (isSelected) BackgroundOnyx else TextPrimaryWhite
                            val shape = RoundedCornerShape(12.dp)

                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(shape)
                                    .background(bg)
                                    .border(1.dp, if (isSelected) AccentNeonVolt else CardBorderSubtle, shape)
                                    .clickable { viewModel.setChannel(channelKey) }
                                    .padding(vertical = 8.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = label,
                                    color = textColor,
                                    fontSize = 12.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium
                                )
                            }
                        }
                    }
                }

                // Save Button & Status Feedback
                Button(
                    onClick = { viewModel.saveSchedule() },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(52.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = AccentNeonVolt),
                    enabled = !uiState.isSaving
                ) {
                    if (uiState.isSaving) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            color = BackgroundOnyx,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (uiState.saveSuccess) {
                                Icon(Icons.Rounded.Check, null, tint = BackgroundOnyx, modifier = Modifier.size(20.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("CADENCE SAVED", color = BackgroundOnyx, fontWeight = FontWeight.Bold)
                            } else {
                                Text("UPDATE CADENCE SCHEDULE", color = BackgroundOnyx, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                AnimatedVisibility(
                    visible = uiState.errorMessage != null,
                    enter = fadeIn(),
                    exit = fadeOut()
                ) {
                    Text(
                        text = uiState.errorMessage ?: "",
                        color = ErrorRed,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }

        // Recent Dispatches Card (Real briefs or empty state)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "RECENT CHECK-IN DISPATCH",
                    style = MaterialTheme.typography.labelLarge,
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(8.dp))
                if (!uiState.recentBrief.isNullOrBlank()) {
                    Text(
                        text = "\"${uiState.recentBrief}\"",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextPrimaryWhite
                    )
                } else {
                    Text(
                        text = "No recent check-in dispatches sent yet. Cadence reminders trigger ${uiState.primingLeadMinutes} mins before scheduled sessions.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
                    )
                }
            }
        }

        // Court finder ($nearSphere + forecast) and one-tap hand-off to Thea on WhatsApp.
        CourtFinderCard()
    }
}

private fun formatUtcTimeToLocal(timeUtc: String): String {
    return try {
        val parts = timeUtc.split(":")
        val hour = parts[0].toInt()
        val minute = parts[1].toInt()
        val cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC")).apply {
            set(java.util.Calendar.HOUR_OF_DAY, hour)
            set(java.util.Calendar.MINUTE, minute)
        }
        val localTz = java.util.TimeZone.getDefault()
        val sdf = java.text.SimpleDateFormat("h:mm a (zzz)", java.util.Locale.getDefault()).apply {
            timeZone = localTz
        }
        sdf.format(cal.time)
    } catch (_: Exception) {
        "$timeUtc UTC"
    }
}

