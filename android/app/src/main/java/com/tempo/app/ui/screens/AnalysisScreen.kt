package com.tempo.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Lightbulb
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.SportsScore
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.feature.analysis.AnalysisStep
import com.tempo.app.feature.analysis.AnalysisViewModel
import com.tempo.app.feature.analysis.BiomechanicalDebrief
import com.tempo.app.feature.analysis.ui.AnalysisStepper
import com.tempo.app.feature.audio.ui.DebriefPlayer
import com.tempo.app.feature.correction.ui.KeyframeStripView
import com.tempo.app.feature.correction.ui.VisualCorrectionPlayer
import com.tempo.app.feature.sdui.ui.WidgetRenderer
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
fun AnalysisScreen(
    sessionId: String,
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: AnalysisViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Spacer(modifier = Modifier.height(24.dp))
            // Navigation Bar Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(
                    onClick = { navController.navigate(Screen.Home.route) },
                    modifier = Modifier
                        .size(40.dp)
                        .clip(CircleShape)
                        .background(SurfaceCharcoal)
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Rounded.ArrowBack,
                        contentDescription = "Back",
                        tint = TextPrimaryWhite
                    )
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(
                        text = "BIOMECHANICAL PIPELINE",
                        style = MaterialTheme.typography.labelSmall.copy(
                            letterSpacing = 1.2.sp,
                            fontWeight = FontWeight.Bold
                        ),
                        color = AccentNeonVolt
                    )
                    Text(
                        text = "Practice Debrief",
                        style = MaterialTheme.typography.titleLarge.copy(
                            fontWeight = FontWeight.Bold
                        ),
                        color = TextPrimaryWhite
                    )
                }
            }
        }

        // Stepper Card (Always visible showing PENDING / ANALYZING / COMPLETED)
        item {
            AnalysisStepper(
                currentStep = uiState.step,
                statusCopy = uiState.statusCopy
            )
        }

        // FAILED State with Retry Option
        if (uiState.step == AnalysisStep.FAILED) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(20.dp),
                    colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                    border = BorderStroke(1.dp, ErrorRed.copy(alpha = 0.5f))
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(56.dp)
                                .clip(CircleShape)
                                .background(ErrorRed.copy(alpha = 0.16f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.ErrorOutline,
                                contentDescription = null,
                                tint = ErrorRed,
                                modifier = Modifier.size(28.dp)
                            )
                        }
                        Text(
                            text = "Analysis Encountered an Issue",
                            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                            color = TextPrimaryWhite
                        )
                        Text(
                            text = uiState.errorMessage
                                ?: "The video could not be fully analyzed. Ensure adequate lighting and full body visibility.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondarySilver
                        )
                        Spacer(Modifier.height(4.dp))
                        Button(
                            onClick = { viewModel.retry() },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(50.dp),
                            shape = RoundedCornerShape(14.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = AccentNeonVolt,
                                contentColor = BackgroundOnyx
                            )
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.Refresh,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = "Retry",
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
            }
        }

        // COMPLETED State: Overall Score & Primary Flaw Header
        if (uiState.step == AnalysisStep.COMPLETED && uiState.debrief != null) {
            item {
                DebriefHeaderCard(debrief = uiState.debrief!!)
            }

            // Coach Voice Debrief Player (Media3 ExoPlayer / TTS fallback + Bluetooth earbud routing)
            item {
                DebriefPlayer(
                    voiceNoteUrl = uiState.debrief!!.voiceNoteUrl,
                    voiceNoteScript = uiState.debrief!!.voiceNoteScript,
                    autoOffer = true
                )
            }

            uiState.feedbackNotice?.let { message ->
                item { Text(message, color = TextSecondarySilver) }
            }
            uiState.visualCorrectionMessage?.let { message ->
                item { Text(message, color = TextSecondarySilver) }
            }
            // Visual Correction Motion Player with 33-Landmark Pose Overlay & Scrub Bar
            item {
                VisualCorrectionPlayer(
                    videoPath = uiState.videoPath,
                    poseTrack = uiState.poseTrack,
                    phases = uiState.kineticPhases
                )
            }

            // Horizontally Scrollable Kinetic Phase Strip (4 phases with dual skeleton & deviations)
            if (uiState.keyframeComparisons.isNotEmpty()) {
                item {
                    KeyframeStripView(
                        comparisons = uiState.keyframeComparisons,
                        onPhaseClicked = { phase ->
                            // Tapping card focuses phase in player
                        }
                    )
                }
            }
            if (uiState.widgets.isNotEmpty()) {
                item {
                    Text(
                        text = "PRESCRIPTION & PROGRESS",
                        style = MaterialTheme.typography.labelSmall.copy(
                            letterSpacing = 1.2.sp,
                            fontWeight = FontWeight.Bold
                        ),
                        color = AccentNeonVolt,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }

                items(uiState.widgets, key = { it.key }) { widget ->
                    WidgetRenderer(
                        widget = widget,
                        onAction = { action -> viewModel.onWidgetAction(action) }
                    )
                }
            }
        }

        item {
            Spacer(Modifier.height(12.dp))
            OutlinedButton(
                onClick = { navController.navigate(Screen.Home.route) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(14.dp),
                border = BorderStroke(1.dp, CardBorderSubtle)
            ) {
                Text(
                    text = "Return to Home",
                    style = MaterialTheme.typography.labelLarge,
                    color = TextSecondarySilver
                )
            }
            Spacer(Modifier.height(32.dp))
        }
    }
}

