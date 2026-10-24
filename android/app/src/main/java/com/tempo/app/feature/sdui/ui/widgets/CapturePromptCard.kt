package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CameraAlt
import androidx.compose.material.icons.rounded.FiberManualRecord
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.sdui.model.CapturePromptWidget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.feature.sdui.ui.components.SduiCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun CapturePromptCard(
    widget: CapturePromptWidget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    SduiCard(eyebrow = "Capture", icon = Icons.Rounded.Videocam, modifier = modifier, highlighted = true) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            GlowingCamera()
            Spacer(Modifier.size(16.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(widget.title, color = TextPrimaryWhite, fontSize = 20.sp, fontWeight = FontWeight.Bold, lineHeight = 25.sp)
                Text(widget.instruction, color = TextSecondarySilver, fontSize = 14.sp, lineHeight = 20.sp)
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetaChip(Icons.Rounded.Timer, "${widget.durationS}s")
            MetaChip(Icons.Rounded.CameraAlt, widget.cameraHint, Modifier.weight(1f, fill = false))
        }

        Button(
            onClick = {
                onAction(
                    WidgetAction.CaptureRequested(
                        widgetId = widget.id,
                        durationS = widget.durationS,
                        cameraHint = widget.cameraHint,
                    ),
                )
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(54.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = AccentNeonVolt, contentColor = BackgroundOnyx),
        ) {
            Icon(Icons.Rounded.FiberManualRecord, null, modifier = Modifier.size(16.dp))
            Spacer(Modifier.size(8.dp))
            Text("Start recording", fontWeight = FontWeight.Bold, fontSize = 16.sp)
        }
    }
}

@Composable
private fun GlowingCamera() {
    val transition = rememberInfiniteTransition(label = "cameraGlow")
    val glow by transition.animateFloat(
        initialValue = 0.85f,
        targetValue = 1.15f,
        animationSpec = infiniteRepeatable(tween(1100, easing = LinearEasing), RepeatMode.Reverse),
        label = "glowScale",
    )
    Box(contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(64.dp)
                .graphicsLayer { scaleX = glow; scaleY = glow; alpha = 1.6f - glow }
                .clip(CircleShape)
                .background(AccentNeonVolt.copy(alpha = 0.25f)),
        )
        Box(
            modifier = Modifier
                .size(52.dp)
                .clip(CircleShape)
                .background(AccentNeonVolt),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.Videocam, null, tint = BackgroundOnyx, modifier = Modifier.size(26.dp))
        }
    }
}

@Composable
private fun MetaChip(icon: ImageVector, label: String, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(BackgroundOnyx.copy(alpha = 0.6f))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, null, tint = AccentNeonVolt, modifier = Modifier.size(16.dp))
        Spacer(Modifier.size(6.dp))
        Text(label, color = TextPrimaryWhite, fontSize = 13.sp, maxLines = 1)
    }
}
