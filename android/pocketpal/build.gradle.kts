plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
 namespace = "dev.finassist.pocketpal"
 compileSdk = 35
 defaultConfig { applicationId = "dev.finassist.pocketpal"; minSdk = 26; targetSdk = 35; versionCode = 2; versionName = "0.2.0-gallery" }
 buildFeatures { buildConfig = true }
 buildTypes {
  debug { buildConfigField("String", "WEB_ORIGIN", "\"http://127.0.0.1:3002\"") }
  release { buildConfigField("String", "WEB_ORIGIN", "\"" + (findProperty("pocketPalOrigin") ?: "https://app.invalid") + "\"") }
 }
 compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
 kotlinOptions { jvmTarget = "17" }
}
dependencies {
 implementation("androidx.webkit:webkit:1.12.1")
 implementation("androidx.work:work-runtime-ktx:2.10.0")
 implementation("com.google.mlkit:text-recognition:16.0.1")
 testImplementation("junit:junit:4.13.2")
}
