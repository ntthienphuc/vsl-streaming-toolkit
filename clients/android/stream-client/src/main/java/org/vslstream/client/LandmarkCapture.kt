package org.vslstream.client

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.SystemClock
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.gson.JsonArray
import com.google.gson.JsonNull
import com.google.gson.JsonObject
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker
import java.security.MessageDigest

/** A distinct capture profile, not equivalent to desktop Holistic or the legacy app.
 * Own this analyzer and close it on the same single camera executor.
 */
class LandmarkCapture(
    context: Context,
    private val targetFps: Int,
    private val frontCamera: Boolean,
    private val onFrame: (JsonObject) -> Unit,
    private val onError: (Exception) -> Unit
) : ImageAnalysis.Analyzer, AutoCloseable {
    companion object {
        const val PROFILE = "android-mediapipe-tasks-pose-hands-v1"
        const val POSE_HASH = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"
        const val HAND_HASH = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
        const val POSE_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
        const val HAND_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    }
    private val pose: PoseLandmarker
    private val hands: HandLandmarker
    private var observed = 0L
    private var rateSkipped = 0L
    private var processed = 0L
    private var noPose = 0L
    private var errors = 0L
    private var clockTies = 0L
    private var lastTime = -1L
    private var firstTime = -1L
    private var lastSampleNs = -1L
    private var seq = 0L
    private var rotation = 0
    private var width = 0
    private var height = 0

    init {
        require(targetFps in 1..30)
        fun verify(name: String, expected: String) {
            val digest = MessageDigest.getInstance("SHA-256")
            context.assets.open(name).use { input ->
                val buffer = ByteArray(65536)
                while (true) { val n = input.read(buffer); if (n < 0) break; digest.update(buffer, 0, n) }
            }
            require(digest.digest().joinToString("") { "%02x".format(it) } == expected) { "Unexpected MediaPipe asset: $name" }
        }
        verify("pose_landmarker_lite.task", POSE_HASH); verify("hand_landmarker.task", HAND_HASH)
        pose = PoseLandmarker.createFromOptions(context, PoseLandmarker.PoseLandmarkerOptions.builder()
            .setBaseOptions(BaseOptions.builder().setModelAssetPath("pose_landmarker_lite.task").setDelegate(Delegate.CPU).build())
            .setRunningMode(RunningMode.VIDEO).setNumPoses(1).setMinPoseDetectionConfidence(0.5f)
            .setMinPosePresenceConfidence(0.5f).setMinTrackingConfidence(0.5f).build())
        try {
            hands = HandLandmarker.createFromOptions(context, HandLandmarker.HandLandmarkerOptions.builder()
                .setBaseOptions(BaseOptions.builder().setModelAssetPath("hand_landmarker.task").setDelegate(Delegate.CPU).build())
                .setRunningMode(RunningMode.VIDEO).setNumHands(2).setMinHandDetectionConfidence(0.5f)
                .setMinHandPresenceConfidence(0.5f).setMinTrackingConfidence(0.5f).build())
        } catch (e: Exception) { pose.close(); throw e }
    }

    override fun analyze(image: ImageProxy) {
        var original: Bitmap? = null
        var upright: Bitmap? = null
        try {
            observed++
            val nowNs = SystemClock.elapsedRealtimeNanos()
            if (lastSampleNs >= 0 && nowNs - lastSampleNs < 1_000_000_000L / targetFps) { rateSkipped++; return }
            lastSampleNs = nowNs
            var timeMs = nowNs / 1_000_000
            if (timeMs <= lastTime) { timeMs = lastTime + 1; clockTies++ }
            lastTime = timeMs
            if (firstTime < 0) firstTime = timeMs
            rotation = image.imageInfo.rotationDegrees
            original = image.toBitmap()
            upright = if (rotation == 0) original else Bitmap.createBitmap(original, 0, 0, original.width, original.height,
                Matrix().apply { postRotate(rotation.toFloat()) }, true)
            width = upright.width; height = upright.height
            val mpImage = BitmapImageBuilder(upright).build()
            val p = try { pose.detectForVideo(mpImage, timeMs) } catch (e: Exception) { mpImage.close(); throw e }
            val h = try { hands.detectForVideo(mpImage, timeMs) } finally { mpImage.close() }
            val body = p.landmarks().firstOrNull()
            if (body == null) noPose++
            val detected = h.landmarks()
            val assigned = assignHands(body, detected, h.handednesses().map { it.firstOrNull()?.categoryName().orEmpty() })
            onFrame(JsonObject().apply {
                addProperty("seq", seq++); addProperty("timestamp_ms", timeMs)
                add("pose_landmarks", body?.let(::landmarksJson) ?: JsonNull.INSTANCE)
                add("left_hand_landmarks", assigned.first?.let(::landmarksJson) ?: JsonNull.INSTANCE)
                add("right_hand_landmarks", assigned.second?.let(::landmarksJson) ?: JsonNull.INSTANCE)
            })
            processed++
        } catch (e: Exception) { errors++; onError(e) }
        finally { if (upright !== original) upright?.recycle(); original?.recycle(); image.close() }
    }

    private fun landmarksJson(values: List<NormalizedLandmark>) = JsonArray().apply {
        values.forEach { point -> add(JsonObject().apply {
            addProperty("x", point.x()); addProperty("y", point.y()); addProperty("z", point.z())
            addProperty("visibility", point.visibility().orElse(1f))
        }) }
    }

    private fun assignHands(pose: List<NormalizedLandmark>?, values: List<List<NormalizedLandmark>>, labels: List<String>):
        Pair<List<NormalizedLandmark>?, List<NormalizedLandmark>?> {
        var left: Int? = null; var right: Int? = null
        if (pose != null) {
            data class Candidate(val distance: Double, val hand: Int, val side: Int)
            val candidates = mutableListOf<Candidate>()
            values.forEachIndexed { index, hand ->
                val x = hand.map { it.x().toDouble() }.average(); val y = hand.map { it.y().toDouble() }.average()
                listOf(15, 16).forEachIndexed { side, joint ->
                    val wrist = pose[joint]
                    if (wrist.visibility().orElse(0f) >= 0.5f) {
                        val d = (x - wrist.x()) * (x - wrist.x()) + (y - wrist.y()) * (y - wrist.y())
                        if (d < 0.08) candidates.add(Candidate(d, index, side))
                    }
                }
            }
            candidates.sortedBy { it.distance }.forEach { candidate ->
                if (candidate.hand != left && candidate.hand != right) {
                    if (candidate.side == 0 && left == null) left = candidate.hand
                    if (candidate.side == 1 && right == null) right = candidate.hand
                }
            }
        }
        values.indices.forEach { i ->
            if (i != left && i != right) {
                // Tasks handedness is used verbatim for this unmirrored inference profile.
                // Device validation must check anatomical left/right on both cameras.
                if (labels.getOrNull(i).equals("Left", true) && left == null) left = i
                else if (labels.getOrNull(i).equals("Right", true) && right == null) right = i
            }
        }
        return Pair(left?.let { values[it] }, right?.let { values[it] })
    }

    /** Call after analyzer executor has drained for a final stable receipt. */
    fun receipt(): JsonObject = JsonObject().apply {
        addProperty("schema_version", 1); addProperty("extractor_profile", PROFILE)
        add("software", JsonObject().apply { addProperty("mediapipe_tasks", "0.10.26.1"); addProperty("client_version", "0.2.1"); addProperty("delegate", "CPU") })
        add("assets", JsonObject().apply {
            add("pose", JsonObject().apply { addProperty("sha256", POSE_HASH); addProperty("source_url", POSE_URL) })
            add("hand", JsonObject().apply { addProperty("sha256", HAND_HASH); addProperty("source_url", HAND_URL) })
        })
        addProperty("delegate", "CPU"); addProperty("running_mode", "VIDEO")
        addProperty("confidence_thresholds", 0.5)
        add("coordinates", JsonObject().apply {
            addProperty("space", "mediapipe_normalized_unclamped_xyz_visibility")
            addProperty("rotation_policy", "rotate_ImageProxy_imageInfo_rotationDegrees")
            addProperty("last_rotation_degrees", rotation); addProperty("inference_mirrored", false)
            addProperty("preview_mirrored", frontCamera); addProperty("lens", if (frontCamera) "front" else "back")
            addProperty("last_upright_width", width); addProperty("last_upright_height", height)
        })
        add("clock", JsonObject().apply {
            addProperty("source", "SystemClock.elapsedRealtimeNanos_at_analyzer_arrival")
            addProperty("strictly_increasing_ms", true); addProperty("tie_policy", "previous_plus_1_ms")
            addProperty("ties_adjusted", clockTies); addProperty("first_timestamp_ms", firstTime); addProperty("last_timestamp_ms", lastTime)
        })
        add("assignment", JsonObject().apply {
            addProperty("algorithm", "greedy_visible_pose_wrist_to_hand_centroid_then_tasks_handedness_verbatim")
            addProperty("squared_distance_threshold", 0.08); addProperty("cache_ms", 0)
            addProperty("anatomical_handedness_device_validated", false)
        })
        add("sampling", JsonObject().apply {
            addProperty("target_fps", targetFps); addProperty("observed_frames", observed)
            addProperty("skipped_rate_limit", rateSkipped); addProperty("processed_frames", processed)
            addProperty("missing_pose_frames_retained", noPose); addProperty("extraction_errors", errors)
            add("skipped_busy", JsonNull.INSTANCE)
            addProperty("camera_backpressure", "KEEP_ONLY_LATEST; upstream replaced frames not observable")
            addProperty("observed_output_fps", if (processed > 1 && lastTime > firstTime) (processed - 1) * 1000.0 / (lastTime - firstTime) else 0.0)
        })
        addProperty("capture_model_compatibility", "unvalidated; matching schema does not prove training compatibility")
    }

    override fun close() { try { pose.close() } finally { hands.close() } }
}
