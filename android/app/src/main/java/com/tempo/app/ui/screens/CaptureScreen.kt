package com.tempo.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.FiberManualRecord
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
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
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import androidx.camera.view.PreviewView
import com.tempo.app.feature.capture.CaptureViewModel
import com.tempo.app.feature.capture.analyzer.PosePreflightAnalyzer
import com.tempo.app.feature.capture.camera.CameraCaptureManager
import com.tempo.app.feature.capture.model.CaptureUiState
import com.tempo.app.feature.capture.model.PreflightCheck
import com.tempo.app.feature.capture.ui.ClipReviewScreen
import com.tempo.app.feature.capture.ui.CountdownOverlay
import com.tempo.app.feature.capture.ui.FramingSilhouetteOverlay
import com.tempo.app.feature.capture.ui.PermissionRationaleView
import com.tempo.app.feature.capture.ui.PreflightStatusChips
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun CaptureScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: CaptureViewModel = hiltViewModel(),
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val playerId by viewModel.playerId.collectAsStateWithLifecycle()
    val accessToken by viewModel.accessToken.collectAsStateWithLifecycle()

    val requiredPermissions = remember {
        arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions(),
    ) { perms ->
        val cameraGranted = perms[Manifest.permission.CAMERA] == true
        if (cameraGranted) {
            viewModel.onPermissionsGranted()
        } else {
            val missing = perms.filterValues { !it }.keys.toList()
            viewModel.onPermissionsDenied(missing)
        }
    }

    // Check permissions on enter
    LaunchedEffect(Unit) {
        val allGranted = requiredPermissions.all {
            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
        }
        if (!allGranted) {
            permissionLauncher.launch(requiredPermissions)
        } else {
            viewModel.onPermissionsGranted()
        }
    }

    when (val state = uiState) {
        is CaptureUiState.PermissionRequired -> {
            PermissionRationaleView(
                onRequestPermissions = { permissionLauncher.launch(requiredPermissions) },
                modifier = modifier,
            )
        }

        is CaptureUiState.Review -> {
            ClipReviewScreen(
                videoPath = state.videoPath,
                promptTitle = state.prompt.title,
                accessToken = accessToken,
                onAccessTokenChanged = viewModel::setAccessToken,
                playerId = playerId,
                onPlayerIdChanged = viewModel::setPlayerId,
                onUseClip = {
                    val sessionId = java.util.UUID.randomUUID().toString()
                    com.tempo.app.feature.ingestion.work.IngestionScheduler.scheduleUpload(
                        context = context,
                        sessionId = sessionId,
                        videoPath = state.videoPath,
                        sport = "badminton",
                        strokeType = "overhead_clear",
                        targetArchetype = "Axelsen",
                        userIntent = state.prompt.title,
                        userId = playerId.trim(),
                        startMs = viewModel.recordingStartMs,
                        endMs = viewModel.recordingEndMs
                    )
                    navController.navigate(Screen.Analysis.createRoute(sessionId))
                },
                onRetake = { viewModel.retake(state.videoPath) },
                modifier = modifier,
            )
        }

        is CaptureUiState.ClipSaved -> {
            ClipSavedView(
                videoPath = state.videoPath,
                onViewAnalysis = {
                    val sessionId = java.util.UUID.randomUUID().toString()
                    com.tempo.app.feature.ingestion.work.IngestionScheduler.scheduleUpload(
                        context = context,
                        sessionId = sessionId,
                        videoPath = state.videoPath,
                        sport = "badminton",
                        strokeType = "overhead_clear",
                        targetArchetype = "Axelsen",
                        userIntent = state.prompt.title,
                        userId = playerId.trim(),
                        startMs = viewModel.recordingStartMs,
                        endMs = viewModel.recordingEndMs
                    )
                    navController.navigate(Screen.Analysis.createRoute(sessionId))
                },
                onRecordAnother = { viewModel.retake(state.videoPath) },
                modifier = modifier,
            )
        }

        is CaptureUiState.Preflight,
        is CaptureUiState.CountingDown,
        is CaptureUiState.Recording -> {
            val prompt = when (state) {
                is CaptureUiState.Preflight -> state.prompt
                is CaptureUiState.CountingDown -> state.prompt
                is CaptureUiState.Recording -> state.prompt
                else -> CaptureViewModel.DEFAULT_PROMPT
            }
            val targetFps = when (state) {
                is CaptureUiState.Preflight -> state.targetFps
                is CaptureUiState.CountingDown -> state.targetFps
                is CaptureUiState.Recording -> state.targetFps
                else -> 30
            }
            val fpsBadge = when (state) {
                is CaptureUiState.Preflight -> state.fpsBadge
                else -> "$targetFps FPS"
            }
            val preflightCheck = (state as? CaptureUiState.Preflight)?.preflight

            // Initialize CameraCaptureManager and PosePreflightAnalyzer
            val previewView = remember { PreviewView(context) }
            val analyzer = remember {
                PosePreflightAnalyzer(context) { check ->
                    viewModel.onPreflightUpdated(check)
                }
            }

            val cameraManager = remember {
                CameraCaptureManager(
                    context = context,
                    lifecycleOwner = lifecycleOwner,
                    onFpsDetermined = { fps -> viewModel.onFpsDetermined(fps) },
                    onRecordingStarted = {
                        // Will trigger auto-stop when elapsed reaches durationS
                    },
                    onRecordingFinalized = { file -> viewModel.onRecordingFinalized(file) },
                    onRecordingError = { _ -> },
                )
            }

            // Start camera lifecycle
            LaunchedEffect(lifecycleOwner) {
                cameraManager.startCamera(previewView, analyzer)
            }

            DisposableEffect(Unit) {
                onDispose {
                    analyzer.close()
                    cameraManager.release()
                }
            }

            Box(
                modifier = modifier
                    .fillMaxSize()
                    .background(BackgroundOnyx),
            ) {
                // 1. Live Camera Preview View
                AndroidView(
                    factory = { previewView },
                    modifier = Modifier.fillMaxSize(),
                )

                // 2. Framing Guide Silhouette Overlay
                FramingSilhouetteOverlay(
                    cameraHint = prompt.cameraHint,
                    isBodyInFrame = preflightCheck?.bodyVisible == true,
                    modifier = Modifier.fillMaxSize(),
                )

                // Top Header Gradient Overlay with prompt and preflight chips
                Column(
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .fillMaxWidth()
                        .background(
                            Brush.verticalGradient(
                                listOf(BackgroundOnyx.copy(alpha = 0.90f), Color.Transparent),
                            ),
                        )
                        .padding(top = 40.dp, start = 16.dp, end = 16.dp, bottom = 20.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        IconButton(onClick = { navController.popBackStack() }) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Rounded.ArrowBack,
                                contentDescription = "Back",
                                tint = TextPrimaryWhite,
                            )
                        }
                        Spacer(Modifier.width(4.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                text = "COACH PRACTICE SET",
                                color = AccentNeonVolt,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 1.2.sp,
                            )
                            Text(
                                text = prompt.title,
                                color = TextPrimaryWhite,
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold,
                                maxLines = 1,
                            )
                        }
                    }

                    // Pre-flight status chips row
                    if (preflightCheck != null && state is CaptureUiState.Preflight) {
                        PreflightStatusChips(
                            check = preflightCheck,
                            fpsBadge = fpsBadge,
                            onDebugSimulatePass = if (com.tempo.app.BuildConfig.DEBUG) {
                                {
                                    viewModel.onPreflightUpdated(
                                        PreflightCheck(
                                            bodyVisible = true,
                                            lightingOk = true,
                                            distanceOk = true,
                                            bodyHeightFraction = 0.60f,
                                            meanLuminance = 100f,
                                            failureHint = null,
                                        ),
                                    )
                                }
                            } else null,
                        )
                    }
                }

                // Bottom Action Controls Overlay
                Column(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .background(
                            Brush.verticalGradient(
                                listOf(Color.Transparent, BackgroundOnyx.copy(alpha = 0.95f)),
                            ),
                        )
                        .padding(horizontal = 24.dp, vertical = 28.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    when (state) {
                        is CaptureUiState.Preflight -> {
                            val isReady = preflightCheck?.isReady == true
                            val canRecord = isReady || com.tempo.app.BuildConfig.DEBUG
                            val recordButtonBg = if (canRecord) AccentNeonVolt else SurfaceVariantDark
                            val recordButtonTint = if (canRecord) BackgroundOnyx else TextMuted

                            Box(
                                modifier = Modifier
                                    .size(80.dp)
                                    .clip(CircleShape)
                                    .background(recordButtonBg)
                                    .border(
                                        width = 3.dp,
                                        color = if (canRecord) AccentNeonVolt else CardBorderSubtle,
                                        shape = CircleShape,
                                    )
                                    .clickable(enabled = canRecord) {
                                        viewModel.startCountdown {
                                            val hasAudio = ContextCompat.checkSelfPermission(
                                                context,
                                                Manifest.permission.RECORD_AUDIO,
                                            ) == PackageManager.PERMISSION_GRANTED
                                            cameraManager.startRecording(hasAudio)
                                            viewModel.onRecordingStarted {
                                                cameraManager.stopRecording()
                                            }
                                        }
                                    },
                                contentAlignment = Alignment.Center,
                            ) {
                                Icon(
                                    imageVector = Icons.Rounded.FiberManualRecord,
                                    contentDescription = "Record",
                                    tint = recordButtonTint,
                                    modifier = Modifier.size(36.dp),
                                )
                            }

                            Text(
                                text = if (isReady) "Tap to record (${prompt.durationS}s set)" else "Align body with guide to record",
                                color = if (isReady) AccentNeonVolt else TextSecondarySilver,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }

                        is CaptureUiState.Recording -> {
                            // Recording Timer & Manual Stop
                            Row(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(50))
                                    .background(BackgroundOnyx.copy(alpha = 0.85f))
                                    .border(1.dp, ErrorRed, RoundedCornerShape(50))
                                    .padding(horizontal = 16.dp, vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(10.dp)
                                        .clip(CircleShape)
                                        .background(ErrorRed),
                                )
                                Spacer(Modifier.width(8.dp))
                                val elapsed = state.elapsedSeconds
                                val total = state.maxDurationSeconds
                                Text(
                                    text = String.format("REC 00:%02d / 00:%02d", elapsed, total),
                                    color = TextPrimaryWhite,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold,
                                )
                            }

                            // Stop recording button
                            Box(
                                modifier = Modifier
                                    .size(72.dp)
                                    .clip(CircleShape)
                                    .background(ErrorRed)
                                    .clickable {
                                        cameraManager.stopRecording()
                                    },
                                contentAlignment = Alignment.Center,
                            ) {
                                Icon(
                                    imageVector = Icons.Rounded.Stop,
                                    contentDescription = "Stop",
                                    tint = BackgroundOnyx,
                                    modifier = Modifier.size(32.dp),
                                )
                            }
                        }

                        is CaptureUiState.CountingDown -> {
                            // Managed in overlay below
                        }

                        else -> Unit
                    }
                }

                // 3. Countdown Overlay (3-2-1)
                AnimatedVisibility(
                    visible = state is CaptureUiState.CountingDown,
                    enter = fadeIn(),
                    exit = fadeOut(),
                ) {
                    if (state is CaptureUiState.CountingDown) {
                        CountdownOverlay(count = state.count)
                    }
                }
            }
        }
    }
}

@Composable
private fun ClipSavedView(
    videoPath: String,
    onViewAnalysis: () -> Unit,
    onRecordAnother: () -> Unit,
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
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(68.dp)
                        .clip(CircleShape)
                        .background(AccentNeonVolt.copy(alpha = 0.14f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Rounded.CheckCircle,
                        contentDescription = null,
                        tint = AccentNeonVolt,
                        modifier = Modifier.size(36.dp),
                    )
                }

                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "Practice Clip Saved!",
                        style = MaterialTheme.typography.headlineMedium,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text = "Saved to app cache for Gemini biomechanical ingestion pipeline.",
                        color = TextSecondarySilver,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }

                Button(
                    onClick = onViewAnalysis,
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
                        text = "View Biomechanical Debrief",
                        fontWeight = FontWeight.Bold,
                        fontSize = 15.sp,
                    )
                }

                Button(
                    onClick = onRecordAnother,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(50.dp),
                    shape = RoundedCornerShape(16.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = SurfaceVariantDark,
                        contentColor = TextPrimaryWhite,
                    ),
                ) {
                    Text(
                        text = "Record Another Clip",
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}
