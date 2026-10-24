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
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun ScheduleScreen(
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
                text = "SAINT (THEA) CADENCE",
                style = MaterialTheme.typography.labelLarge,
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Practice Schedule",
                style = MaterialTheme.typography.displayLarge
            )
        }

        // Active Cadence Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(modifier = Modifier.padding(24.dp)) {
                Text(
                    text = "CURRENT CADENCE",
                    style = MaterialTheme.typography.labelLarge,
                    color = AccentNeonVolt
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Mon, Wed, Fri @ 18:00 UTC",
                    style = MaterialTheme.typography.titleLarge
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Badminton Overhead Clear & Jump Smash Focus",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondarySilver
                )
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "Saint (Thea) WhatsApp Priming: Active (30 min lead)",
                    style = MaterialTheme.typography.bodyMedium,
                    color = AccentNeonVolt
                )
            }
        }

        // Recent Dispatches Placeholder
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
                Text(
                    text = "\"Hey Sumanth! Scheduled practice in 30 mins (18:00 UTC). Today's focus: maintaining reach on your overhead clear.\"",
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
    }
}
