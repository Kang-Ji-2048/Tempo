package com.tempo.app.feature.capture.ui

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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CameraAlt
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.Videocam
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun PermissionRationaleView(
    onRequestPermissions: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = androidx.compose.foundation.BorderStroke(1.dp, CardBorderSubtle),
        ) {
            Column(
                modifier = Modifier.padding(28.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(68.dp)
                        .clip(CircleShape)
                        .background(AccentNeonVolt.copy(alpha = 0.14f))
                        .border(1.5.dp, AccentNeonVolt, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Videocam,
                        contentDescription = null,
                        tint = AccentNeonVolt,
                        modifier = Modifier.size(32.dp),
                    )
                }

                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "Camera & Audio Access",
                        style = MaterialTheme.typography.headlineMedium,
                        textAlign = TextAlign.Center,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = "Tempo uses your camera to measure real-time biomechanics and MediaPipe pose landmarks, and microphone to calibrate audio coaching cadence.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondarySilver,
                        textAlign = TextAlign.Center,
                    )
                }

                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    PermissionReasonRow(
                        icon = Icons.Rounded.CameraAlt,
                        title = "Biomechanical Video Analysis",
                        subtitle = "60/30fps capture with 33-point skeletal pose tracking",
                    )
                    PermissionReasonRow(
                        icon = Icons.Rounded.Mic,
                        title = "Audio Cadence & Cues",
                        subtitle = "Sync stroke contact sound with wearable biometrics",
                    )
                }

                Button(
                    onClick = onRequestPermissions,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(52.dp),
                    shape = RoundedCornerShape(16.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = AccentNeonVolt,
                        contentColor = BackgroundOnyx,
                    ),
                ) {
                    Text(
                        text = "Grant Permissions",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun PermissionReasonRow(
    icon: ImageVector,
    title: String,
    subtitle: String,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(BackgroundOnyx),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = AccentNeonVolt,
                modifier = Modifier.size(18.dp),
            )
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(
                text = title,
                color = TextPrimaryWhite,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = subtitle,
                color = TextSecondarySilver,
                fontSize = 12.sp,
            )
        }
    }
}
