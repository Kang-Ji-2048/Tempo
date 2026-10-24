package com.tempo.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Bluetooth
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.Notifications
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material.icons.rounded.SmartToy
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.feature.onboarding.OnboardingNavigationEvent
import com.tempo.app.feature.onboarding.OnboardingViewModel
import com.tempo.app.feature.sdui.ui.WidgetRenderer
import com.tempo.app.network.models.UserProfileDto
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import kotlin.math.roundToInt

@Composable
fun OnboardingScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: OnboardingViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    // Handle navigation event to Home
    LaunchedEffect(Unit) {
        viewModel.navigationEvents.collect { event ->
            when (event) {
                is OnboardingNavigationEvent.NavigateToHome -> {
                    navController.navigate(Screen.Home.route) {
                        popUpTo(Screen.Onboarding.route) { inclusive = true }
                    }
                }
            }
        }
    }

    val animatedProgress by animateFloatAsState(
        targetValue = uiState.progress.coerceIn(0.05f, 1.0f),
        label = "onboardingProgress"
    )

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Top Header: Step label + Progress bar
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = if (uiState.isCompleted) "CALIBRATION COMPLETE" else "ATHLETE ONBOARDING",
                    style = MaterialTheme.typography.labelLarge,
                    color = AccentNeonVolt,
                    letterSpacing = 1.2.sp
                )
                Text(
                    text = "${(animatedProgress * 100).roundToInt()}%",
                    style = MaterialTheme.typography.labelLarge,
                    color = TextSecondarySilver,
                    fontWeight = FontWeight.Bold
                )
            }

            LinearProgressIndicator(
                progress = { animatedProgress },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp)),
                color = AccentNeonVolt,
                trackColor = SurfaceVariantDark
            )
        }

        // Conversational AI Coach Bubble
        CoachSpeechHeader(message = uiState.coachMessage)

        // Animated Content: Switches dynamically as stepId changes
        AnimatedContent(
            targetState = uiState.stepId,
            transitionSpec = {
                (slideInHorizontally { width -> width } + fadeIn()).togetherWith(
                    slideOutHorizontally { width -> -width } + fadeOut()
                )
            },
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            label = "stepTransition"
        ) { targetStep ->
            if (uiState.isCompleted) {
                // Final Step: Profile Summary + Friendly Runtime Permissions
                PermissionsAndSummaryView(
                    userProfile = uiState.userProfile,
                    onComplete = { permissionsGranted ->
                        viewModel.completeOnboardingAndSave(permissionsGranted)
                    }
                )
            } else {
                // SDUI Widget Step
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState()),
                    contentAlignment = Alignment.TopCenter
                ) {
                    if (uiState.currentWidget != null) {
                        WidgetRenderer(
                            widget = uiState.currentWidget!!,
                            onAction = { action -> viewModel.onWidgetAction(action) },
                            modifier = Modifier.fillMaxWidth()
                        )
                    } else if (uiState.isLoading) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(200.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            CircularProgressIndicator(color = AccentNeonVolt)
                        }
                    } else if (uiState.errorMessage != null) {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                            border = BorderStroke(1.dp, CardBorderSubtle)
                        ) {
                            Column(
                                modifier = Modifier.padding(20.dp),
                                horizontalAlignment = Alignment.CenterHorizontally
                            ) {
                                Text(
                                    text = uiState.errorMessage ?: "An error occurred",
                                    color = TextSecondarySilver,
                                    fontSize = 14.sp
                                )
                                Spacer(modifier = Modifier.height(12.dp))
                                Button(
                                    onClick = { viewModel.loadInitialStep() },
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = AccentNeonVolt,
                                        contentColor = BackgroundOnyx
                                    )
                                ) {
                                    Text("Retry Connection")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CoachSpeechHeader(message: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, CardBorderSubtle)
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.Top
        ) {
            Box(
                modifier = Modifier
                    .size(44.dp)
                    .clip(CircleShape)
                    .background(AccentNeonVolt),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Rounded.SmartToy,
                    contentDescription = "Tempo Coach",
                    tint = BackgroundOnyx,
                    modifier = Modifier.size(24.dp)
                )
            }
            Spacer(modifier = Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "COACH TEMPO",
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = AccentNeonVolt,
                    letterSpacing = 1.sp
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextPrimaryWhite,
                    lineHeight = 20.sp
                )
            }
        }
    }
}

