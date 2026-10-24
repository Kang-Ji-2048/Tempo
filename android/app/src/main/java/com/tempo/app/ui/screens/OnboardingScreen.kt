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
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun OnboardingScreen(
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
                text = "WELCOME TO TEMPO",
                style = MaterialTheme.typography.labelLarge,
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Kinematic Sports Coaching Built for You",
                style = MaterialTheme.typography.displayLarge
            )

            Spacer(modifier = Modifier.height(24.dp))

            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = MaterialTheme.shapes.large,
                colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                border = BorderStroke(1.dp, CardBorderSubtle)
            ) {
                Column(modifier = Modifier.padding(24.dp)) {
                    Text(
                        text = "1. Wearable Telemetry Sync",
                        style = MaterialTheme.typography.titleMedium,
                        color = AccentNeonVolt
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Syncs with Android Health Connect to track cardiovascular load and cadence.",
                        style = MaterialTheme.typography.bodyMedium
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    Text(
                        text = "2. Gemini 4 Argon Biomechanics",
                        style = MaterialTheme.typography.titleMedium,
                        color = AccentNeonVolt
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Breaks down your kinetic chain (preparation, loading, impact, recovery) vs Olympic baselines.",
                        style = MaterialTheme.typography.bodyMedium
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    Text(
                        text = "3. Dynamic SDUI Drills",
                        style = MaterialTheme.typography.titleMedium,
                        color = AccentNeonVolt
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Emits Server-Driven UI progression trees and remedial drills tailored to your exact flaw.",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }

        Button(
            onClick = {
                navController.navigate(Screen.Home.route) {
                    popUpTo(Screen.Onboarding.route) { inclusive = true }
                }
            },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = AccentNeonVolt,
                contentColor = BackgroundOnyx
            ),
            shape = MaterialTheme.shapes.medium
        ) {
            Text(text = "Get Started", style = MaterialTheme.typography.labelLarge)
        }
    }
}
