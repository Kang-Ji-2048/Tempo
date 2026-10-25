package com.tempo.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Cameraswitch
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.feature.live.LiveConnection
import com.tempo.app.feature.live.LivePose
import com.tempo.app.feature.live.LivePoseAnalyzer
import com.tempo.app.feature.live.LiveUiState
import com.tempo.app.feature.live.LiveViewModel
import com.tempo.app.feature.voice.VoiceMicButton
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import java.util.concurrent.Executors
import kotlin.math.roundToInt

/** MediaPipe Pose skeleton edges (arms, torso, legs; face omitted). */
private val POSE_EDGES = listOf(
    11 to 12, 11 to 13, 13 to 15, 12 to 14, 14 to 16, 11 to 23, 12 to 24, 23 to 24,
    23 to 25, 25 to 27, 24 to 26, 26 to 28, 27 to 31, 28 to 32, 15 to 19, 16 to 20,
)
private const val MIN_VISIBILITY = 0.5f

@Composable
fun LiveScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: LiveViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val pose by viewModel.pose.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var hasCamera by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    var frontCamera by rememberSaveable { mutableStateOf(false) }
    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { hasCamera = it }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    text = "LIVE DRILL MODE",
                    style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold),
                    color = AccentNeonVolt
                )
                Text(
                    text = uiState.activeLesson ?: uiState.skill?.replace('_', ' ')?.replaceFirstChar { it.uppercase() } ?: "Live Coaching",
                    style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Black),
                    color = TextPrimaryWhite
                )
            }
            ConnectionPill(uiState.connection)
        }

        // Camera + skeleton overlay, both in the analysis frame's 3:4 space so landmarks line up.
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(3f / 4f)
                .clip(RoundedCornerShape(24.dp))
                .background(SurfaceCharcoal)
        ) {
            if (hasCamera) {
                CameraPoseFeed(
                    frontCamera = frontCamera,
                    onPose = viewModel::onPose,
                    onNoPose = viewModel::onPoseLost,
                )
                SkeletonOverlay(pose = pose, mirror = frontCamera, modifier = Modifier.fillMaxSize())
            } else {
                Column(
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text("Live mode needs the camera to see your form.", color = TextSecondarySilver)
                    Button(onClick = { cameraPermission.launch(Manifest.permission.CAMERA) }) { Text("Allow camera") }
                }
            }
            HudRow(uiState, Modifier.align(Alignment.TopStart).padding(12.dp))
            IconButton(
                onClick = { frontCamera = !frontCamera },
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(8.dp)
                    .clip(CircleShape)
                    .background(BackgroundOnyx.copy(alpha = 0.6f))
            ) {
                Icon(Icons.Rounded.Cameraswitch, contentDescription = "Switch camera", tint = TextPrimaryWhite)
            }
            if (pose == null && hasCamera) {
                Text(
                    "Step back until your whole body is in frame",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextPrimaryWhite,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(12.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(BackgroundOnyx.copy(alpha = 0.7f))
                        .padding(horizontal = 10.dp, vertical = 6.dp)
                )
            }
        }

        CueCard(uiState)

        Button(
            onClick = viewModel::toggleLive,
            enabled = hasCamera && uiState.connection != LiveConnection.CONNECTING,
            modifier = Modifier.fillMaxWidth().height(56.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (uiState.isStreaming) ErrorRed else AccentNeonVolt,
                contentColor = if (uiState.isStreaming) TextPrimaryWhite else BackgroundOnyx
            )
        ) {
            Icon(if (uiState.isStreaming) Icons.Rounded.Stop else Icons.Rounded.PlayArrow, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(if (uiState.isStreaming) "Stop live drill" else "Start live drill", fontWeight = FontWeight.Bold)
        }
        uiState.statusMessage?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver) }

        // Ask Thea anything mid-drill; answers are spoken right away, form cues wait until she's done.
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = SurfaceCharcoal,
            border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.4f)),
            modifier = Modifier.fillMaxWidth()
        ) {
            VoiceMicButton(channel = "live", modifier = Modifier.padding(16.dp))
        }

        uiState.lastEventLog?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = TextMuted)
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun CameraPoseFeed(frontCamera: Boolean, onPose: (LivePose) -> Unit, onNoPose: () -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val previewView = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }

    DisposableEffect(lifecycleOwner, frontCamera) {
        val executor = Executors.newSingleThreadExecutor()
        val analyzer = LivePoseAnalyzer(context, onPose, onNoPose)
        val providerFuture = ProcessCameraProvider.getInstance(context)
        val fourByThree = ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
            .build()
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().setResolutionSelector(fourByThree).build()
                .also { it.setSurfaceProvider(previewView.surfaceProvider) }
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(fourByThree)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .build()
                .also { it.setAnalyzer(executor, analyzer) }
            val selector = if (frontCamera) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
            runCatching {
                provider.unbindAll()
                provider.bindToLifecycle(lifecycleOwner, selector, preview, analysis)
            }
        }, ContextCompat.getMainExecutor(context))

        onDispose {
            runCatching { providerFuture.get().unbindAll() }
            executor.shutdown()
            analyzer.close()
        }
    }
    AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())
}

