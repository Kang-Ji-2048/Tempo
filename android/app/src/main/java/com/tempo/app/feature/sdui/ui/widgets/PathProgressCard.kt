package com.tempo.app.feature.sdui.ui.widgets

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Timeline
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tempo.app.feature.sdui.model.PathNode
import com.tempo.app.feature.sdui.model.PathNodeState
import com.tempo.app.feature.sdui.model.PathProgressWidget
import com.tempo.app.feature.sdui.ui.components.SduiCard
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.AccentNeonVoltDark
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

private val RowHeight = 104.dp
private val NodeBox = 76.dp
private val LabelWidth = 112.dp
private val LabelShift = NodeBox / 2 + 12.dp + LabelWidth / 2
private val ZigZag = listOf(0.dp, 48.dp, 72.dp, 48.dp, 0.dp, (-48).dp, (-72).dp, (-48).dp)

private fun offsetFor(index: Int): Dp = ZigZag[index % ZigZag.size]

@Composable
fun PathProgressCard(
    widget: PathProgressWidget,
    modifier: Modifier = Modifier,
    /** Called for unlocked nodes only; null leaves the path read-only. */
    onNodeClick: ((PathNode) -> Unit)? = null,
) {
    val states = widget.nodes.map(widget::stateOf)
    val done = states.count { it == PathNodeState.DONE }
    val fraction by animateFloatAsState(
        targetValue = if (states.isEmpty()) 0f else done / states.size.toFloat(),
        animationSpec = tween(700),
        label = "pathProgress",
    )

    SduiCard(
        eyebrow = "Skill path",
        icon = Icons.Rounded.Timeline,
        modifier = modifier,
        trailing = { StreakChip(widget.currentStreak) },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(widget.title, style = MaterialTheme.typography.titleLarge)
            Text("$done of ${states.size} skills mastered", style = MaterialTheme.typography.bodyMedium)
        }
        LinearProgressIndicator(
            progress = { fraction },
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp)
                .clip(CircleShape),
            color = AccentNeonVolt,
            trackColor = SurfaceVariantDark,
            drawStopIndicator = {},
        )
        PathTree(widget.nodes, states, onNodeClick)
    }
}

@Composable
private fun PathTree(nodes: List<PathNode>, states: List<PathNodeState>, onNodeClick: ((PathNode) -> Unit)?) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .height(RowHeight * nodes.size),
    ) {
        Canvas(Modifier.matchParentSize()) {
            val row = RowHeight.toPx()
            for (i in 0 until nodes.size - 1) {
                val start = Offset(size.width / 2 + offsetFor(i).toPx(), row * i + row / 2)
                val end = Offset(size.width / 2 + offsetFor(i + 1).toPx(), row * (i + 1) + row / 2)
                val midY = (start.y + end.y) / 2
                val path = Path().apply {
                    moveTo(start.x, start.y)
                    cubicTo(start.x, midY, end.x, midY, end.x, end.y)
                }
                val reached = states[i] == PathNodeState.DONE
                drawPath(
                    path = path,
                    color = if (reached) AccentNeonVolt.copy(alpha = 0.8f) else CardBorderSubtle,
                    style = Stroke(
                        width = 6.dp.toPx(),
                        cap = StrokeCap.Round,
                        pathEffect = if (reached) null else PathEffect.dashPathEffect(floatArrayOf(4f, 22f)),
                    ),
                )
            }
        }

        nodes.forEachIndexed { i, node ->
            val x = offsetFor(i)
            val labelOnRight = x <= 0.dp
            Box(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .offset(x = x, y = RowHeight * i + (RowHeight - NodeBox) / 2)
                    .size(NodeBox)
                    .then(
                        if (onNodeClick != null && states[i] != PathNodeState.LOCKED) {
                            Modifier.clip(CircleShape).clickable { onNodeClick(node) }
                        } else {
                            Modifier
                        }
                    ),
                contentAlignment = Alignment.Center,
            ) {
                PathNodeBubble(states[i])
            }
            NodeLabel(
                node = node,
                state = states[i],
                alignEnd = !labelOnRight,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .offset(
                        x = if (labelOnRight) x + LabelShift else x - LabelShift,
                        y = RowHeight * i + RowHeight / 2 - 20.dp,
                    )
                    .width(LabelWidth),
            )
        }
    }
}

@Composable
private fun PathNodeBubble(state: PathNodeState) {
    val size = if (state == PathNodeState.ACTIVE) 66.dp else 56.dp
    val face = when (state) {
        PathNodeState.DONE, PathNodeState.ACTIVE -> AccentNeonVolt
        PathNodeState.LOCKED -> SurfaceVariantDark
    }
    val rim = when (state) {
        PathNodeState.DONE, PathNodeState.ACTIVE -> AccentNeonVoltDark
        PathNodeState.LOCKED -> CardBorderSubtle
    }
    val icon = when (state) {
        PathNodeState.DONE -> Icons.Rounded.Check
        PathNodeState.ACTIVE -> Icons.Rounded.PlayArrow
        PathNodeState.LOCKED -> Icons.Rounded.Lock
    }
    val tint = if (state == PathNodeState.LOCKED) TextMuted else BackgroundOnyx

    Box(contentAlignment = Alignment.Center) {
        if (state == PathNodeState.ACTIVE) PulseRing(size)
        // "3D" rim underneath, Duolingo-style.
        Box(
            Modifier
                .offset(y = 5.dp)
                .size(size)
                .clip(CircleShape)
                .background(rim),
        )
        Box(
            modifier = Modifier
                .size(size)
                .clip(CircleShape)
                .background(face),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = state.name, tint = tint, modifier = Modifier.size(size * 0.45f))
        }
    }
}

@Composable
private fun PulseRing(size: Dp) {
    val transition = rememberInfiniteTransition(label = "pulse")
    val progress by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1400, easing = LinearEasing), RepeatMode.Restart),
        label = "pulseProgress",
    )
    Box(
        Modifier
            .size(size)
            .graphicsLayer {
                val scale = 1f + 0.4f * progress
                scaleX = scale
                scaleY = scale
                alpha = 1f - progress
            }
            .border(3.dp, AccentNeonVolt, CircleShape),
    )
}

@Composable
private fun NodeLabel(node: PathNode, state: PathNodeState, alignEnd: Boolean, modifier: Modifier) {
    val align = if (alignEnd) TextAlign.End else TextAlign.Start
    Column(modifier = modifier) {
        Text(
            text = node.title,
            color = if (state == PathNodeState.LOCKED) TextMuted else TextPrimaryWhite,
            fontSize = 14.sp,
            fontWeight = if (state == PathNodeState.ACTIVE) FontWeight.Bold else FontWeight.Medium,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            textAlign = align,
            modifier = Modifier.fillMaxWidth(),
        )
        Text(
            text = when (state) {
                PathNodeState.ACTIVE -> "UP NEXT · +${node.xpReward} XP"
                PathNodeState.DONE -> "Mastered"
                PathNodeState.LOCKED -> "+${node.xpReward} XP"
            },
            color = if (state == PathNodeState.ACTIVE) AccentNeonVolt else TextSecondarySilver,
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 0.6.sp,
            textAlign = align,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun StreakChip(streak: Int) {
    Row(
        modifier = Modifier
            .clip(CircleShape)
            .background(AccentNeonVolt.copy(alpha = 0.14f))
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            Icons.Rounded.LocalFireDepartment,
            contentDescription = null,
            tint = AccentNeonVolt,
            modifier = Modifier.size(16.dp),
        )
        Text(
            text = " $streak day${if (streak == 1) "" else "s"}",
            color = AccentNeonVolt,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}
