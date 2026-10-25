package com.tempo.app.feature.sports

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.SportsTennis
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.network.models.SportDto
import com.tempo.app.network.models.SportSkillDto
import com.tempo.app.ui.components.TempoErrorCard
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@Composable
fun SportSelectionScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: SportSelectionViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
            .padding(16.dp)
    ) {
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            Spacer(modifier = Modifier.height(24.dp))

            Text(
                text = "TEMPO CALIBRATION",
                style = MaterialTheme.typography.labelMedium.copy(letterSpacing = 1.5.sp),
                color = AccentNeonVolt
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Select Your Sport",
                style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold),
                color = TextPrimaryWhite
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "Choose the discipline you want to measure and analyze with Gemini 4 Argon.",
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondarySilver
            )

            Spacer(modifier = Modifier.height(16.dp))

            AnimatedVisibility(
                visible = state.errorMessage != null,
                enter = fadeIn(),
                exit = fadeOut()
            ) {
                Column(modifier = Modifier.padding(bottom = 12.dp)) {
                    TempoErrorCard(
                        errorMessage = state.errorMessage ?: "",
                        errorDetail = state.errorDetail,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Button(
                        onClick = viewModel::loadSports,
                        colors = ButtonDefaults.buttonColors(containerColor = SurfaceCharcoal)
                    ) {
                        Text("Retry", color = TextPrimaryWhite)
                    }
                }
            }

            if (state.isLoading) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(color = AccentNeonVolt)
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Fixed(2),
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(bottom = 80.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(state.sports, key = { it.id }) { sport ->
                        SportCard(
                            sport = sport,
                            isSelected = state.selectedSport?.id == sport.id,
                            onClick = {
                                viewModel.onSportClicked(sport)
                            }
                        )
                    }
                }
            }
        }

        // Bottom confirmation action bar if a sport is selected
        if (state.selectedSport != null && !state.showSkillPicker) {
            Surface(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(bottom = 8.dp),
                shape = RoundedCornerShape(16.dp),
                color = SurfaceCharcoal,
                border = BorderStroke(1.dp, CardBorderSubtle)
            ) {
                Row(
                    modifier = Modifier
                        .padding(16.dp)
                        .fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = state.selectedSport?.name.orEmpty(),
                            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                            color = TextPrimaryWhite
                        )
                        state.selectedSkill?.let { skill ->
                            Text(
                                text = "Skill: ${skill.name}",
                                style = MaterialTheme.typography.bodySmall,
                                color = AccentNeonVolt
                            )
                        }
                    }

                    Button(
                        onClick = {
                            viewModel.confirmSportAndSkill {
                                navController.navigate(Screen.Onboarding.route) {
                                    popUpTo(Screen.SportSelection.route) { inclusive = true }
                                }
                            }
                        },
                        enabled = !state.isSaving,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = AccentNeonVolt,
                            contentColor = BackgroundOnyx
                        ),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        if (state.isSaving) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                color = BackgroundOnyx,
                                strokeWidth = 2.dp
                            )
                        } else {
                            Text("Confirm", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        // Skill Picker Dialog
        if (state.showSkillPicker && state.selectedSport != null) {
            SkillPickerDialog(
                sport = state.selectedSport!!,
                selectedSkill = state.selectedSkill,
                isSaving = state.isSaving,
                onSkillSelected = viewModel::onSkillSelected,
                onDismiss = viewModel::dismissSkillPicker,
                onConfirm = {
                    viewModel.confirmSportAndSkill {
                        navController.navigate(Screen.Onboarding.route) {
                            popUpTo(Screen.SportSelection.route) { inclusive = true }
                        }
                    }
                }
            )
        }
    }
}

@Composable
private fun SportCard(
    sport: SportDto,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    val ready = sport.analysis_ready
    val border = when {
        isSelected -> BorderStroke(2.dp, AccentNeonVolt)
        ready -> BorderStroke(1.dp, CardBorderSubtle)
        else -> BorderStroke(1.dp, CardBorderSubtle.copy(alpha = 0.3f))
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .height(130.dp)
            .alpha(if (ready) 1f else 0.45f)
            .clickable(enabled = ready, onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = border
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                // Icon representation
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .clip(CircleShape)
                        .background(if (ready) AccentNeonVolt.copy(alpha = 0.15f) else Color.DarkGray),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Rounded.SportsTennis,
                        contentDescription = null,
                        tint = if (ready) AccentNeonVolt else TextMuted,
                        modifier = Modifier.size(20.dp)
                    )
                }

                if (ready) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = AccentNeonVolt.copy(alpha = 0.15f)
                    ) {
                        Text(
                            text = "Ready",
                            color = AccentNeonVolt,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                } else {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = Color.DarkGray.copy(alpha = 0.5f)
                    ) {
                        Text(
                            text = "Coming soon",
                            color = TextMuted,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Normal,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            Column {
                Text(
                    text = sport.name,
                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                    color = TextPrimaryWhite
                )
                Text(
                    text = if (ready) "${sport.skills.size} skill(s)" else "Under development",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (ready) TextSecondarySilver else TextMuted
                )
            }
        }
    }
}

@Composable
private fun SkillPickerDialog(
    sport: SportDto,
    selectedSkill: SportSkillDto?,
    isSaving: Boolean,
    onSkillSelected: (SportSkillDto) -> Unit,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "Select ${sport.name} Skill",
                color = TextPrimaryWhite,
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = "Which movement do you want to focus on?",
                    color = TextSecondarySilver,
                    fontSize = 13.sp
                )
                Spacer(modifier = Modifier.height(4.dp))
                sport.skills.forEach { skill ->
                    val isChecked = selectedSkill?.id == skill.id
                    val ready = skill.analysis_ready

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .alpha(if (ready) 1f else 0.4f)
                            .clickable(enabled = ready) { onSkillSelected(skill) }
                            .padding(vertical = 4.dp, horizontal = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(
                            selected = isChecked,
                            onClick = { if (ready) onSkillSelected(skill) },
                            enabled = ready,
                            colors = RadioButtonDefaults.colors(
                                selectedColor = AccentNeonVolt,
                                unselectedColor = TextSecondarySilver
                            )
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Column {
                            Text(
                                text = skill.name,
                                color = TextPrimaryWhite,
                                fontWeight = if (isChecked) FontWeight.Bold else FontWeight.Normal
                            )
                            if (!ready) {
                                Text(
                                    text = "Coming soon",
                                    color = TextMuted,
                                    fontSize = 11.sp
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = onConfirm,
                enabled = !isSaving && selectedSkill != null && selectedSkill.analysis_ready,
                colors = ButtonDefaults.buttonColors(
                    containerColor = AccentNeonVolt,
                    contentColor = BackgroundOnyx
                )
            ) {
                if (isSaving) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        color = BackgroundOnyx,
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Select & Continue", fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = TextSecondarySilver)
            }
        },
        containerColor = SurfaceCharcoal,
        shape = RoundedCornerShape(20.dp)
    )
}
