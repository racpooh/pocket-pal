import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// Pure Kotlin/JVM: API client, upload queue, JSON, money. No third-party dependencies, so it is also built and
// tested outside Android (see android/README.md). Used unchanged by :app.
plugins { id("org.jetbrains.kotlin.jvm") }

java { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
kotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }

val e2e by sourceSets.creating {
    compileClasspath += sourceSets.main.get().output
    runtimeClasspath += output + compileClasspath
}
configurations[e2e.implementationConfigurationName].extendsFrom(configurations.implementation.get())

tasks.register<JavaExec>("selfTest") {
    group = "verification"
    description = "Dependency-free unit tests of the client core"
    classpath = sourceSets.test.get().runtimeClasspath
    mainClass.set("dev.finassist.core.CoreSelfTest")
}
tasks.named("check") { dependsOn("selfTest") }

// ./gradlew :core:e2e -PbaseUrl=http://127.0.0.1:8001  (needs backend/scripts/dev_server.py --profile e2e --provider fake running)
tasks.register<JavaExec>("e2e") {
    group = "verification"
    classpath = e2e.runtimeClasspath
    mainClass.set("dev.finassist.e2e.Cp3aE2EKt")
    args(
        (findProperty("baseUrl") ?: "http://127.0.0.1:8001").toString(),
        rootProject.file("../backend/fixtures/synthetic/slips").path,
        layout.buildDirectory.dir("e2e").get().asFile.path,
    )
}
