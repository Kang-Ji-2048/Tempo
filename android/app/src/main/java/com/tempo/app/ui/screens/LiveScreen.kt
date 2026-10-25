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
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Cameraswitch
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.feature.live.LiveConnection
import com.tempo.app.feature.live.LiveEvent
import com.tempo.app.feature.live.LivePose
import com.tempo.app.feature.live.LivePoseAnalyzer
import com.tempo.app.feature.live.LiveUiState
import com.tempo.app.feature.live.LiveViewModel
import com.tempo.app.feature.live.RepPhase
import com.tempo.app.feature.voice.VoiceMicButton
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import java.util.concurrent.Executors
import kotlin.math.max
import kotlin.math.roundToInt

private val Volt = Color(0xFFCCFF00)
private val Cyan = Color(0xFF00E5FF)
private val Amber = Color(0xFFFFB300)
private val Glass = Color(0xB3101010)
private val LiveGreen = Color(0xFF2EE66B)

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
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val pose by viewModel.pose.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var hasCamera by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    var frontCamera by rememberSaveable { mutableStateOf(true) }
    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { hasCamera = it }

    LaunchedEffect(hasCamera) {
        if (hasCamera) viewModel.startLive() else cameraPermission.launch(Manifest.permission.CAMERA)
    }
    LaunchedEffect(Unit) {
        viewModel.events.collect { event ->
            when (event) {
                is LiveEvent.OpenSession -> navController.navigate(Screen.Analysis.createRoute(event.sessionId))
            }
        }
    }

    Box(modifier = modifier.fillMaxSize().background(Color.Black)) {
        if (hasCamera) {
            CameraPoseFeed(frontCamera = frontCamera, onPose = viewModel::onPose, onNoPose = viewModel::onPoseLost)
            SkeletonOverlay(pose = pose, mirror = frontCamera, state = state, modifier = Modifier.fillMaxSize())
        } else {
            Column(
                modifier = Modifier.align(Alignment.Center).padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text("Live coaching needs the camera to see your form.", color = TextSecondarySilver, textAlign = TextAlign.Center)
                Button(onClick = { cameraPermission.launch(Manifest.permission.CAMERA) }) { Text("Allow camera") }
            }
        }

        TopHud(
            state = state,
            onBack = { navController.popBackStack() },
            onFlip = { frontCamera = !frontCamera },
            modifier = Modifier.align(Alignment.TopCenter).statusBarsPadding().padding(12.dp)
        )
        if (pose == null && hasCamera && state.summary == null) {
            Text(
                "Step back until your whole body is in frame",
                style = MaterialTheme.typography.bodyMedium,
                color = TextPrimaryWhite,
                modifier = Modifier.align(Alignment.Center).clip(RoundedCornerShape(12.dp)).background(Glass)
                    .padding(horizontal = 14.dp, vertical = 8.dp)
            )
        }
        BottomCoachBar(
            state = state,
            onAsk = viewModel::askThea,
            onFinish = viewModel::finishSet,
            onReconnect = viewModel::startLive,
            modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(12.dp)
        )
        state.summary?.let { summary ->
            Column(
                modifier = Modifier.align(Alignment.Center).padding(24.dp).clip(RoundedCornerShape(24.dp)).background(Glass)
                    .border(1.dp, if (summary.passed) Volt else Amber, RoundedCornerShape(24.dp)).padding(22.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(if (summary.passed) "SET COMPLETE" else "SET SAVED",
                    style = MaterialTheme.typography.labelLarge.copy(letterSpacing = 1.4.sp, fontWeight = FontWeight.Black),
                    color = if (summary.passed) Volt else Amber)
                Text(summary.summary, style = MaterialTheme.typography.bodyLarge, color = TextPrimaryWhite, textAlign = TextAlign.Center)
                Button(onClick = viewModel::openSummary,
                    colors = ButtonDefaults.buttonColors(containerColor = Volt, contentColor = BackgroundOnyx)) {
                    Text("View set breakdown", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun TopHud(state: LiveUiState, onBack: () -> Unit, onFlip: () -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(Glass)
                .border(1.dp, Color.White.copy(alpha = 0.08f), RoundedCornerShape(20.dp)).padding(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack, modifier = Modifier.size(36.dp)) {
                Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Back", tint = TextPrimaryWhite)
            }
            Column(Modifier.weight(1f).padding(horizontal = 6.dp)) {
                Text(
                    state.drillTitle ?: "Live coach",
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                    color = TextPrimaryWhite, maxLines = 1
                )
                Text(
                    "${state.validReps} / ${state.targetReps} quality reps" +
                        (state.targetStroke?.let { " · ${it.replace('_', ' ')}" } ?: "") +
                        (if (state.sequence.size > 1) " · combo" else ""),
                    style = MaterialTheme.typography.labelSmall, color = TextSecondarySilver, maxLines = 1
                )
            }
            IconButton(onClick = onFlip, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Rounded.Cameraswitch, contentDescription = "Switch camera", tint = TextPrimaryWhite)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            ConnectionPill(state.connection)
            if (state.isStreaming) Badge("${state.sentFps} FPS")
            state.heartRate?.let { hr ->
                Row(Modifier.clip(RoundedCornerShape(10.dp)).background(Glass).padding(horizontal = 8.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Favorite, contentDescription = null, tint = ErrorRed, modifier = Modifier.size(12.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("$hr bpm", style = MaterialTheme.typography.labelSmall, color = TextPrimaryWhite)
                }
            }
        }
        PhaseStrip(state.phase)
    }
}

@Composable
private fun ConnectionPill(connection: LiveConnection) {
    val pulse by rememberInfiniteTransition(label = "livePulse").animateFloat(
        initialValue = 0.35f, targetValue = 1f, animationSpec = infiniteRepeatable(tween(800), RepeatMode.Reverse),
        label = "liveDot")
    val (label, color) = when (connection) {
        LiveConnection.LIVE -> "LIVE COACH ACTIVE" to LiveGreen
        LiveConnection.CONNECTING -> "CONNECTING" to TextSecondarySilver
        LiveConnection.ERROR -> "OFFLINE" to ErrorRed
        LiveConnection.DISCONNECTED -> "PAUSED" to TextMuted
    }
    Row(Modifier.clip(RoundedCornerShape(10.dp)).background(Glass).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color.copy(alpha = if (connection == LiveConnection.LIVE) pulse else 1f)))
        Spacer(Modifier.width(6.dp))
        Text(label, style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold), color = color)
    }
}

@Composable
private fun Badge(text: String) {
    Text(text, style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold), color = TextPrimaryWhite,
        modifier = Modifier.clip(RoundedCornerShape(10.dp)).background(Glass).padding(horizontal = 8.dp, vertical = 5.dp))
}

@Composable
private fun PhaseStrip(phase: RepPhase) {
    val steps = listOf("READY", "LOAD", "IMPACT", "RECOVER")
    Row(Modifier.clip(RoundedCornerShape(12.dp)).background(Glass).padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        steps.forEach { step ->
            val active = phase.label == step
            Text(step, style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Black, letterSpacing = 0.8.sp),
                color = if (active) BackgroundOnyx else TextSecondarySilver,
                modifier = Modifier.clip(RoundedCornerShape(8.dp)).background(if (active) Volt else Color.Transparent)
                    .padding(horizontal = 10.dp, vertical = 5.dp))
        }
    }
}

@Composable
private fun BottomCoachBar(state: LiveUiState, onAsk: (String) -> Unit, onFinish: () -> Unit, onReconnect: () -> Unit,
                           modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Glass)
            .border(1.dp, Color.White.copy(alpha = 0.08f), RoundedCornerShape(24.dp)).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            RepRing(state.validReps, state.targetReps)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                state.lastRep?.let { rep ->
                    Text(
                        "${rep.quality}%" + (rep.proMatch?.let { " · Match: $it" } ?: ""),
                        style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
                        color = if (rep.counted) Volt else Amber
                    )
                }
                Text(state.subtitle, style = MaterialTheme.typography.bodyMedium, color = TextPrimaryWhite, maxLines = 3)
                state.driftMessage?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = Amber, maxLines = 2)
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            VoiceMicButton(channel = "live", size = 52.dp, showCaption = false, onTranscript = onAsk)
            Text("Talk to Thea", style = MaterialTheme.typography.labelLarge, color = TextSecondarySilver, modifier = Modifier.weight(1f))
            when (state.connection) {
                LiveConnection.LIVE -> Button(
                    onClick = onFinish, enabled = !state.isSaving && state.summary == null,
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Volt, contentColor = BackgroundOnyx)
                ) {
                    if (state.isSaving) CircularProgressIndicator(Modifier.size(18.dp), color = BackgroundOnyx, strokeWidth = 2.dp)
                    else Text("Finish & Save Set", fontWeight = FontWeight.Bold)
                }
                LiveConnection.CONNECTING -> CircularProgressIndicator(Modifier.size(24.dp), color = Volt, strokeWidth = 2.dp)
                else -> OutlinedButton(onClick = onReconnect, border = BorderStroke(1.dp, Volt)) {
                    Text("Reconnect", color = Volt, fontWeight = FontWeight.Bold)
                }
            }
        }
        state.statusMessage?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = TextSecondarySilver) }
    }
}