@Composable
private fun PermissionsAndSummaryView(
    userProfile: UserProfileDto?,
    onComplete: (Boolean) -> Unit
) {
    val context = LocalContext.current

    // Runtime permissions for Pixel 10 Pro / modern Android
    val permissionsToRequest = remember {
        val list = mutableListOf(
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            list.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            list.add(Manifest.permission.BLUETOOTH_CONNECT)
            list.add(Manifest.permission.BLUETOOTH_SCAN)
        }
        list
    }

    var permissionStatusMap by remember {
        mutableStateOf(
            permissionsToRequest.associateWith { perm ->
                ContextCompat.checkSelfPermission(context, perm) == PackageManager.PERMISSION_GRANTED
            }
        )
    }

    val healthConnectManager = remember { com.tempo.app.feature.biometrics.HealthConnectManager(context) }
    var healthConnectAvailable by remember { mutableStateOf(healthConnectManager.isAvailable()) }
    var healthConnectGranted by remember { mutableStateOf(false) }

    val healthConnectLauncher = rememberLauncherForActivityResult(
        contract = androidx.health.connect.client.PermissionController.createRequestPermissionResultContract()
    ) { grantedPermissions ->
        healthConnectGranted = grantedPermissions.containsAll(healthConnectManager.permissions)
    }

    LaunchedEffect(Unit) {
        if (healthConnectAvailable) {
            healthConnectGranted = healthConnectManager.hasPermissions()
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        permissionStatusMap = results
        if (healthConnectAvailable && !healthConnectGranted) {
            healthConnectLauncher.launch(healthConnectManager.permissions)
        }
    }

    val allHardwareGranted = permissionStatusMap.values.all { it }
    val allPermissionsGranted = allHardwareGranted && (!healthConnectAvailable || healthConnectGranted)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Athlete Blueprint Profile Summary Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.5.dp, AccentNeonVolt.copy(alpha = 0.5f))
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "ATHLETE PROFILE SUMMARY",
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        color = AccentNeonVolt,
                        letterSpacing = 1.2.sp
                    )
                    Text(
                        text = "Calibrated",
                        fontSize = 12.sp,
                        color = AccentNeonVolt,
                        fontWeight = FontWeight.SemiBold
                    )
                }

                val sportName = userProfile?.sport?.replaceFirstChar { it.uppercase() } ?: "Selected Sport"
                val archetype = userProfile?.targetArchetype?.ifBlank { "Pro Benchmark" } ?: "Pro Benchmark"
                val playstyle = userProfile?.playstyle?.replaceFirstChar { it.uppercase() } ?: "Aggressive"
                val level = userProfile?.level?.replaceFirstChar { it.uppercase() } ?: "Intermediate"
                val goal = userProfile?.goal?.replace("_", " ")?.replaceFirstChar { it.uppercase() } ?: "Overhead Power"

                Text(
                    text = "$sportName • $archetype Benchmark",
                    style = MaterialTheme.typography.titleLarge,
                    color = TextPrimaryWhite
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    ProfileBadge(label = "$playstyle Style")
                    ProfileBadge(label = level)
                    ProfileBadge(label = goal)
                }
            }
        }

        // Friendly Runtime Permissions Section
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                Text(
                    text = "HARDWARE & SENSOR PERMISSIONS",
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = AccentNeonVolt,
                    letterSpacing = 1.2.sp
                )

                Text(
                    text = "Tempo operates in real-time on your Pixel. Grant the permissions below for full edge analysis:",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondarySilver
                )

                // 1. Camera
                val cameraGranted = permissionStatusMap[Manifest.permission.CAMERA] == true
                PermissionRow(
                    icon = Icons.Rounded.Videocam,
                    title = "Camera",
                    reason = "Record 60fps video for 33-landmark pose Landmarker analysis",
                    granted = cameraGranted
                )

                // 2. Microphone
                val micGranted = permissionStatusMap[Manifest.permission.RECORD_AUDIO] == true
                PermissionRow(
                    icon = Icons.Rounded.Mic,
                    title = "Microphone",
                    reason = "Detect shuttle/ball impact acoustic transients to sync stroke timing",
                    granted = micGranted
                )

                // 3. Bluetooth
                val btGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    permissionStatusMap[Manifest.permission.BLUETOOTH_CONNECT] == true
                } else {
                    true
                }
                PermissionRow(
                    icon = Icons.Rounded.Bluetooth,
                    title = "Bluetooth",
                    reason = "Connect to smart racket sensors and wearable heart-rate monitors",
                    granted = btGranted
                )

                // 4. Notifications
                val notifGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    permissionStatusMap[Manifest.permission.POST_NOTIFICATIONS] == true
                } else {
                    true
                }
                PermissionRow(
                    icon = Icons.Rounded.Notifications,
                    title = "Notifications",
                    reason = "Receive executive coaching briefs and practice cadence reminders",
                    granted = notifGranted
                )

                // 5. Health Connect
                if (!healthConnectAvailable) {
                    PermissionRow(
                        icon = Icons.Rounded.Favorite,
                        title = "Health Connect",
                        reason = "Health Connect not available on this device",
                        granted = false,
                        onToggle = null
                    )
                } else {
                    PermissionRow(
                        icon = Icons.Rounded.Favorite,
                        title = "Health Connect",
                        reason = "Correlate cardiovascular fatigue and strain with kinematic breakdown",
                        granted = healthConnectGranted,
                        onToggle = {
                            if (!healthConnectGranted) {
                                healthConnectLauncher.launch(healthConnectManager.permissions)
                            }
                        }
                    )
                }
            }
        }

        // Action Buttons: Grant All / Enter Home
        if (!allHardwareGranted) {
            Button(
                onClick = {
                    permissionLauncher.launch(permissionsToRequest.toTypedArray())
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(16.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = AccentNeonVolt,
                    contentColor = BackgroundOnyx
                )
            ) {
                Icon(Icons.Rounded.Shield, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Grant All Permissions",
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp
                )
            }
        }

        Button(
            onClick = {
                onComplete(allPermissionsGranted)
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(54.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (allHardwareGranted) AccentNeonVolt else SurfaceVariantDark,
                contentColor = if (allHardwareGranted) BackgroundOnyx else TextPrimaryWhite
            )
        ) {
            Text(
                text = "Enter Tempo & Begin Training",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )
            Spacer(modifier = Modifier.width(8.dp))
            Icon(Icons.Rounded.ArrowForward, contentDescription = null, modifier = Modifier.size(18.dp))
        }

        Spacer(modifier = Modifier.height(16.dp))
    }
}

