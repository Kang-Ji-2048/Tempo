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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
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
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun CaptureScreen(
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
                text = "PRACTICE INGESTION",
                style = MaterialTheme.typography.labelLarge,
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Record Practice Set",
                style = MaterialTheme.typography.displayLarge
            )
            Spacer(modifier = Modifier.height(16.dp))

            // Camera Viewfinder Placeholder
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(380.dp),
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
                            text = "CameraX + MediaPipe 33 Pose Viewfinder",
                            style = MaterialTheme.typography.titleMedium,
                            color = AccentNeonVolt
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Wearable Sync: 164 BPM | Health Connect Active",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondarySilver
                        )
                    }
                }
            }
        }

        // Action Trigger
        Button(
            onClick = {
                // Navigate to Analysis mock
                navController.navigate(Screen.Analysis.createRoute("sample_session_01"))
            },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(
                containerColor = ErrorRed,
                contentColor = BackgroundOnyx
            ),
            shape = MaterialTheme.shapes.medium
        ) {
            Icon(imageVector = Icons.Default.FiberManualRecord, contentDescription = null)
            Spacer(modifier = Modifier.padding(4.dp))
            Text(text = "Complete & Ingest Practice Set", style = MaterialTheme.typography.labelLarge)
        }
    }
}
