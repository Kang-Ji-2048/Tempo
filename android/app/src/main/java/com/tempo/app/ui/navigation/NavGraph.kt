package com.tempo.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.tempo.app.feature.auth.LoginScreen
import com.tempo.app.feature.auth.RegisterScreen
import com.tempo.app.feature.capture.CaptureViewModel
import com.tempo.app.feature.lesson.LessonDetailScreen
import com.tempo.app.feature.lesson.LessonRoutes
import com.tempo.app.feature.sdui.model.CapturePromptWidget
import com.tempo.app.feature.sports.SportSelectionScreen
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
        composable(Screen.Login.route) {
            LoginScreen(navController = navController)
        }
        composable(Screen.Register.route) {
            RegisterScreen(navController = navController)
        }
        composable(Screen.SportSelection.route) {
            SportSelectionScreen(navController = navController)
        }
        composable(Screen.Home.route) {
            HomeScreen(navController = navController)
        }
        composable(Screen.Onboarding.route) {
            OnboardingScreen(navController = navController)
        }
        composable(
            route = LessonRoutes.LESSON_PATTERN,
            arguments = listOf(navArgument("nodeId") { type = NavType.StringType })
        ) {
            LessonDetailScreen(navController = navController)
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
        // Capture pre-configured with a lesson's title and framing instructions.
        composable(
            route = LessonRoutes.CAPTURE_PATTERN,
            arguments = listOf("lesson_node", "lesson_title", "framing").map { name ->
                navArgument(name) {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                }
            }
        ) { backStackEntry ->
            val captureViewModel: CaptureViewModel = hiltViewModel()
            val args = backStackEntry.arguments
            val lessonNode = args?.getString("lesson_node")
            val lessonTitle = args?.getString("lesson_title")
            val framing = args?.getString("framing")
            LaunchedEffect(lessonNode) {
                if (lessonNode != null && lessonTitle != null) {
                    captureViewModel.setPrompt(
                        CapturePromptWidget(
                            title = "Record: $lessonTitle",
                            instruction = framing ?: "Film the full movement from the side.",
                            cameraHint = "Side-on, 3m back, full body and racket in frame",
                            durationS = 15,
                            id = "lesson_$lessonNode",
                        )
                    )
                }
            }
            CaptureScreen(navController = navController, viewModel = captureViewModel)
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
        composable(Screen.Saint.route) { com.tempo.app.feature.saint.SaintScreen(navController) }
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