@Composable
private fun RepRing(valid: Int, target: Int) {
    val progress by animateFloatAsState(targetValue = if (target > 0) (valid.toFloat() / target).coerceIn(0f, 1f) else 0f,
        animationSpec = tween(500), label = "repRing")
    Box(Modifier.size(76.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = 8.dp.toPx()
            drawArc(Color.White.copy(alpha = 0.12f), 0f, 360f, false, style = Stroke(stroke))
            drawArc(Volt, -90f, 360f * progress, false, style = Stroke(stroke, cap = StrokeCap.Round))
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("$valid", style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Black), color = TextPrimaryWhite)
            Text("of $target", style = MaterialTheme.typography.labelSmall, color = TextSecondarySilver)
        }
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

/**
 * Skeleton in Neon Volt; the hitting elbow/shoulder in Cyan when within the level target, Amber when
 * close, Red when well short (judged at impact). Coordinates follow PreviewView's FILL_CENTER crop.
 */
@Composable
private fun SkeletonOverlay(pose: LivePose?, mirror: Boolean, state: LiveUiState, modifier: Modifier = Modifier) {
    val elbow = state.elbowDeg
    val threshold = state.thresholdDeg
    val jointColor = when {
        elbow == null || threshold == null || state.phase == RepPhase.READY -> Cyan
        elbow >= threshold -> Cyan
        elbow >= threshold - 10 -> Amber
        else -> ErrorRed
    }
    val left = state.handedness == "left"
    val elbowIdx = if (left) 13 else 14
    val shoulderIdx = if (left) 11 else 12
    Box(modifier) {
        Canvas(Modifier.fillMaxSize()) {
            val landmarks = pose?.landmarks ?: return@Canvas
            val aspect = pose.aspect.coerceAtLeast(0.1f)
            val scale = max(size.width / aspect, size.height)
            val offX = (size.width - aspect * scale) / 2f
            val offY = (size.height - scale) / 2f
            fun point(i: Int): Offset? {
                val lm = landmarks.getOrNull(i) ?: return null
                if (lm[3] < MIN_VISIBILITY) return null
                val x = if (mirror) 1f - lm[0] else lm[0]
                return Offset(offX + x * aspect * scale, offY + lm[1] * scale)
            }
            POSE_EDGES.forEach { (a, b) ->
                val p1 = point(a)
                val p2 = point(b)
                if (p1 != null && p2 != null) {
                    val hot = (a == shoulderIdx && b == elbowIdx) || (a == elbowIdx && b == elbowIdx + 2)
                    drawLine(if (hot) jointColor else Volt, p1, p2, strokeWidth = (if (hot) 7 else 5).dp.toPx(), cap = StrokeCap.Round)
                }
            }
            (11..32).forEach { i ->
                point(i)?.let { drawCircle(if (i == elbowIdx || i == shoulderIdx) jointColor else Color.White,
                    radius = (if (i == elbowIdx) 8 else 4).dp.toPx(), center = it) }
            }
        }
        // Floating angle readout next to the hitting elbow.
        val lm = pose?.landmarks?.getOrNull(elbowIdx)
        if (lm != null && lm[3] >= MIN_VISIBILITY && elbow != null) {
            ElbowLabel(elbow, threshold, jointColor, lm, pose.aspect, mirror)
        }
    }
}

@Composable
private fun ElbowLabel(elbow: Double, threshold: Double?, color: Color, lm: FloatArray, aspect: Float, mirror: Boolean) {
    androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxSize()) {
        val w = constraints.maxWidth.toFloat()
        val h = constraints.maxHeight.toFloat()
        val a = aspect.coerceAtLeast(0.1f)
        val scale = max(w / a, h)
        val x = (w - a * scale) / 2f + (if (mirror) 1f - lm[0] else lm[0]) * a * scale
        val y = (h - scale) / 2f + lm[1] * scale
        val density = androidx.compose.ui.platform.LocalDensity.current
        Text(
            "${elbow.roundToInt()}°" + (threshold?.let { " / ${it.roundToInt()}°" } ?: ""),
            style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Black),
            color = BackgroundOnyx,
            modifier = Modifier
                .padding(start = with(density) { (x + 14f).toDp() }.coerceAtLeast(0.dp),
                    top = with(density) { (y - 14f).toDp() }.coerceAtLeast(0.dp))
                .clip(RoundedCornerShape(8.dp)).background(color).padding(horizontal = 6.dp, vertical = 2.dp)
        )
    }
}
