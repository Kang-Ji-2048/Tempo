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

@Composable
fun HomeScreen(
    navController: NavController,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        // Top Welcome Header
        Column {
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
                    text = "Badminton Overhead Clear & Jump Smash",
                    style = MaterialTheme.typography.titleLarge
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Current Benchmark: Viktor Axelsen profile (175.0° full reach). Connect wearable & start recording.",
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
