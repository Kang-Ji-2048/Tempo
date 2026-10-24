package com.tempo.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.tempo.app.feature.sdui.debug.SduiDebugScreen
import com.tempo.app.ui.screens.AnalysisScreen
import com.tempo.app.ui.screens.CaptureScreen
import com.tempo.app.ui.screens.HomeScreen
import com.tempo.app.ui.screens.LiveScreen
import com.tempo.app.ui.screens.OnboardingScreen
import com.tempo.app.ui.screens.ScheduleScreen

@Composable
fun TempoNavGraph(
    navController: NavHostController,
    modifier: Modifier = Modifier,
    startDestination: String = Screen.Home.route
) {
    NavHost(
        navController = navController,
        startDestination = startDestination,
        modifier = modifier
    ) {
        composable(Screen.Home.route) {
            HomeScreen(navController = navController)
        }
        composable(Screen.Onboarding.route) {
            OnboardingScreen(navController = navController)
        }
        composable(
            route = Screen.Capture.route,
            deepLinks = listOf(
                androidx.navigation.navDeepLink { uriPattern = "tempo://app/capture" },
                androidx.navigation.navDeepLink { uriPattern = "https://tempo.app/capture" }
            )
        ) {
            CaptureScreen(navController = navController)
        }
        composable(
            route = Screen.Analysis.route,
            arguments = listOf(
                navArgument("sessionId") {
                    type = NavType.StringType
                    defaultValue = "default_session"
                }
            ),
            deepLinks = listOf(
                androidx.navigation.navDeepLink { uriPattern = "tempo://app/analysis/{sessionId}" },
                androidx.navigation.navDeepLink { uriPattern = "https://tempo.app/analysis/{sessionId}" }
            )
        ) { backStackEntry ->
            val sessionId = backStackEntry.arguments?.getString("sessionId") ?: "default_session"
            AnalysisScreen(sessionId = sessionId, navController = navController)
        }
        composable(Screen.Live.route) {
            LiveScreen(navController = navController)
        }
        composable(
            route = Screen.Schedule.route,
            deepLinks = listOf(
                androidx.navigation.navDeepLink { uriPattern = "tempo://app/schedule" },
                androidx.navigation.navDeepLink { uriPattern = "https://tempo.app/schedule" }
            )
        ) {
            ScheduleScreen(navController = navController)
        }
        composable(Screen.SduiDebug.route) {
            SduiDebugScreen(onNavigateToCapture = { navController.navigate(Screen.Capture.route) })
        }
    }
}
