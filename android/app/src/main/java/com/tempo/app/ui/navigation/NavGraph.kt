package com.tempo.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
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
        composable(Screen.Capture.route) {
            CaptureScreen(navController = navController)
        }
        composable(
            route = Screen.Analysis.route,
            arguments = listOf(
                navArgument("sessionId") {
                    type = NavType.StringType
                    defaultValue = "default_session"
                }
            )
        ) { backStackEntry ->
            val sessionId = backStackEntry.arguments?.getString("sessionId") ?: "default_session"
            AnalysisScreen(sessionId = sessionId, navController = navController)
        }
        composable(Screen.Live.route) {
            LiveScreen(navController = navController)
        }
        composable(Screen.Schedule.route) {
            ScheduleScreen(navController = navController)
        }
    }
}