@Composable
private fun DebriefHeaderCard(
    debrief: BiomechanicalDebrief,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, CardBorderSubtle)
    ) {
        Column(
            modifier = Modifier.padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Overall score + Benchmark
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "OVERALL MASTERY",
                        style = MaterialTheme.typography.labelSmall.copy(
                            letterSpacing = 1.2.sp,
                            fontWeight = FontWeight.Bold
                        ),
                        color = TextMuted
                    )
                    Spacer(Modifier.height(4.dp))
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(
                            text = debrief.overallScore?.toString() ?: "Unavailable",
                            fontSize = 44.sp,
                            fontWeight = FontWeight.Black,
                            color = AccentNeonVolt,
                            lineHeight = 44.sp
                        )
                        Text(
                            text = if (debrief.overallScore != null) " / 100" else "",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = TextMuted,
                            modifier = Modifier.padding(bottom = 6.dp)
                        )
                    }
                }

                if (debrief.matchedArchetype != null) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .background(SurfaceVariantDark)
                            .border(1.dp, CardBorderSubtle, RoundedCornerShape(12.dp))
                            .padding(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        Text(
                            text = "Benchmark: ${debrief.matchedArchetype}",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = TextPrimaryWhite
                        )
                    }
                }
            }

            // High-contrast Callout: The One Primary Flaw
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(16.dp))
                    .background(Color(0xFF2C1E14))
                    .border(1.dp, Color(0xFF8B4513), RoundedCornerShape(16.dp))
                    .padding(16.dp)
            ) {
                Row(verticalAlignment = Alignment.Top) {
                    Box(
                        modifier = Modifier
                            .size(32.dp)
                            .clip(CircleShape)
                            .background(Color(0xFFE65100).copy(alpha = 0.2f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.Lightbulb,
                            contentDescription = null,
                            tint = Color(0xFFFF9800),
                            modifier = Modifier.size(18.dp)
                        )
                    }
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(
                            text = "PRIMARY TECHNIQUE FLAW",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFFF9800),
                            letterSpacing = 1.sp
                        )
                        Spacer(Modifier.height(2.dp))
                        Text(
                            text = debrief.primaryFlaw,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = TextPrimaryWhite
                        )
                    }
                }
            }

            // Audio Coaching Cue
            if (!debrief.audioCue.isNullOrBlank()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(SurfaceVariantDark)
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Rounded.SportsScore,
                        contentDescription = null,
                        tint = AccentNeonVolt,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.width(10.dp))
                    Text(
                        text = debrief.audioCue,
                        fontSize = 13.sp,
                        color = TextSecondarySilver,
                        fontWeight = FontWeight.Medium
                    )
                }
            }
        }
    }
}
