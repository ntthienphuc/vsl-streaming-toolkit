plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "org.vslstream.demo"
    compileSdk = 36
    buildFeatures { buildConfig = true }
    defaultConfig { applicationId = "org.vslstream.demo"; minSdk = 26; targetSdk = 36; versionCode = 3; versionName = "0.2.1" }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    implementation(project(":stream-client"))
    implementation("com.google.guava:guava:33.3.1-android")
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("androidx.camera:camera-camera2:1.4.2")
    implementation("androidx.camera:camera-lifecycle:1.4.2")
    implementation("androidx.camera:camera-view:1.4.2")
}
