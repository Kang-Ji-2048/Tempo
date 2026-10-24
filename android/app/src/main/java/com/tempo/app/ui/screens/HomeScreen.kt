package com.tempo.app.ui.screens

import android.content.Context
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Sports
import androidx.compose.material.icons.rounded.ChatBubbleOutline
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.NetworkCheck
import androidx.compose.material.icons.rounded.Psychology
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.feature.home.HomeViewModel
import com.tempo.app.feature.home.TheaMessage
import com.tempo.app.feature.home.TheaSender
import com.tempo.app.feature.sdui.model.PathProgressWidget
import com.tempo.app.feature.sdui.ui.WidgetRenderer
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: HomeViewModel = hiltViewModel()
) {
    val context = LocalContext.current
    val profile by viewModel.userProfile.collectAsStateWithLifecycle()
    val latestSession by viewModel.latestSession.collectAsStateWithLifecycle()
    val debugState by viewModel.debugState.collectAsStateWithLifecycle()
    val conversationState by viewModel.conversationState.collectAsStateWithLifecycle()
    val homeHeader by viewModel.homeHeader.collectAsStateWithLifecycle()

    var showDebugSheet by remember { mutableStateOf(false) }
    var inputText by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    val sportDisplay = homeHeader?.sportDisplay
        ?: profile?.sport?.replaceFirstChar { it.uppercase() }
        ?: debugState.sport.takeIf { it.isNotBlank() && it != "Not selected" }?.replaceFirstChar { it.uppercase() }
        ?: "Badminton"
    val strokeDisplay = profile?.goal?.replace('_', ' ')?.replaceFirstChar { it.uppercase() } ?: "Overhead Clear"

    // Diagnostics / Settings sheet
    if (showDebugSheet) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(
            onDismissRequest = { showDebugSheet = false },
            sheetState = sheetState,
            containerColor = SurfaceCharcoal,
            contentColor = TextPrimaryWhite
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text(
                    text = "SETTINGS & SYSTEM STATUS",
                    style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                    color = AccentNeonVolt
                )

                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = BackgroundOnyx),
                    border = BorderStroke(1.dp, CardBorderSubtle)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Athlete:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(debugState.email, style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite, fontWeight = FontWeight.SemiBold)
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Active Sport:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(sportDisplay, style = MaterialTheme.typography.bodySmall, color = AccentNeonVolt, fontWeight = FontWeight.Bold)
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("AI Engine:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text("Gemini 4 Argon (Saint Runtime)", style = MaterialTheme.typography.bodySmall, color = TextPrimaryWhite)
                        }
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Network:", style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
                            Text(debugState.healthStatus, style = MaterialTheme.typography.bodySmall, color = AccentNeonVolt)
                        }
                    }
                }

                Button(
                    onClick = { viewModel.testConnection() },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !debugState.isCheckingConnection,
                    colors = ButtonDefaults.buttonColors(containerColor = AccentNeonVolt, contentColor = BackgroundOnyx),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    if (debugState.isCheckingConnection) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), color = BackgroundOnyx, strokeWidth = 2.dp)
                    } else {
                        Icon(Icons.Rounded.NetworkCheck, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Check Network Health (/health)", fontWeight = FontWeight.Bold)
                    }
                }

                OutlinedButton(
                    onClick = {
                        showDebugSheet = false
                        navController.navigate(Screen.SportSelection.route)
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.6f))
                ) {
                    Icon(Icons.Default.Sports, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Change Sport Discipline", color = AccentNeonVolt, fontWeight = FontWeight.SemiBold)
                }

                OutlinedButton(
                    onClick = {
                        showDebugSheet = false
                        viewModel.logout {
                            navController.navigate(Screen.Login.route) {
                                popUpTo(0) { inclusive = true }
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    border = BorderStroke(1.dp, Color(0xFFC62828))
                ) {
                    Icon(Icons.Default.ExitToApp, contentDescription = null, tint = Color(0xFFFF8A80), modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Sign Out", color = Color(0xFFFF8A80), fontWeight = FontWeight.SemiBold)
                }

                Spacer(modifier = Modifier.height(16.dp))
            }
        }
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx)
    ) {
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 100.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)
        ) {
            // Header: Thea Living Coach Studio Bar
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(CircleShape)
                                    .background(AccentNeonVolt)
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                text = "THEA COACHING ECOSYSTEM",
                                style = MaterialTheme.typography.labelSmall.copy(
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 1.2.sp
                                ),
                                color = AccentNeonVolt
                            )
                        }
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "Conversational Studio",
                            style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Black),
                            color = TextPrimaryWhite
                        )
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        // WhatsApp Out-of-band Saint Cadence Button
                        IconButton(
                            onClick = { viewModel.openWhatsAppCadence(context) },
                            modifier = Modifier
                                .size(40.dp)
                                .clip(CircleShape)
                                .background(SurfaceCharcoal)
                                .border(1.dp, CardBorderSubtle, CircleShape)
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.ChatBubbleOutline,
                                contentDescription = "Saint WhatsApp Cadence",
                                tint = AccentNeonVolt,
                                modifier = Modifier.size(20.dp)
                            )
                        }

                        // Settings & Diagnostics
                        IconButton(
                            onClick = { showDebugSheet = true },
                            modifier = Modifier
                                .size(40.dp)
                                .clip(CircleShape)
                                .background(SurfaceCharcoal)
                                .border(1.dp, CardBorderSubtle, CircleShape)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Settings,
                                contentDescription = "Settings",
                                tint = TextSecondarySilver,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }
                }
            }

            // Sport & Discipline Quick Filter Pill
            item {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = SurfaceCharcoal,
                    border = BorderStroke(1.dp, CardBorderSubtle),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { navController.navigate(Screen.SportSelection.route) }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.Sports,
                                contentDescription = null,
                                tint = AccentNeonVolt,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Column {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(
                                        text = sportDisplay,
                                        style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                                        color = TextPrimaryWhite
                                    )
                                    homeHeader?.level?.let { level ->
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Surface(
                                            shape = RoundedCornerShape(8.dp),
                                            color = AccentNeonVolt.copy(alpha = 0.15f),
                                            border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.5f))
                                        ) {
                                            Text(
                                                text = level.replaceFirstChar { it.uppercase() },
                                                style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                                                color = AccentNeonVolt,
                                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                                            )
                                        }
                                    }
                                }
                                val cadence = homeHeader?.let { header ->
                                    listOfNotNull(
                                        header.intensity?.replaceFirstChar { it.uppercase() },
                                        header.cadenceLabel
                                    ).joinToString(" • ").ifBlank { null }
                                }
                                Text(
                                    text = cadence ?: strokeDisplay,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = TextMuted
                                )
                            }
                        }
                        Text(
                            text = "Tap to switch",
                            style = MaterialTheme.typography.labelSmall,
                            color = AccentNeonVolt
                        )
                    }
                }
            }

            // Quick Training Launch Cards
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Card(
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                        border = BorderStroke(1.dp, CardBorderSubtle),
                        onClick = { navController.navigate(Screen.Capture.route) }
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.PlayArrow, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(20.dp))
                                Spacer(modifier = Modifier.width(6.dp))
                                Text("Record Clip", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text("CameraX 60fps & 33 pose landmarks", style = MaterialTheme.typography.bodySmall, color = TextMuted)
                        }
                    }

                    Card(
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
                        border = BorderStroke(1.dp, CardBorderSubtle),
                        onClick = { navController.navigate(Screen.Live.route) }
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Speed, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(20.dp))
                                Spacer(modifier = Modifier.width(6.dp))
                                Text("Live Earbuds", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text("Real-time cues with 15s cooldown", style = MaterialTheme.typography.bodySmall, color = TextMuted)
                        }
                    }
                }
            }

            // SECTION 1: Top-Level Duolingo Skill Progression Tree (PathProgressWidget)
            val pathWidget = conversationState.activeWidgets.filterIsInstance<PathProgressWidget>().firstOrNull()
            if (pathWidget != null) {
                item(key = "top_path_progress") {
                    WidgetRenderer(
                        widget = pathWidget,
                        onAction = { viewModel.onWidgetAction(it) }
                    )
                }
            }

            // SECTION 2: Coach Thea Dialogue Feed (Surface A)
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "COACH THEA DIALOGUE",
                        style = MaterialTheme.typography.labelMedium.copy(
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        ),
                        color = AccentNeonVolt
                    )

                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = SurfaceVariantDark
                    ) {
                        Text(
                            text = "Gemini 4 Argon",
                            style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp),
                            color = TextSecondarySilver,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            items(
                items = conversationState.messages,
                key = { it.id }
            ) { msg ->
                TheaMessageBubble(
                    message = msg,
                    onAudioPlay = {
                        // Spoken audio preview
                    }
                )
            }

            if (conversationState.isThinking) {
                item {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            color = AccentNeonVolt,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(10.dp))
                        Text(
                            text = "Thea is analyzing kinetic metrics...",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextMuted
                        )
                    }
                }
            }

            // Suggested Conversation Quick Chips
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val chips = listOf(
                        "Why did my contact point drop?",
                        "How do I fix elbow flexion?",
                        "Check my training cadence"
                    )
                    chips.forEach { chipText ->
                        Surface(
                            shape = RoundedCornerShape(20.dp),
                            color = SurfaceCharcoal,
                            border = BorderStroke(1.dp, CardBorderSubtle),
                            modifier = Modifier.clickable {
                                viewModel.sendMessage(chipText)
                            }
                        ) {
                            Text(
                                text = chipText,
                                style = MaterialTheme.typography.labelSmall.copy(fontSize = 11.sp),
                                color = TextSecondarySilver,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                            )
                        }
                    }
                }
            }

            // SECTION 3: Dynamic Server-Driven UI (SDUI) Interactive Widgets
            val otherWidgets = conversationState.activeWidgets.filter { it !is PathProgressWidget }
            if (otherWidgets.isNotEmpty()) {
                item {
                    Text(
                        text = "RECOMMENDED ACTION DRILLS & COMPREHENSION",
                        style = MaterialTheme.typography.labelMedium.copy(
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        ),
                        color = AccentNeonVolt
                    )
                }

                items(
                    items = otherWidgets,
                    key = { it.key }
                ) { widget ->
                    WidgetRenderer(
                        widget = widget,
                        onAction = { action -> viewModel.onWidgetAction(action) }
                    )
                }
            }
        }

        // Persistent Interactive Bottom Chat Bar ("Ask Coach Thea...")
        Surface(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth(),
            color = BackgroundOnyx.copy(alpha = 0.95f),
            border = BorderStroke(1.dp, CardBorderSubtle)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = inputText,
                    onValueChange = { inputText = it },
                    placeholder = {
                        Text(
                            text = "Ask Coach Thea about technique, drills...",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextMuted
                        )
                    },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(24.dp),
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = SurfaceCharcoal,
                        unfocusedContainerColor = SurfaceCharcoal,
                        focusedTextColor = TextPrimaryWhite,
                        unfocusedTextColor = TextPrimaryWhite,
                        focusedIndicatorColor = AccentNeonVolt,
                        unfocusedIndicatorColor = CardBorderSubtle,
                        cursorColor = AccentNeonVolt
                    ),
                    maxLines = 2,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = {
                        if (inputText.isNotBlank()) {
                            viewModel.sendMessage(inputText)
                            inputText = ""
                        }
                    })
                )

                Spacer(modifier = Modifier.width(8.dp))

                IconButton(
                    onClick = {
                        if (inputText.isNotBlank()) {
                            viewModel.sendMessage(inputText)
                            inputText = ""
                        }
                    },
                    modifier = Modifier
                        .size(46.dp)
                        .clip(CircleShape)
                        .background(AccentNeonVolt)
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Rounded.Send,
                        contentDescription = "Send",
                        tint = BackgroundOnyx,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
        }
    }
}

