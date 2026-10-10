# Android third-party components

The original Kotlin client is distributed under the repository MIT license. That license does not replace the licenses of dependencies, Gradle tooling, detector models, or user data. The build obtains dependencies from their declared upstream repositories.

| Component | Pinned version | Upstream terms/source |
|---|---|---|
| MediaPipe Tasks Vision | 0.10.26.1 | [MediaPipe source and Apache-2.0 license](https://github.com/google-ai-edge/mediapipe) |
| AndroidX Activity | 1.10.1 | [AndroidX source](https://android.googlesource.com/platform/frameworks/support/) (Apache-2.0) |
| AndroidX CameraX | 1.4.2 | [AndroidX source](https://android.googlesource.com/platform/frameworks/support/) (Apache-2.0) |
| OkHttp / MockWebServer | 4.12.0 | [OkHttp source](https://github.com/square/okhttp) (Apache-2.0) |
| Gson | 2.11.0 | [Gson source](https://github.com/google/gson) (Apache-2.0) |
| Guava Android | 33.3.1-android | [Guava source](https://github.com/google/guava) (Apache-2.0) |
| JUnit (tests only) | 4.13.2 | [JUnit license](https://github.com/junit-team/junit4/blob/main/LICENSE-junit.txt) (EPL-1.0) |
| Kotlin | 2.2.20 | [Kotlin source](https://github.com/JetBrains/kotlin) (Apache-2.0) |
| Gradle wrapper | 8.14 | [Gradle license](https://github.com/gradle/gradle/blob/master/LICENSE) (Apache-2.0) |

The wrapper scripts retain their upstream notices; the distribution archive is SHA-256 pinned. Binary redistribution should preserve applicable dependency license and notice files, including transitive components resolved by Gradle. This table documents direct dependencies, not an exhaustive binary software bill of materials.

## Detector assets

`fetch_assets.py` retrieves exact MediaPipe Pose Landmarker Lite and Hand Landmarker task assets from Google's public model storage. URLs and SHA-256 values are recorded in that script and in capture receipts. See the official [pose model documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker) and [hand model documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker).

These files are not included in Git or the Python distribution. Access to a download does not by itself establish redistribution permission. The software MIT license and MediaPipe source license must not be asserted as a blanket license for detector weights. Review the applicable asset terms before distributing an APK that embeds them. A developer can fetch them locally to build the camera example. The CI APK omits the assets and is for compilation and file replay only.

Recognition ONNX models, ordered labels derived from datasets, natural videos, and human landmark traces are not supplied by this Android example. Their rights and consent remain separate from software licensing.