@Composable
private fun ProfileBadge(label: String) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(SurfaceVariantDark)
            .padding(horizontal = 10.dp, vertical = 6.dp)
    ) {
        Text(
            text = label,
            fontSize = 12.sp,
            color = AccentNeonVolt,
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
private fun PermissionRow(
    icon: ImageVector,
    title: String,
    reason: String,
    granted: Boolean,
    onToggle: (() -> Unit)? = null
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(if (granted) AccentNeonVolt.copy(alpha = 0.15f) else SurfaceVariantDark),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = if (granted) AccentNeonVolt else TextSecondarySilver,
                modifier = Modifier.size(20.dp)
            )
        }

        Spacer(modifier = Modifier.width(12.dp))

        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
                color = TextPrimaryWhite
            )
            Text(
                text = reason,
                fontSize = 12.sp,
                color = TextSecondarySilver,
                lineHeight = 16.sp
            )
        }

        Spacer(modifier = Modifier.width(8.dp))

        if (granted) {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(12.dp))
                    .background(AccentNeonVolt.copy(alpha = 0.2f))
                    .padding(horizontal = 10.dp, vertical = 4.dp),
                contentAlignment = Alignment.Center
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Rounded.Check,
                        contentDescription = null,
                        tint = AccentNeonVolt,
                        modifier = Modifier.size(14.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "Granted",
                        color = AccentNeonVolt,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        } else {
            OutlinedButton(
                onClick = { onToggle?.invoke() },
                modifier = Modifier.height(32.dp),
                border = BorderStroke(1.dp, CardBorderSubtle),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = TextSecondarySilver)
            ) {
                Text(text = "Needed", fontSize = 11.sp)
            }
        }
    }
}
