package com.tempo.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.tempo.app.BuildConfig
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.tempo.app.feature.home.HomeViewModel

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue

@OptIn(ExperimentalFoundationApi::class, ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: HomeViewModel = hiltViewModel()
) {
    val profile by viewModel.userProfile.collectAsStateWithLifecycle()
    val debugState by viewModel.debugState.collectAsStateWithLifecycle()
    var showDebugSheet by remember { mutableStateOf(false) }

    val sportDisplay = profile?.sport?.replaceFirstChar { it.uppercase() } ?: "Badminton"
    val archetypeDisplay = profile?.targetArchetype ?: "Viktor Axelsen"
    val playstyleDisplay = profile?.playstyle?.replaceFirstChar { it.uppercase() } ?: "Aggressive"

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
                    .padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text(
                    text = "SETTINGS & DEBUG",
                    style = MaterialTheme.typography.titleLarge,
                    color = AccentNeonVolt
                )

                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = MaterialTheme.shapes.medium,
                    colors = CardDefaults.cardColors(containerColor = BackgroundOnyx),
                    border = BorderStroke(1.dp, CardBorderSubtle)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "BASE_URL:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(text = debugState.baseUrl, style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite)
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "Active Mode:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(
                                text = if (debugState.isMockMode) "Mock API" else "Real Backend",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (debugState.isMockMode) TextSecondarySilver else AccentNeonVolt
                            )
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "Token Present:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(
                                text = if (debugState.isTokenPresent) "Yes" else "No",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (debugState.isTokenPresent) AccentNeonVolt else TextSecondarySilver
                            )
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(text = "Unified User ID:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(text = debugState.userId, style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite)
                        }
                        Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(text = "Backend /health Result:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(
                                text = debugState.healthStatus,
                                style = MaterialTheme.typography.bodySmall,
                                color = TextPrimaryWhite
                            )
                        }
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(text = "Use mock API", style = MaterialTheme.typography.bodyLarge)
                        Text(
                            text = "Takes effect after restart",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextMuted
                        )
                    }
                    Switch(
                        checked = debugState.isMockMode,
                        onCheckedChange = { viewModel.setUseMockApi(it) },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = BackgroundOnyx,
                            checkedTrackColor = AccentNeonVolt
                        )
                    )
                }

                Button(
                    onClick = { viewModel.checkHealth() },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = AccentNeonVolt,
                        contentColor = BackgroundOnyx
                    ),
                    shape = MaterialTheme.shapes.medium
                ) {
                    Text("Re-test Backend /health")
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
                    viewModel.checkHealth()
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
                    text = "TARGET MASTERY",
                    style = MaterialTheme.typography.labelLarge,
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "$sportDisplay Overhead & Stroke Mastery",
                    style = MaterialTheme.typography.titleLarge
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Current Benchmark: $archetypeDisplay profile • $playstyleDisplay style. Biometrics calibrated & ready.",
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

        // Quick Navigation Section
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

            Card(
                modifier = Modifier.weight(1f),
                shape = MaterialTheme.shapes.large,
                colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                border = BorderStroke(1.dp, CardBorderSubtle),
                onClick = { navController.navigate(Screen.Analysis.createRoute("sample_session_01")) }
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(text = "85%", style = MaterialTheme.typography.titleLarge, color = AccentNeonVolt)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(text = "Latest Debrief", style = MaterialTheme.typography.titleMedium)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(text = "View SDUI & drills", style = MaterialTheme.typography.bodyMedium)
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

        if (BuildConfig.DEBUG) {
            OutlinedButton(
                onClick = { navController.navigate(Screen.SduiDebug.route) },
                modifier = Modifier.fillMaxWidth(),
                border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.5f)),
                shape = MaterialTheme.shapes.medium
            ) {
                Text(text = "Open SDUI Lab (debug)", color = AccentNeonVolt)
            }
        }
    }
}
