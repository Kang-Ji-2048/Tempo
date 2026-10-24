package com.tempo.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun AnalysisScreen(
    sessionId: String,
    navController: NavController,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Column {
            Text(
                text = "BIOMECHANICAL DEBRIEF",
                style = MaterialTheme.typography.labelLarge,
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Session Analysis",
                style = MaterialTheme.typography.displayLarge
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = "ID: $sessionId",
                style = MaterialTheme.typography.bodyMedium,
                color = TextMuted
            )
        }

        // Score Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(24.dp)) {
                Text(
                    text = "85 / 100",
                    style = MaterialTheme.typography.displayLarge,
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Benchmark: Viktor Axelsen (Overhead Clear)",
                    style = MaterialTheme.typography.titleMedium
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Focus: 'Accelerate forearm pronation at peak reach, not before.'",
                    style = MaterialTheme.typography.bodyLarge
                )
            }
        }

        // SDUI Widget Placeholder 1: PathProgressWidget
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "SERVER-DRIVEN UI: PathProgressWidget",
                    style = MaterialTheme.typography.labelLarge,
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Current Streak: 5 Days",
                    style = MaterialTheme.typography.titleMedium
                )
                Text(
                    text = "Active Node: Forearm Pronation Speed (UNLOCKED)",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondarySilver
                )
            }
        }

        // SDUI Widget Placeholder 2: DrillCardWidget
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "PRESCRIBED REMEDIAL DRILL",
                    style = MaterialTheme.typography.labelLarge,
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "30s Rapid Pronation Drill (15 Reps)",
                    style = MaterialTheme.typography.titleMedium
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Stand 1 meter from wall. Rapidly pronate forearm against shuttlecock target maintaining elbow height.",
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }

        Button(
            onClick = { navController.navigate(Screen.Home.route) },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = AccentNeonVolt,
                contentColor = BackgroundOnyx
            ),
            shape = MaterialTheme.shapes.medium
        ) {
            Text(text = "Back to Home", style = MaterialTheme.typography.labelLarge)
        }
    }
}
