plugins {
    id("com.android.application")
}

// Valores inyectados por el generador en gradle.properties
fun prop(name: String): String = project.property(name) as String
val cfgAppId       = prop("appId")
val cfgVersionCode = prop("appVersionCode").toInt()
val cfgVersionName = prop("appVersionName")
val cfgKsFile      = File(prop("keystoreFile"))
val cfgKsPass      = prop("keystorePass")
val cfgKeyAlias    = prop("keyAlias")
val cfgKeyPass     = prop("keyPass")

android {
    namespace = "com.webapp.shell"
    compileSdk = 37
    buildToolsVersion = "37.0.0"

    defaultConfig {
        applicationId = cfgAppId
        minSdk = 24
        targetSdk = 37
        versionCode = cfgVersionCode
        versionName = cfgVersionName
    }

    signingConfigs {
        create("release") {
            storeFile = cfgKsFile
            storePassword = cfgKsPass
            keyAlias = cfgKeyAlias
            keyPassword = cfgKeyPass
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }
}
