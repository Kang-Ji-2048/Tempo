package com.tempo.app.ui.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val DarkColorScheme = darkColorScheme(
    primary = AccentNeonVolt,
    onPrimary = BackgroundOnyx,
    primaryContainer = SurfaceVariantDark,
    onPrimaryContainer = AccentNeonVolt,
    secondary = AccentNeonVoltDark,
    onSecondary = BackgroundOnyx,
    background = BackgroundOnyx,
    onBackground = TextPrimaryWhite,
    surface = SurfaceCharcoal,
    onSurface = TextPrimaryWhite,
    surfaceVariant = SurfaceVariantDark,
    onSurfaceVariant = TextSecondarySilver,
    outline = CardBorderSubtle,
    error = ErrorRed,
    onError = TextPrimaryWhite
)

@Composable
fun TempoTheme(
    content: @Composable () -> Unit
) {
    val colorScheme = DarkColorScheme
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.background.toArgb()
            window.navigationBarColor = colorScheme.surface.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
            WindowCompat.getInsetsController(window, view).isAppearanceLightNavigationBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        shapes = TempoShapes,
        content = content
    )
}