@Composable
private fun SkeletonOverlay(pose: LivePose?, mirror: Boolean, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val landmarks = pose?.landmarks ?: return@Canvas
        fun point(i: Int): Offset? {
            val lm = landmarks.getOrNull(i) ?: return null
            if (lm[3] < MIN_VISIBILITY) return null
            val x = if (mirror) 1f - lm[0] else lm[0]
            return Offset(x * size.width, lm[1] * size.height)
        }
        POSE_EDGES.forEach { (a, b) ->
            val p1 = point(a)
            val p2 = point(b)
            if (p1 != null && p2 != null) {
                drawLine(AccentNeonVolt, p1, p2, strokeWidth = 5.dp.toPx(), cap = StrokeCap.Round)
            }
        }
        (11..32).forEach { i ->
            point(i)?.let { drawCircle(Color.White, radius = 4.dp.toPx(), center = it) }
        }
    }
}

@Composable
private fun HudRow(state: LiveUiState, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        HudChip("Reps ${state.reps}")
        state.elbowDeg?.let { elbow ->
            val target = state.thresholdDeg?.let { " / ${it.roundToInt()}°" }.orEmpty()
            HudChip("Elbow ${elbow.roundToInt()}°$target", good = state.thresholdDeg?.let { elbow >= it })
        }
        state.kneeDeg?.let { HudChip("Knee ${it.roundToInt()}°") }
        if (state.isStreaming) HudChip("${state.sentFps} Hz")
    }
}

@Composable
private fun HudChip(text: String, good: Boolean? = null) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold),
        color = when (good) {
            true -> AccentNeonVolt
            false -> ErrorRed
            null -> TextPrimaryWhite
        },
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(BackgroundOnyx.copy(alpha = 0.65f))
            .padding(horizontal = 8.dp, vertical = 4.dp)
    )
}

@Composable
private fun ConnectionPill(connection: LiveConnection) {
    val (label, color) = when (connection) {
        LiveConnection.LIVE -> "LIVE" to AccentNeonVolt
        LiveConnection.CONNECTING -> "CONNECTING" to TextSecondarySilver
        LiveConnection.ERROR -> "OFFLINE" to ErrorRed
        LiveConnection.DISCONNECTED -> "IDLE" to TextMuted
    }
    Surface(shape = RoundedCornerShape(10.dp), color = SurfaceVariantDark, border = BorderStroke(1.dp, CardBorderSubtle)) {
        Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(6.dp))
            Text(label, style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold), color = color)
        }
    }
}

@Composable
private fun CueCard(state: LiveUiState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, CardBorderSubtle)
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(
                    "THEA'S CUE",
                    style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold),
                    color = AccentNeonVolt
                )
                Text(
                    if (state.cooldownRemainingMs > 0) "Next cue in ${(state.cooldownRemainingMs + 999) / 1000}s" else "Ready",
                    style = MaterialTheme.typography.labelSmall,
                    color = TextMuted
                )
            }
            Text(
                state.activeCueText,
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                color = if (state.lastCueFocus == "positive") AccentNeonVolt else TextPrimaryWhite
            )
            Text(
                "Played ${state.totalCuesPlayed} • held for cooldown ${state.totalCuesSuppressed} • held while talking ${state.cuesHeldForVoice}",
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondarySilver
            )
        }
    }
}
