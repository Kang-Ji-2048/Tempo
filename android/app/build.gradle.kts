import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.hilt)
    alias(libs.plugins.ksp)
}

val localProperties = Properties()
val localPropertiesFile = rootProject.file("local.properties")
if (localPropertiesFile.exists()) {
    localProperties.load(localPropertiesFile.inputStream())
}

val localBaseUrl = localProperties.getProperty("BASE_URL", "http://localhost:8000/")
val localDebugToken = localProperties.getProperty("TEMPO_DEBUG_TOKEN", "")
val localTheaNumber = localProperties.getProperty("THEA_NUMBER", "")
val localUseMockApi = localProperties.getProperty("USE_MOCK_API", "false").toBoolean()
val localUserId = localProperties.getProperty("TEMPO_USER_ID", "user_1")

android {
    namespace = "com.tempo.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.tempo.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        buildConfigField("String", "BASE_URL", "\"$localBaseUrl\"")
        buildConfigField("Boolean", "USE_MOCK_API", "$localUseMockApi")
        buildConfigField("String", "TEMPO_DEBUG_TOKEN", "\"$localDebugToken\"")
        buildConfigField("String", "THEA_NUMBER", "\"$localTheaNumber\"")
        buildConfigField("String", "TEMPO_USER_ID", "\"\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            buildConfigField("String", "BASE_URL", "\"https://api.tempo.app/\"")
            buildConfigField("Boolean", "USE_MOCK_API", "false")
            buildConfigField("String", "TEMPO_DEBUG_TOKEN", "\"\"")
            buildConfigField("String", "THEA_NUMBER", "\"$localTheaNumber\"")
            buildConfigField("String", "TEMPO_USER_ID", "\"\"")
        }
        debug {
            buildConfigField("String", "BASE_URL", "\"$localBaseUrl\"")
            buildConfigField("Boolean", "USE_MOCK_API", "$localUseMockApi")
            buildConfigField("String", "TEMPO_DEBUG_TOKEN", "\"$localDebugToken\"")
            buildConfigField("String", "THEA_NUMBER", "\"$localTheaNumber\"")
            buildConfigField("String", "TEMPO_USER_ID", "\"$localUserId\"")
        }
        create("demoOffline") {
            initWith(getByName("debug"))
            matchingFallbacks += listOf("debug")
            buildConfigField("String", "BASE_URL", "\"http://10.0.2.2:8000/\"")
            buildConfigField("Boolean", "USE_MOCK_API", "true")
            buildConfigField("String", "TEMPO_DEBUG_TOKEN", "\"\"")
            buildConfigField("String", "THEA_NUMBER", "\"$localTheaNumber\"")
            buildConfigField("String", "TEMPO_USER_ID", "\"$localUserId\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.androidx.navigation.compose)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    implementation(libs.retrofit)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging.interceptor)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.retrofit.kotlinx.serialization.converter)

    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.concurrent.futures.ktx)

    // CameraX
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.video)
    implementation(libs.androidx.camera.view)

    // MediaPipe Pose Landmarker
    implementation(libs.mediapipe.tasks.vision)
    implementation(libs.androidx.graphics.path)

    // Media3 ExoPlayer & Transformer
    implementation(libs.androidx.media3.exoplayer)
    implementation(libs.androidx.media3.ui)
    implementation(libs.androidx.media3.transformer)
    implementation(libs.androidx.media3.effect)

    // WorkManager
    implementation(libs.androidx.work.runtime.ktx)

    // Room Database
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    // Health Connect & Firebase
    implementation(libs.androidx.health.connect)
    implementation(libs.firebase.messaging)

    testImplementation(libs.junit)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
