# Worker container: the ONLY place Android tooling runs.
# Built from the repo root (see docker-compose.yml: context: .) so it can
# copy backend/app without duplicating it.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    ANDROID_HOME=/opt/android-sdk \
    APKTOOL_VERSION=2.9.3 \
    CMDLINE_TOOLS_VERSION=16111833 \
    BUILD_TOOLS_VERSION=37.0.0 \
    PLATFORM_VERSION=37.0 \
    GRADLE_VERSION=9.7.1 \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYTHONUNBUFFERED=1
# BUILD_TOOLS_VERSION=37.0.0 is the latest Google publishes as of this build
# (verified against https://dl.google.com/android/repository/repository2-3.xml)
# and covers aapt2/apksigner/zipalign for apps targeting API 33-37
# (Android 13 through the current 17) — bump this to whatever's newest if a
# future Android version's apps fail to rebuild with an unrecognized-
# resource/manifest-attribute error from aapt2.

RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jdk-headless \
        python3 python3-pip \
        wget unzip curl ca-certificates \
        android-tools-adb \
    && rm -rf /var/lib/apt/lists/* \
    && test -d "$JAVA_HOME"

# --- apktool (official GitHub release, version pinned & detected at runtime;
#     the project's old Bitbucket download host now 403s, GitHub Releases is
#     the current canonical distribution channel) ---
RUN wget -q -O /usr/local/bin/apktool.jar \
        "https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VERSION}/apktool_${APKTOOL_VERSION}.jar" \
    && printf '#!/bin/sh\nexec java -jar /usr/local/bin/apktool.jar "$@"\n' > /usr/local/bin/apktool \
    && chmod +x /usr/local/bin/apktool

# --- Android cmdline-tools -> provides aapt2 / apksigner / zipalign via build-tools ---
# The license-acceptance step tolerates a non-zero exit (sdkmanager's `yes |`
# pipe can trip SIGPIPE harmlessly); the actual build-tools install does NOT
# swallow its exit code — if it fails, the image build fails loudly here
# instead of silently shipping a worker with no aapt2/apksigner/zipalign.
RUN mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools \
    && wget -q -O /tmp/cmdline-tools.zip \
        "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS_VERSION}_latest.zip" \
    && unzip -q /tmp/cmdline-tools.zip -d ${ANDROID_SDK_ROOT}/cmdline-tools \
    && mv ${ANDROID_SDK_ROOT}/cmdline-tools/cmdline-tools ${ANDROID_SDK_ROOT}/cmdline-tools/latest \
    && rm /tmp/cmdline-tools.zip \
    && (yes | ${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager --licenses >/dev/null 2>&1 || true) \
    && ${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager "build-tools;${BUILD_TOOLS_VERSION}" "platforms;android-${PLATFORM_VERSION}" \
    && test -x "${ANDROID_SDK_ROOT}/build-tools/${BUILD_TOOLS_VERSION}/aapt2" \
    && test -x "${ANDROID_SDK_ROOT}/build-tools/${BUILD_TOOLS_VERSION}/apksigner" \
    && test -x "${ANDROID_SDK_ROOT}/build-tools/${BUILD_TOOLS_VERSION}/zipalign" \
    && test -f "${ANDROID_SDK_ROOT}/platforms/android-${PLATFORM_VERSION}/android.jar"

ENV PATH="${ANDROID_SDK_ROOT}/build-tools/${BUILD_TOOLS_VERSION}:${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${JAVA_HOME}/bin:/opt/gradle/bin:${PATH}"

# --- Gradle (for the "generador de apks" URL-wrapper app builder; see
#     app/services/appgen_service.py — the Android Gradle Plugin version in
#     its bundled template requires this exact Gradle line) ---
RUN wget -q -O /tmp/gradle.zip \
        "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
    && unzip -q /tmp/gradle.zip -d /opt && rm /tmp/gradle.zip \
    && mv /opt/gradle-${GRADLE_VERSION} /opt/gradle \
    && test -x /opt/gradle/bin/gradle

# Standalone baksmali/smali binaries are deliberately NOT installed: the
# only known distribution channel (JesusFreke/smali's Bitbucket "Downloads")
# now requires a paid Bitbucket plan and returns HTTP 402/intermittent
# failures even for existing files — not something to depend on in a build.
# Nothing in this codebase calls baksmali/smali as standalone binaries
# anyway: apktool_service.py only shells out to `apktool`, which already
# bundles equivalent Smali<->DEX handling internally for decode/build.

# --- JADX ---
RUN wget -q -O /tmp/jadx.zip \
        "https://github.com/skylot/jadx/releases/download/v1.5.0/jadx-1.5.0.zip" \
    && unzip -q /tmp/jadx.zip -d /opt/jadx && rm /tmp/jadx.zip \
    && ln -s /opt/jadx/bin/jadx /usr/local/bin/jadx

RUN useradd --create-home --uid 1000 apklab \
    && mkdir -p /data/storage /data/db \
    && chown -R apklab:apklab /data ${ANDROID_SDK_ROOT} /opt/jadx /opt/gradle

WORKDIR /app
COPY backend/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY worker/start.sh ./start.sh

RUN chmod +x ./start.sh && chown -R apklab:apklab /app
USER apklab

EXPOSE 8000
CMD ["./start.sh"]
