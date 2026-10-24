package com.tempo.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
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
fun LiveScreen(
    navController: NavController,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .padding(24.dp),
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        Column {
            Text(
                text = "REAL-TIME EDGE STREAM",
                style = MaterialTheme.typography.labelLarge,
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Live Earbud Cueing",
                style = MaterialTheme.typography.displayLarge
            )
            Spacer(modifier = Modifier.height(16.dp))

            // Live HUD Card
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(300.dp),
                shape = MaterialTheme.shapes.large,
                colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                border = BorderStroke(1.dp, CardBorderSubtle)
            ) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = "WebSocket /api/v1/live/stream Connected",
                            style = MaterialTheme.typography.titleMedium,
                            color = AccentNeonVolt
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Streaming keyframes at 2-3 fps + 168 BPM",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondarySilver
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = "\"Keep elbow high before shuttle contact.\"",
                            style = MaterialTheme.typography.titleLarge,
                            color = AccentNeonVolt
                        )
                    }
                }
            }
        }

        Button(
            onClick = { navController.navigate(Screen.Home.route) },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = SurfaceCharcoal,
                contentColor = TextSecondarySilver
            ),
            shape = MaterialTheme.shapes.medium
        ) {
            Text(text = "End Live Stream", style = MaterialTheme.typography.labelLarge)
        }
    }
}
