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
import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.feature.lesson.LessonRoutes
import com.tempo.app.feature.thea.ContinueWithTheaButton
import com.tempo.app.feature.sdui.ui.WidgetRenderer
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.feature.analysis.CurriculumAdaptationUi
import kotlin.math.abs
import kotlin.math.roundToInt
import com.tempo.app.feature.analysis.ProComparisonUi
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
    val proComparison by viewModel.proComparison.collectAsStateWithLifecycle()
    val adaptation by viewModel.adaptation.collectAsStateWithLifecycle()

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
                        text = "PRACTICE REVIEW",
                        style = MaterialTheme.typography.labelSmall.copy(
                            letterSpacing = 1.2.sp,
                            fontWeight = FontWeight.Bold
                        ),
                        color = AccentNeonVolt
                    )
                    Text(
                        text = "Your session review",
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
                            text = "This session needs another look",
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
            adaptation?.takeIf { it.lessonCompleted || it.remedialAssigned || it.lessonUnchanged }?.let { change ->
                item { AdaptationBanner(change) }
            }
            proComparison?.takeIf { it.angles.isNotEmpty() }?.let { comparison ->
                item { ProComparisonCard(comparison) }
            }
            if (uiState.kineticPhases.isNotEmpty()) {
                item { PhaseBreakdownCard(uiState.kineticPhases) }
            }
            item {
                ContinueWithTheaButton(question = "Can you turn this breakdown into my next session plan?")
            }

            item {
                OutlinedButton(
                    onClick = { navController.navigate(Screen.Saint.route) },
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Plan next session with Saint", color = AccentNeonVolt) }
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
                        text = "YOUR NEXT STEP",
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
                        onAction = { action -> viewModel.onWidgetAction(action) },
                        // "Do This Live": remedial drills open Live mode bound to that drill.
                        onDrillLive = { drill -> navController.navigate(LessonRoutes.live(null, drill.id)) },
                        onDrillUpload = { navController.navigate(Screen.Capture.route) }
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
            val isGemini = debrief.llmSource == "gemini"
            val chipBg = if (isGemini) AccentNeonVolt.copy(alpha = 0.15f) else Color(0xFF3E1212)
            val chipBorder = if (isGemini) AccentNeonVolt.copy(alpha = 0.6f) else Color(0xFFE53935)
            val chipColor = if (isGemini) AccentNeonVolt else Color(0xFFFF8A80)
            val chipText = if (isGemini) {
                "AI: Gemini 4 Argon" + if (debrief.videoUsed == true) " (Video + Pose)" else " (Pose Data)"
            } else {
                "AI: fallback (" + (debrief.llmError?.take(40) ?: "offline / rule-based") + ")"
            }

            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(chipBg)
                    .border(1.dp, chipBorder, RoundedCornerShape(8.dp))
                    .padding(horizontal = 10.dp, vertical = 4.dp)
            ) {
                Text(
                    text = chipText,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = chipColor
                )
            }

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
                            text = "YOUR MAIN FOCUS",
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


@Composable
private fun AdaptationBanner(adaptation: CurriculumAdaptationUi) {
    val passed = adaptation.lessonCompleted
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (passed) AccentNeonVolt.copy(alpha = 0.12f) else SurfaceCharcoal
        ),
        border = BorderStroke(1.dp, if (passed) AccentNeonVolt.copy(alpha = 0.6f) else CardBorderSubtle)
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                text = when {
                    passed -> "LESSON COMPLETE"
                    adaptation.lessonUnchanged -> "LESSON UNCHANGED"
                    else -> "LESSON ADAPTED"
                },
                style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold),
                color = AccentNeonVolt
            )
            Text(
                text = if (passed) {
                    "${adaptation.nodeTitle ?: "This lesson"} passed with ${adaptation.overallScore ?: "-"}/100." +
                        (adaptation.nextNodeTitle?.let { " Unlocked: $it." } ?: " You've finished the path!")
                } else if (adaptation.action == "not_measured") {
                    "Thea couldn't measure your swing in this clip, so your lesson stays where it was. " +
                        "Her filming tips are below; record again side-on with your full body in frame."
                } else if (adaptation.lessonUnchanged) {
                    adaptation.reason ?: "This clip didn't grade your lesson."
                } else {
                    "Score ${adaptation.overallScore ?: "-"}/100. You need ${adaptation.passScore}+ to pass " +
                        "${adaptation.nodeTitle ?: "this lesson"}. A targeted drill and quiz were added below and to Home."
                },
                style = MaterialTheme.typography.bodyMedium,
                color = TextPrimaryWhite
            )
        }
    }
}

@Composable
private fun ProComparisonCard(comparison: ProComparisonUi) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, CardBorderSubtle)
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(
                    text = "YOU vs ${comparison.matchedPro.uppercase()}",
                    style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold),
                    color = AccentNeonVolt
                )
                comparison.similarityScore?.let {
                    Text("${(it * 100).roundToInt()}% similar", style = MaterialTheme.typography.labelSmall, color = TextSecondarySilver)
                }
            }
            Row(modifier = Modifier.fillMaxWidth()) {
                Text("Joint", modifier = Modifier.weight(1.6f), style = MaterialTheme.typography.labelSmall, color = TextMuted)
                Text("You", modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, color = TextMuted)
                Text("Pro", modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, color = TextMuted)
                Text("Delta", modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, color = TextMuted)
            }
            comparison.angles.forEach { angle ->
                val close = abs(angle.deltaDeg) <= 5.0
                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(angle.label, modifier = Modifier.weight(1.6f), style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite)
                    Text("${angle.athleteDeg.roundToInt()}°", modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite, fontWeight = FontWeight.Bold)
                    Text("${angle.proDeg.roundToInt()}°", modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                    Text(
                        text = (if (angle.deltaDeg > 0) "+" else "") + "${angle.deltaDeg.roundToInt()}°",
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall,
                        color = if (close) AccentNeonVolt else ErrorRed,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            Text(
                text = if (comparison.validated) "Reference angles validated." else
                    "Pro reference angles are illustrative, not lab-measured.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted
            )
        }
    }
}


/** The four kinetic phases with measured angles; Impact is compared against the matched pro. */
@Composable
private fun PhaseBreakdownCard(phases: List<KineticPhaseUiModel>) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, CardBorderSubtle)
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(
                text = "PHASE BREAKDOWN",
                style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold),
                color = AccentNeonVolt
            )
            phases.forEach { phase ->
                Row(verticalAlignment = Alignment.Top) {
                    Text(
                        text = phase.phaseName,
                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Bold),
                        color = TextPrimaryWhite,
                        modifier = Modifier.width(110.dp)
                    )
                    Text(
                        text = phase.observation.ifBlank { "${phase.timestampMs} ms" },
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondarySilver
                    )
                }
            }
        }
    }
}
