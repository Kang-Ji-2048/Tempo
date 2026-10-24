package com.tempo.app.feature.correction.ui

import android.net.Uri
import androidx.annotation.OptIn
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Replay
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.tempo.app.feature.correction.model.CachedVideoPoseTrack
import com.tempo.app.feature.correction.model.FramePose
import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import kotlinx.coroutines.delay
import java.io.File
import kotlin.math.abs

@OptIn(UnstableApi::class)
@Composable
fun VisualCorrectionPlayer(
    videoPath: String?,
    poseTrack: CachedVideoPoseTrack?,
    phases: List<KineticPhaseUiModel>,
    modifier: Modifier = Modifier,
    onPhaseSelected: (KineticPhaseUiModel) -> Unit = {}
) {
    val context = LocalContext.current

    // Player state
    var isPlaying by remember { mutableStateOf(false) }
    var currentPositionMs by remember { mutableLongStateOf(0L) }
    var totalDurationMs by remember { mutableLongStateOf(poseTrack?.durationMs ?: 3000L) }
    var showOverlayLandmarks by remember { mutableStateOf(true) }

    // Initialize ExoPlayer
    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply {
            repeatMode = Player.REPEAT_MODE_ALL
            playWhenReady = true
        }
    }

    // Set video source
    LaunchedEffect(videoPath) {
        if (!videoPath.isNullOrBlank()) {
            val file = File(videoPath)
            if (file.exists()) {
                val mediaItem = MediaItem.fromUri(Uri.fromFile(file))
                exoPlayer.setMediaItem(mediaItem)
                exoPlayer.prepare()
            }
        }
    }

    // Lifecycle cleanup
    DisposableEffect(exoPlayer) {
        val listener = object : Player.Listener {
            override fun onIsPlayingChanged(playing: Boolean) {
                isPlaying = playing
            }

            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY) {
                    val duration = exoPlayer.duration
                    if (duration > 0) {
                        totalDurationMs = duration
                    }
                }
            }
        }
        exoPlayer.addListener(listener)

        onDispose {
            exoPlayer.removeListener(listener)
            exoPlayer.release()
        }
    }

    // Smooth polling loop for skeleton synchronization (~60 fps)
    LaunchedEffect(exoPlayer, isPlaying) {
        while (true) {
            currentPositionMs = exoPlayer.currentPosition
            delay(16L)
        }
    }

    // Find nearest athlete pose for current playback timestamp
    val currentPose: FramePose? = remember(currentPositionMs, poseTrack) {
        poseTrack?.frames?.minByOrNull { abs(it.timestampMs - currentPositionMs) }
    }

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = androidx.compose.foundation.BorderStroke(1.dp, CardBorderSubtle)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header Bar
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = "BIOMECHANICAL MOTION OVERLAY",
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.2.sp,
                        color = AccentNeonVolt
                    )
                    Text(
                        text = "33-Landmark Pose Tracking",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimaryWhite
                    )
                }

                // Toggle Skeleton overlay button
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(12.dp))
                        .background(if (showOverlayLandmarks) AccentNeonVolt.copy(alpha = 0.15f) else SurfaceVariantDark)
                        .border(
                            1.dp,
                            if (showOverlayLandmarks) AccentNeonVolt else CardBorderSubtle,
                            RoundedCornerShape(12.dp)
                        )
                        .clickable { showOverlayLandmarks = !showOverlayLandmarks }
                        .padding(horizontal = 10.dp, vertical = 6.dp)
                ) {
                    Text(
                        text = if (showOverlayLandmarks) "Skeleton ON" else "Skeleton OFF",
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (showOverlayLandmarks) AccentNeonVolt else TextSecondarySilver
                    )
                }
            }

            Spacer(Modifier.height(14.dp))

            // Main Video Surface + Synchronized Canvas Overlay
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(9f / 16f)
                    .clip(RoundedCornerShape(18.dp))
                    .background(BackgroundOnyx)
            ) {
                // ExoPlayer View
                AndroidView(
                    factory = { ctx ->
                        PlayerView(ctx).apply {
                            player = exoPlayer
                            useController = false
                            setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )

                // Synchronized Pose Canvas Overlay
                if (showOverlayLandmarks) {
                    SkeletonCanvasOverlay(
                        athleteLandmarks = currentPose?.landmarks,
                        referenceLandmarks = null,
                        modifier = Modifier.fillMaxSize()
                    )
                }

                // Play / Pause Floating Control Overlay on tap
                Box(
                    modifier = Modifier
                        .align(Alignment.Center)
                        .size(56.dp)
                        .clip(CircleShape)
                        .background(BackgroundOnyx.copy(alpha = 0.65f))
                        .clickable {
                            if (exoPlayer.isPlaying) {
                                exoPlayer.pause()
                            } else {
                                exoPlayer.play()
                            }
                        },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = if (isPlaying) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                        contentDescription = if (isPlaying) "Pause" else "Play",
                        tint = AccentNeonVolt,
                        modifier = Modifier.size(32.dp)
                    )
                }

                // Live Timestamp Badge
                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(12.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(BackgroundOnyx.copy(alpha = 0.80f))
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    val sec = currentPositionMs / 1000f
                    Text(
                        text = String.format("%.2fs", sec),
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = AccentNeonVolt
                    )
                }
            }

            Spacer(Modifier.height(14.dp))

            // Scrub Bar with Phase Markers
            CorrectionScrubBar(
                currentPositionMs = currentPositionMs,
                totalDurationMs = totalDurationMs.coerceAtLeast(1000L),
                phases = phases,
                onSeek = { targetMs ->
                    exoPlayer.seekTo(targetMs)
                    currentPositionMs = targetMs
                },
                onPhaseClick = { phase ->
                    exoPlayer.seekTo(phase.timestampMs)
                    currentPositionMs = phase.timestampMs
                    onPhaseSelected(phase)
                }
            )
        }
    }
}

