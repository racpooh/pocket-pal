plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Base URLs: debug → the developer's machine through `adb reverse tcp:8000 tcp:8000`; release → HTTPS only
// (enforced again at runtime by BaseUrlPolicy, and by network_security_config).
val debugBaseUrl = (findProperty("debugApiBaseUrl") ?: "http://127.0.0.1:8000").toString()
val releaseBaseUrl = (findProperty("releaseApiBaseUrl") ?: "https://api.invalid").toString()

android {
    namespace = "dev.finassist.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.finassist.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 5
        versionName = "0.4.1-slice1"
    }

    buildTypes {
        debug {
            buildConfigField("String", "API_BASE_URL", "\"$debugBaseUrl\"")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("String", "API_BASE_URL", "\"$releaseBaseUrl\"")
        }
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation(project(":core"))
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
