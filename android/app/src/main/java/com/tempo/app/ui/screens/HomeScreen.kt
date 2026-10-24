package com.tempo.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Sports
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.NetworkCheck
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import com.tempo.app.BuildConfig
import com.tempo.app.feature.home.HomeViewModel
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun HomeScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: HomeViewModel = hiltViewModel()
) {
    val profile by viewModel.userProfile.collectAsStateWithLifecycle()
    val latestSession by viewModel.latestSession.collectAsStateWithLifecycle()
    val debugState by viewModel.debugState.collectAsStateWithLifecycle()
    var showDebugSheet by remember { mutableStateOf(false) }

    val sportDisplay = profile?.sport?.replaceFirstChar { it.uppercase() }
        ?: debugState.sport.takeIf { it.isNotBlank() && it != "Not selected" }?.replaceFirstChar { it.uppercase() }
        ?: "Select Sport"
    val levelDisplay = profile?.level?.replaceFirstChar { it.uppercase() } ?: "Intermediate"
    val playstyleDisplay = profile?.playstyle?.replaceFirstChar { it.uppercase() } ?: "All-court"
    val goalDisplay = profile?.goal?.replace("_", " ")?.replaceFirstChar { it.uppercase() } ?: "Technique Refinement"

    if (showDebugSheet) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(
            onDismissRequest = { showDebugSheet = false },
            sheetState = sheetState,
            containerColor = SurfaceCharcoal,
            contentColor = TextPrimaryWhite
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "SETTINGS & DIAGNOSTICS",
                        style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                        color = AccentNeonVolt
                    )
                }

                // Account & Config Card
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = BackgroundOnyx),
                    border = BorderStroke(1.dp, CardBorderSubtle)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "Athlete Email:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(text = debugState.email, style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite, fontWeight = FontWeight.SemiBold)
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "Active Sport:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(text = sportDisplay, style = MaterialTheme.typography.bodySmall, color = AccentNeonVolt, fontWeight = FontWeight.Bold)
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "BASE_URL:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(text = debugState.baseUrl, style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite)
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "Backend Mode:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(
                                text = if (debugState.isMockMode) "Mock API" else "Real Backend",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (debugState.isMockMode) TextSecondarySilver else AccentNeonVolt,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }

                // AI Engine Status Card (R2f)
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = BackgroundOnyx),
                    border = BorderStroke(1.dp, CardBorderSubtle)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(text = "AI ENGINE (GEMINI 4 ARGON)", style = MaterialTheme.typography.labelSmall, color = AccentNeonVolt)
                        val ai = debugState.aiStatus
                        if (ai != null) {
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(text = "Model ID:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                                Text(text = ai.model, style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite, fontWeight = FontWeight.Bold)
                            }
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(text = "API Key:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                                Text(text = ai.key_masked, style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite)
                            }
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(text = "Last Call:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                                Text(
                                    text = if (ai.last_call_ok == true) "OK (${ai.last_latency_ms ?: 0}ms)" else if (ai.last_call_ok == false) "Fallback" else "No calls yet",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = if (ai.last_call_ok == true) AccentNeonVolt else if (ai.last_call_ok == false) Color(0xFFFF8A80) else TextMuted,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            if (ai.last_error != null) {
                                Text(
                                    text = "Error: ${ai.last_error}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Color(0xFFFF8A80)
                                )
                            }
                        } else {
                            Text(text = "Tap 'Test Connection' to query /api/v1/ai/status", style = MaterialTheme.typography.bodySmall, color = TextMuted)
                        }
                    }
                }

                // Health Status Card
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = BackgroundOnyx),
                    border = BorderStroke(1.dp, CardBorderSubtle)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(text = "Network /health Diagnostics:", style = MaterialTheme.typography.labelSmall, color = AccentNeonVolt)
                        Text(
                            text = debugState.healthStatus,
                            style = MaterialTheme.typography.bodySmall,
                            color = TextPrimaryWhite
                        )
                    }
                }

                // Test Connection Button
                Button(
                    onClick = { viewModel.testConnection() },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !debugState.isCheckingConnection,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = AccentNeonVolt,
                        contentColor = BackgroundOnyx
                    ),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    if (debugState.isCheckingConnection) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), color = BackgroundOnyx, strokeWidth = 2.dp)
                    } else {
                        Icon(imageVector = Icons.Rounded.NetworkCheck, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Test Connection (/health & AI)", fontWeight = FontWeight.Bold)
                    }
                }

                // Change Sport Button (R4)
                OutlinedButton(
                    onClick = {
                        showDebugSheet = false
                        navController.navigate(Screen.SportSelection.route)
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.6f))
                ) {
                    Icon(imageVector = Icons.Default.Sports, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Change Sport Discipline", color = AccentNeonVolt, fontWeight = FontWeight.SemiBold)
                }

                // Logout Button (R3)
                OutlinedButton(
                    onClick = {
                        showDebugSheet = false
                        viewModel.logout {
                            navController.navigate(Screen.Login.route) {
                                popUpTo(0) { inclusive = true }
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    border = BorderStroke(1.dp, Color(0xFFC62828))
                ) {
                    Icon(imageVector = Icons.Default.ExitToApp, contentDescription = null, tint = Color(0xFFFF8A80), modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Sign Out (Clear Room & Tokens)", color = Color(0xFFFF8A80), fontWeight = FontWeight.SemiBold)
                }

                Spacer(modifier = Modifier.height(16.dp))
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        // Top Welcome Header with Long-Press Debug Trigger
        Column(
            modifier = Modifier.combinedClickable(
                onLongClick = {
                    showDebugSheet = true
                    viewModel.testConnection()
                },
                onClick = {}
            )
        ) {
            Text(
                text = "TEMPO AI",
                style = MaterialTheme.typography.labelLarge,
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Autonomous Sports Coach",
                style = MaterialTheme.typography.displayLarge
            )
            Text(
                text = "Long-press header to open Diagnostics sheet",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted
            )
        }

        // Daily Hero Action Card (Large 24.dp Rounded Card)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(24.dp)) {
                Text(
                    text = "ACTIVE CALIBRATION",
                    style = MaterialTheme.typography.labelLarge,
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "$sportDisplay Technique Calibration",
                    style = MaterialTheme.typography.titleLarge
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Profile: $levelDisplay level • $playstyleDisplay style • Goal: $goalDisplay.",
                    style = MaterialTheme.typography.bodyMedium
                )
                Spacer(modifier = Modifier.height(20.dp))
                Button(
                    onClick = { navController.navigate(Screen.Capture.route) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = AccentNeonVolt,
                        contentColor = BackgroundOnyx
                    ),
                    shape = MaterialTheme.shapes.medium
                ) {
                    Icon(imageVector = Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(modifier = Modifier.padding(4.dp))
                    Text(text = "Start Practice Session", style = MaterialTheme.typography.labelLarge)
                }
            }
        }

        // Quick Navigation Section: Real Latest Session vs Empty State (R5)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Card(
                modifier = Modifier.weight(1f),
                shape = MaterialTheme.shapes.large,
                colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                border = BorderStroke(1.dp, CardBorderSubtle),
                onClick = { navController.navigate(Screen.Live.route) }
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Icon(imageVector = Icons.Default.Speed, contentDescription = null, tint = AccentNeonVolt)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(text = "Live Earbud Cues", style = MaterialTheme.typography.titleMedium)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(text = "Real-time edge audio corrections", style = MaterialTheme.typography.bodyMedium)
                }
            }

            if (latestSession != null && latestSession?.overallScore != null) {
                val score = latestSession?.overallScore ?: 0
                Card(
                    modifier = Modifier.weight(1f),
                    shape = MaterialTheme.shapes.large,
                    colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                    border = BorderStroke(1.dp, CardBorderSubtle),
                    onClick = { navController.navigate(Screen.Analysis.createRoute(latestSession!!.sessionId)) }
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(text = "$score%", style = MaterialTheme.typography.titleLarge, color = AccentNeonVolt)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(text = "Latest Debrief", style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = latestSession?.primaryFlaw?.take(35) ?: "View SDUI & drills",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextSecondarySilver
                        )
                    }
                }
            } else {
                Card(
                    modifier = Modifier.weight(1f),
                    shape = MaterialTheme.shapes.large,
                    colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                    border = BorderStroke(1.dp, CardBorderSubtle),
                    onClick = { navController.navigate(Screen.Capture.route) }
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(text = "No sessions yet", style = MaterialTheme.typography.titleSmall, color = TextPrimaryWhite)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(text = "Record your first set", style = MaterialTheme.typography.bodyMedium, color = AccentNeonVolt)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(text = "Capture a practice clip", style = MaterialTheme.typography.bodySmall, color = TextMuted)
                    }
                }
            }
        }

        // Onboarding shortcut for testing
        OutlinedButton(
            onClick = { navController.navigate(Screen.Onboarding.route) },
            modifier = Modifier.fillMaxWidth(),
            border = BorderStroke(1.dp, CardBorderSubtle),
            shape = MaterialTheme.shapes.medium
        ) {
            Text(text = "View Athlete Onboarding", color = TextSecondarySilver)
        }

        // SDUI Lab: debug only, labeled "Mock widget lab (debug only)", hidden in release
        if (BuildConfig.DEBUG) {
            OutlinedButton(
                onClick = { navController.navigate(Screen.SduiDebug.route) },
                modifier = Modifier.fillMaxWidth(),
                border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.5f)),
                shape = MaterialTheme.shapes.medium
            ) {
                Text(text = "Mock widget lab (debug only)", color = AccentNeonVolt)
            }
        }
    }
}
