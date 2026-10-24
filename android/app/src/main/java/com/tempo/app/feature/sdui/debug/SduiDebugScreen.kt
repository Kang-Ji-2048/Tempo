package com.tempo.app.feature.sdui.debug

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.tempo.app.feature.sdui.ui.WidgetRenderer
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.ErrorRed
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextSecondarySilver

/** Developer gallery rendering the hard-coded mock SDUI feed through the real renderer. */
@Composable
fun SduiDebugScreen(
    onNavigateToCapture: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: SduiDebugViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(viewModel) {
        viewModel.events.collect { event ->
            when (event) {
                is SduiEvent.Message -> {
                    snackbar.currentSnackbarData?.dismiss()
                    snackbar.showSnackbar(event.text)
                }
                SduiEvent.NavigateToCapture -> onNavigateToCapture()
            }
        }
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(BackgroundOnyx),
    ) {
        LazyColumn(
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            item(key = "header") {
                GalleryHeader(state = state, onReload = viewModel::load)
            }
            items(state.items, key = { it.key }) { item ->
                WidgetRenderer(
                    widget = item.widget,
                    onAction = viewModel::onAction,
                    modifier = Modifier.animateItem(),
                )
            }
        }

        if (state.isLoading && state.items.isEmpty()) {
            CircularProgressIndicator(color = AccentNeonVolt, modifier = Modifier.align(Alignment.Center))
        }

        AnimatedVisibility(visible = state.isPosting, modifier = Modifier.align(Alignment.TopCenter)) {
            LinearProgressIndicator(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(3.dp),
                color = AccentNeonVolt,
                trackColor = SurfaceVariantDark,
            )
        }

        SnackbarHost(snackbar, modifier = Modifier.align(Alignment.BottomCenter))
    }
}

@Composable
private fun GalleryHeader(state: SduiFeedUiState, onReload: () -> Unit) {
    Column(Modifier.padding(horizontal = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    "SDUI LAB",
                    color = AccentNeonVolt,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.6.sp,
                )
                Text("Widget Gallery", style = MaterialTheme.typography.displayLarge)
            }
            IconButton(onClick = onReload) {
                Icon(Icons.Rounded.Refresh, contentDescription = "Reset mock feed", tint = AccentNeonVolt)
            }
        }
        Text(
            text = "${state.knownCount} widgets rendered · ${state.unknownCount} unknown skipped safely",
            color = TextSecondarySilver,
            fontSize = 13.sp,
        )
        state.error?.let { Text(it, color = ErrorRed, fontSize = 13.sp) }
    }
}
