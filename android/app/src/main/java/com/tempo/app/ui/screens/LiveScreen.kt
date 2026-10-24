package com.tempo.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.rounded.Block
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Headphones
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
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
import com.tempo.app.feature.live.LiveViewModel
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import java.util.Locale

@Composable
fun LiveScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: LiveViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            // Screen Header
            Column {
                Text(
                    text = "REAL-TIME EDGE STREAM",
                    style = MaterialTheme.typography.labelSmall.copy(
                        letterSpacing = 1.2.sp,
                        fontWeight = FontWeight.Bold
                    ),
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Live Earbud Cueing",
                    style = MaterialTheme.typography.displayMedium.copy(fontWeight = FontWeight.Black),
                    color = TextPrimaryWhite
                )
            }

            // Real-Time Telemetry & WebSocket HUD Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                border = BorderStroke(1.dp, CardBorderSubtle)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(10.dp)
                                    .clip(CircleShape)
                                    .background(Color.Gray)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = "Live coaching: not connected",
                                style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold),
                                color = TextMuted
                            )
                        }

                        // Earbud Audio Routing Pill
                        Surface(
                            shape = RoundedCornerShape(10.dp),
                            color = SurfaceVariantDark,
                            border = BorderStroke(1.dp, CardBorderSubtle)
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Rounded.Headphones,
                                    contentDescription = null,
                                    tint = AccentNeonVolt,
                                    modifier = Modifier.size(13.dp)
                                )
                                Spacer(Modifier.width(4.dp))
                                Text(
                                    text = "Earbuds (Media/Speech)",
                                    style = MaterialTheme.typography.labelSmall.copy(fontSize = 11.sp),
                                    color = TextSecondarySilver
                                )
                            }
                        }
                    }

                    // Biometrics readout row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text(text = "LIVE STREAM", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                            Text(
                                text = "Offline (not connected)",
                                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                                color = TextSecondarySilver
                            )
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text(text = "HEART RATE", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                            Text(
                                text = "Heart rate: no sensor",
                                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                                color = TextSecondarySilver
                            )
                        }
                    }

                    // Active Coaching Cue Box
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(16.dp))
                            .background(BackgroundOnyx)
                            .border(1.dp, AccentNeonVolt.copy(alpha = 0.3f), RoundedCornerShape(16.dp))
                            .padding(16.dp)
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(
                                text = "ACTIVE COACHING CUE",
                                style = MaterialTheme.typography.labelSmall.copy(
                                    letterSpacing = 1.sp,
                                    fontWeight = FontWeight.Bold
                                ),
                                color = AccentNeonVolt
                            )
                            Text(
                                text = "\"${uiState.activeCueText}\"",
                                style = MaterialTheme.typography.titleMedium.copy(
                                    fontWeight = FontWeight.SemiBold,
                                    lineHeight = 22.sp
                                ),
                                color = TextPrimaryWhite
                            )
                        }
                    }
                }
            }

            // Cue Rate Limiter / Cooldown Monitor Card (15-second gap enforcement)
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                border = BorderStroke(
                    1.dp,
                    if (uiState.cooldownRemainingMs > 0) Color(0xFFFFB300).copy(alpha = 0.5f) else CardBorderSubtle
                )
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Rounded.Timer,
                                contentDescription = null,
                                tint = if (uiState.cooldownRemainingMs > 0) Color(0xFFFFB300) else AccentNeonVolt,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = "15-SECOND RATE LIMIT MONITOR",
                                style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                                color = TextMuted
                            )
                        }

                        // Countdown Status Pill
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = if (uiState.cooldownRemainingMs > 0) Color(0xFF332600) else AccentNeonVolt.copy(alpha = 0.15f),
                            border = BorderStroke(
                                1.dp,
                                if (uiState.cooldownRemainingMs > 0) Color(0xFFFFB300) else AccentNeonVolt
                            )
                        ) {
                            Text(
                                text = if (uiState.cooldownRemainingMs > 0) {
                                    val secs = String.format(Locale.US, "%.1fs Cooldown", uiState.cooldownRemainingMs / 1000f)
                                    "⏳ $secs"
                                } else {
                                    "✓ Ready (15s Elapsed)"
                                },
                                style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                                color = if (uiState.cooldownRemainingMs > 0) Color(0xFFFFB300) else AccentNeonVolt,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                            )
                        }
                    }

                    // Stats row: Played vs Suppressed
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Cues Delivered: ${uiState.totalCuesPlayed}",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextSecondarySilver
                        )
                        Text(
                            text = "Suppressed (<15s): ${uiState.totalCuesSuppressed}",
                            style = MaterialTheme.typography.bodySmall.copy(
                                fontWeight = if (uiState.totalCuesSuppressed > 0) FontWeight.Bold else FontWeight.Normal
                            ),
                            color = if (uiState.totalCuesSuppressed > 0) Color(0xFFFFB300) else TextMuted
                        )
                    }

                    // Event Log Banner (Shows last played or suppressed event)
                    if (uiState.lastEventLog != null) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .background(
                                    if (uiState.isSuppressedLastAttempt) {
                                        Color(0xFF3A1818)
                                    } else {
                                        AccentNeonVolt.copy(alpha = 0.12f)
                                    }
                                )
                                .border(
                                    1.dp,
                                    if (uiState.isSuppressedLastAttempt) ErrorRed else AccentNeonVolt.copy(alpha = 0.4f),
                                    RoundedCornerShape(12.dp)
                                )
                                .padding(12.dp)
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = if (uiState.isSuppressedLastAttempt) Icons.Rounded.Block else Icons.Rounded.CheckCircle,
                                    contentDescription = null,
                                    tint = if (uiState.isSuppressedLastAttempt) ErrorRed else AccentNeonVolt,
                                    modifier = Modifier.size(18.dp)
                                )
                                Spacer(Modifier.width(10.dp))
                                Text(
                                    text = uiState.lastEventLog!!,
                                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
                                    color = if (uiState.isSuppressedLastAttempt) Color(0xFFFF8A80) else TextPrimaryWhite
                                )
                            }
                        }
                    }
                }
            }

            // Live Stream Triggers (Disabled until edge model is deployed)
            Button(
                onClick = {},
                enabled = false,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                colors = ButtonDefaults.buttonColors(
                    disabledContainerColor = SurfaceVariantDark.copy(alpha = 0.5f),
                    disabledContentColor = TextMuted
                ),
                shape = RoundedCornerShape(14.dp)
            ) {
                Text(
                    text = "Live Stream Triggers (Disabled: no live stream)",
                    style = MaterialTheme.typography.labelMedium
                )
            }

            // Clearly labelled "Cue player test" section
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                border = BorderStroke(1.dp, CardBorderSubtle)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(
                        text = "CUE PLAYER TEST (Audio & Rate Limiter Diagnostics)",
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                        color = AccentNeonVolt
                    )

                    Button(
                        onClick = {
                            viewModel.triggerCue(cueText = "Keep elbow high at contact point.")
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = AccentNeonVolt,
                            contentColor = BackgroundOnyx
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(imageVector = Icons.Rounded.PlayArrow, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = "Test Manual Cue #1",
                            fontWeight = FontWeight.Bold
                        )
                    }

                    Button(
                        onClick = {
                            viewModel.triggerCue(cueText = "Accelerate forearm pronation now!")
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = SurfaceVariantDark,
                            contentColor = TextPrimaryWhite
                        ),
                        shape = RoundedCornerShape(12.dp),
                        border = BorderStroke(1.dp, CardBorderSubtle)
                    ) {
                        Icon(imageVector = Icons.AutoMirrored.Rounded.VolumeUp, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = "Test Immediate Cue #2 (15s Suppression Test)",
                            fontWeight = FontWeight.SemiBold
                        )
                    }

                    OutlinedButton(
                        onClick = { viewModel.resetCooldown() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(42.dp),
                        shape = RoundedCornerShape(12.dp),
                        border = BorderStroke(1.dp, CardBorderSubtle)
                    ) {
                        Icon(imageVector = Icons.Rounded.Refresh, contentDescription = null, modifier = Modifier.size(16.dp), tint = TextMuted)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = "Reset 15s Cooldown",
                            style = MaterialTheme.typography.labelMedium,
                            color = TextMuted
                        )
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Return Home
        Button(
            onClick = { navController.navigate(Screen.Home.route) },
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = SurfaceCharcoal,
                contentColor = TextSecondarySilver
            ),
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Text(text = "End Live Stream", style = MaterialTheme.typography.labelLarge)
        }
    }
}