@Composable
private fun TheaMessageBubble(
    message: TheaMessage,
    onAudioPlay: (String) -> Unit
) {
    val isThea = message.sender == TheaSender.THEA
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (isThea) Alignment.Start else Alignment.End
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(if (isThea) 0.92f else 0.85f),
            horizontalArrangement = if (isThea) Arrangement.Start else Arrangement.End,
            verticalAlignment = Alignment.Top
        ) {
            if (isThea) {
                Box(
                    modifier = Modifier
                        .size(32.dp)
                        .clip(CircleShape)
                        .background(AccentNeonVolt),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Psychology,
                        contentDescription = "Coach Thea",
                        tint = BackgroundOnyx,
                        modifier = Modifier.size(18.dp)
                    )
                }
                Spacer(modifier = Modifier.width(10.dp))
            }

            Surface(
                shape = RoundedCornerShape(
                    topStart = 16.dp,
                    topEnd = 16.dp,
                    bottomStart = if (isThea) 4.dp else 16.dp,
                    bottomEnd = if (isThea) 16.dp else 4.dp
                ),
                color = if (isThea) SurfaceCharcoal else AccentNeonVolt,
                border = BorderStroke(1.dp, if (isThea) CardBorderSubtle else AccentNeonVolt)
            ) {
                Column(modifier = Modifier.padding(14.dp)) {
                    Text(
                        text = if (isThea) "Coach Thea" else "You",
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                        color = if (isThea) AccentNeonVolt else BackgroundOnyx.copy(alpha = 0.7f)
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = message.text,
                        style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 20.sp),
                        color = if (isThea) TextPrimaryWhite else BackgroundOnyx
                    )

                    if (!message.audioCueText.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = BackgroundOnyx.copy(alpha = 0.6f),
                            border = BorderStroke(1.dp, CardBorderSubtle)
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.AutoMirrored.Rounded.VolumeUp,
                                    contentDescription = null,
                                    tint = AccentNeonVolt,
                                    modifier = Modifier.size(14.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = message.audioCueText,
                                    style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold),
                                    color = AccentNeonVolt
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