@Composable
fun CorrectionScrubBar(
    currentPositionMs: Long,
    totalDurationMs: Long,
    phases: List<KineticPhaseUiModel>,
    onSeek: (Long) -> Unit,
    onPhaseClick: (KineticPhaseUiModel) -> Unit,
    modifier: Modifier = Modifier
) {
    val progress = (currentPositionMs.toFloat() / totalDurationMs.toFloat()).coerceIn(0f, 1f)

    Column(modifier = modifier.fillMaxWidth()) {
        // Scrubber Track
        BoxWithConstraints(
            modifier = Modifier
                .fillMaxWidth()
                .height(44.dp)
                .pointerInput(totalDurationMs) {
                    detectTapGestures { offset ->
                        val ratio = (offset.x / size.width).coerceIn(0f, 1f)
                        val targetMs = (ratio * totalDurationMs).toLong()
                        onSeek(targetMs)
                    }
                }
                .pointerInput(totalDurationMs) {
                    detectDragGestures { change, _ ->
                        change.consume()
                        val ratio = (change.position.x / size.width).coerceIn(0f, 1f)
                        val targetMs = (ratio * totalDurationMs).toLong()
                        onSeek(targetMs)
                    }
                },
            contentAlignment = Alignment.CenterStart
        ) {
            val totalWidthPx = constraints.maxWidth.toFloat()

            // Background Track
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(SurfaceVariantDark)
            )

            // Active Progress Fill
            Box(
                modifier = Modifier
                    .fillMaxWidth(progress)
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(AccentNeonVolt)
            )

            // Phase Markers on Scrub Track
            for (phase in phases) {
                val phaseRatio = (phase.timestampMs.toFloat() / totalDurationMs.toFloat()).coerceIn(0f, 1f)
                val markerOffsetXPx = phaseRatio * totalWidthPx

                val markerInitial = when {
                    phase.phaseName.startsWith("Prep", ignoreCase = true) -> "P"
                    phase.phaseName.startsWith("Load", ignoreCase = true) -> "L"
                    phase.phaseName.startsWith("Imp", ignoreCase = true) -> "I"
                    else -> "F"
                }

                Box(
                    modifier = Modifier
                        .offset { IntOffset(x = (markerOffsetXPx - 12.dp.toPx()).toInt(), y = 0) }
                        .size(24.dp)
                        .clip(CircleShape)
                        .background(
                            if (phase.phaseName.startsWith("Imp", ignoreCase = true)) Color(0xFFFFB703)
                            else SurfaceCharcoal
                        )
                        .border(
                            1.5.dp,
                            if (phase.phaseName.startsWith("Imp", ignoreCase = true)) Color(0xFFFFB703)
                            else AccentNeonVolt,
                            CircleShape
                        )
                        .clickable { onPhaseClick(phase) },
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = markerInitial,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (phase.phaseName.startsWith("Imp", ignoreCase = true)) BackgroundOnyx else TextPrimaryWhite
                    )
                }
            }

            // Current Playhead Thumb
            val thumbOffsetXPx = progress * totalWidthPx
            Box(
                modifier = Modifier
                    .offset { IntOffset(x = (thumbOffsetXPx - 8.dp.toPx()).toInt(), y = 0) }
                    .size(16.dp)
                    .clip(CircleShape)
                    .background(TextPrimaryWhite)
                    .border(2.dp, AccentNeonVolt, CircleShape)
            )
        }

        // Time labels & Phase Legend
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            val currSec = currentPositionMs / 1000f
            val totSec = totalDurationMs / 1000f
            Text(
                text = String.format("%02d:%02d / %02d:%02d", (currSec / 60).toInt(), (currSec % 60).toInt(), (totSec / 60).toInt(), (totSec % 60).toInt()),
                fontSize = 12.sp,
                color = TextSecondarySilver,
                fontWeight = FontWeight.Medium
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                phases.forEach { p ->
                    Text(
                        text = p.phaseName,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = if (p.phaseName.startsWith("Imp", ignoreCase = true)) Color(0xFFFFB703) else TextMuted,
                        modifier = Modifier.clickable { onPhaseClick(p) }
                    )
                }
            }
        }
    }
}
