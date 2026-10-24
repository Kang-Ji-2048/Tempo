package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Extension
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.BuildConfig
import com.tempo.app.feature.sdui.model.UnknownWidget
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.TextMuted

/**
 * Unknown widgets are skipped silently in release builds. Debug builds show a
 * subtle dashed placeholder so missing client support is visible during development.
 */
@Composable
fun UnknownWidgetCard(widget: UnknownWidget, modifier: Modifier = Modifier) {
    if (!BuildConfig.DEBUG) return
    Row(
        modifier = modifier
            .fillMaxWidth()
            .drawBehind {
                drawRoundRect(
                    color = CardBorderSubtle,
                    cornerRadius = CornerRadius(24.dp.toPx()),
                    style = Stroke(
                        width = 1.5.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 10f)),
                    ),
                )
            }
            .padding(horizontal = 20.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.Extension, null, tint = TextMuted, modifier = Modifier.size(18.dp))
        Spacer(Modifier.size(10.dp))
        Text(
            text = "Unsupported widget “${widget.widgetType}” — skipped safely",
            color = TextMuted,
            fontSize = 13.sp,
        )
    }
}
