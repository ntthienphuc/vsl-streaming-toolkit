package org.vslstream.flutterdemo

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import android.view.View
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.StandardMessageCodec
import io.flutter.plugin.platform.PlatformView
import io.flutter.plugin.platform.PlatformViewFactory
import org.vslstream.client.LandmarkCapture
import org.vslstream.client.StreamSession
import java.io.File
import java.net.HttpURLConnection
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/** Presentation bridge only. The native reference client's extractor and
 * transport module are reused directly, including their capture profile.
 * No historical Flutter transport, filtering, cached hands, or model is used. */
class MainActivity : FlutterFragmentActivity(), MethodChannel.MethodCallHandler, EventChannel.StreamHandler {
    private val captureExecutor = Executors.newSingleThreadExecutor()
    private val ioExecutor = Executors.newSingleThreadExecutor()
    private var eventSink: EventChannel.EventSink? = null
    private var preview: PreviewView? = null
    private var session: StreamSession? = null
    private var capture: LandmarkCapture? = null
    private var provider: ProcessCameraProvider? = null
    private var analyzer: ImageAnalysis? = null
    private val stopRequested = AtomicBoolean(false)
    private val sourceFailure = AtomicReference<String?>(null)
    @Volatile private var serverReady: JsonObject? = null
    @Volatile private var active = false
    private var phase = "idle"
    private var message = "Connect a toolkit server, then choose live capture or canonical replay."
    private var mode = ""
    private var stopReason = ""
    // Source fields are written on captureExecutor, and published after it drains.
    private var sourceReceipt = JsonObject()
    @Volatile private var finalReceipt: JsonObject? = null
    private val responses = JsonArray()
    private var responseLogOmitted = 0L
    private var captureFile: File? = null
    private var captureWriter: java.io.BufferedWriter? = null
    private var traceFrames = 0L
    private var traceBytes = 0L
    private var replayUri: Uri? = null
    private var replayName: String? = null
    private var pickerBusy = false
    private var exporting = false
    private var pendingReceipt: ByteArray? = null
    private var pendingTrace: File? = null
    private var pendingLive: Pair<String, Int>? = null

    private val replayPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        pickerBusy = false
        if (uri != null) {
            replayUri = uri
            replayName = runCatching {
                contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                    if (it.moveToFirst()) it.getString(0) else null
                }
            }.getOrNull() ?: "Selected canonical file"
        }
        emit("selection", mapOf("name" to replayName, "selecting" to false, "cancelled" to (uri == null)))
    }
    private val receiptPicker = registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        val bytes = pendingReceipt
        pendingReceipt = null
        pickerBusy = false
        if (uri == null) finishExport("receipt", "cancelled", "Diagnostics export cancelled.")
        else writeExport("receipt", uri) { it.write(requireNotNull(bytes) { "Export snapshot lost; export again." }) }
    }
    private val framesPicker = registerForActivityResult(ActivityResultContracts.CreateDocument("application/x-ndjson")) { uri ->
        val file = pendingTrace
        pendingTrace = null
        pickerBusy = false
        if (uri == null) finishExport("frames", "cancelled", "Frame export cancelled.")
        else writeExport("frames", uri) { out ->
            requireNotNull(file) { "Export snapshot lost; export again." }.inputStream().use { it.copyTo(out) }
        }
    }
    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val request = pendingLive
        pendingLive = null
        if (request != null && granted && !isFinishing && !isDestroyed) {
            try { startCamera(request.first, request.second) }
            catch (e: Exception) { status("failed", e.message ?: "Camera start failed.") }
        } else if (request != null) status("failed", "Camera permission denied. Canonical replay remains available.")
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "vsl_streaming/bridge").setMethodCallHandler(this)
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, "vsl_streaming/events").setStreamHandler(this)
        flutterEngine.platformViewsController.registry.registerViewFactory(
            "vsl_streaming/camera",
            object : PlatformViewFactory(StandardMessageCodec.INSTANCE) {
                override fun create(context: Context, viewId: Int, args: Any?): PlatformView {
                    val view = PreviewView(context).apply {
                        implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                        scaleType = PreviewView.ScaleType.FIT_CENTER
                    }
                    preview = view
                    emit("cameraPreviewReady", mapOf("ready" to true))
                    return object : PlatformView {
                        override fun getView(): View = view
                        override fun dispose() {
                            if (preview === view) {
                                if (active && mode == "live") stop("preview_disposed")
                                preview = null
                                emit("cameraPreviewReady", mapOf("ready" to false))
                            }
                        }
                    }
                }
            })
    }

    override fun onListen(arguments: Any?, sink: EventChannel.EventSink) {
        eventSink = sink
        emit("status", mapOf("phase" to phase, "message" to message, "active" to active))
        emit("cameraPreviewReady", mapOf("ready" to (preview != null)))
        emitDiagnostics()
    }
    override fun onCancel(arguments: Any?) { eventSink = null }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        try {
            when (call.method) {
                "inspect" -> { inspect(endpoint(call), result); return }
                "inspectVideo" -> {
                    inspectVideo(call.argument<String>("path").orEmpty(), result)
                    return
                }
                "snapshot" -> result.success(snapshot())
                "startLive" -> {
                    requireIdle()
                    val url = endpoint(call)
                    val target = (call.argument<Number>("targetFps") ?: 15).toInt()
                    require(target in 1..30) { "Target FPS must be 1–30." }
                    check(preview != null) { "Wait for the camera preview to be ready." }
                    if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                        pendingLive = url to target
                        status("awaiting_permission", "Camera permission is required only for live capture.")
                        cameraPermission.launch(Manifest.permission.CAMERA)
                    } else startCamera(url, target)
                    result.success(snapshot())
                }
                "stop" -> { pendingLive = null; stop("user_stop"); result.success(snapshot()) }
                "selectReplay" -> {
                    requireIdle()
                    pickerBusy = true
                    emit("selection", mapOf("name" to replayName, "selecting" to true))
                    try { replayPicker.launch(arrayOf("application/json", "application/octet-stream", "text/plain", "application/x-ndjson")) }
                    catch (e: Exception) {
                        pickerBusy = false
                        emit("selection", mapOf("name" to replayName, "selecting" to false, "cancelled" to true))
                        throw e
                    }
                    result.success(null)
                }
                "startReplay" -> {
                    requireIdle()
                    val uri = requireNotNull(replayUri) { "Choose a canonical JSON / JSONL file first." }
                    startReplay(endpoint(call), uri)
                    result.success(snapshot())
                }
                "exportReceipt" -> { chooseExport("receipt"); result.success(null) }
                "exportFrames" -> { chooseExport("frames"); result.success(null) }
                else -> result.notImplemented()
            }
        } catch (e: Exception) {
            result.error("bridge_error", e.message ?: e.javaClass.simpleName, null)
        }
    }

    private fun endpoint(call: MethodCall): String {
        val url = call.argument<String>("endpoint")?.trim().orEmpty()
        val uri = java.net.URI(url)
        require(uri.scheme in listOf("ws", "wss") && !uri.host.isNullOrBlank() &&
            uri.path == "/v1/stream" && uri.fragment == null && uri.userInfo == null && uri.query == null) {
            "Use a ws:// or wss:// server endpoint ending in /v1/stream, without credentials or query."
        }
        require(BuildConfig.DEBUG || uri.scheme == "wss") { "Release builds require wss://." }
        return url
    }

    private fun requireIdle() {
        check(!active) { "Stop the current session and wait for completion first." }
        check(!pickerBusy && !exporting) { "Finish or cancel the current file picker/export first." }
        check(pendingLive == null) { "A camera permission request is pending." }
    }

    private fun emit(type: String, fields: Map<String, Any?> = emptyMap()) {
        runOnUiThread { if (!isDestroyed) eventSink?.success(mapOf("type" to type) + fields) }
    }
    private fun status(next: String, text: String) {
        runOnUiThread {
            phase = next
            message = text
            emit("status", mapOf("phase" to phase, "message" to message, "active" to active))
        }
    }
    private fun sourceFailed(text: String) {
        sourceFailure.compareAndSet(null, text)
        status("stopping", text)
    }

    private fun jsonValue(value: JsonElement?): Any? {
        if (value == null || value.isJsonNull) return null
        if (value.isJsonObject) return value.asJsonObject.entrySet().associate { it.key to jsonValue(it.value) }
        if (value.isJsonArray) return value.asJsonArray.map { jsonValue(it) }
        val primitive = value.asJsonPrimitive
        return when {
            primitive.isBoolean -> primitive.asBoolean
            primitive.isNumber -> primitive.asString.toLongOrNull() ?: primitive.asDouble
            else -> primitive.asString
        }
    }

    private fun diagnostics(): JsonObject = finalReceipt?.deepCopy() ?: JsonObject().apply {
        addProperty("schema_version", 1)
        addProperty("extractor_profile", if (mode == "live") LandmarkCapture.PROFILE else "replay_input_unspecified")
        add("transport", session?.diagnostics() ?: JsonObject())
        add("server_ready", serverReady?.deepCopy())
        addProperty("source_failure", sourceFailure.get())
        addProperty("device_measurements_validated", false)
    }

    private fun emitDiagnostics() = emit("diagnostics", mapOf(
        "data" to jsonValue(diagnostics()), "finalized" to (finalReceipt != null)))

    private fun snapshot(): Map<String, Any?> = mapOf(
        "phase" to phase, "message" to message, "active" to active,
        "previewReady" to (preview != null), "replayName" to replayName,
        "exporting" to exporting, "selecting" to (pickerBusy && !exporting),
        "hasReceipt" to (finalReceipt != null && !active),
        "hasFrames" to (captureFile?.exists() == true && finalReceipt != null && !active),
        "diagnostics" to jsonValue(diagnostics())
    )

    private fun inspectVideo(path: String, result: MethodChannel.Result) {
        ioExecutor.execute {
            try {
                require(path.isNotBlank()) { "Choose a local video file first." }
                val file = File(path)
                require(file.isFile && file.canRead()) { "Selected video is missing or unreadable; select it again." }
                val bytes = file.length()
                require(bytes > 0) { "Selected video is empty." }
                val retriever = MediaMetadataRetriever()
                val metadata = try {
                    retriever.setDataSource(file.absolutePath)
                    fun number(key: Int, name: String): Long =
                        retriever.extractMetadata(key)?.toLongOrNull()
                            ?: error("Video $name metadata is unavailable.")
                    val width = number(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH, "width")
                    val height = number(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT, "height")
                    val rotation = number(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION, "rotation")
                    val duration = number(MediaMetadataRetriever.METADATA_KEY_DURATION, "duration")
                    require(width in 1..Int.MAX_VALUE.toLong() && height in 1..Int.MAX_VALUE.toLong()) {
                        "Video dimensions are invalid."
                    }
                    require(rotation in listOf(0L, 90L, 180L, 270L)) { "Video rotation metadata is unsupported." }
                    require(duration >= 0) { "Video duration is invalid." }
                    mapOf("width" to width.toInt(), "height" to height.toInt(),
                        "rotation" to rotation.toInt(), "duration_ms" to duration, "bytes" to bytes)
                } finally { retriever.release() }
                runOnUiThread { result.success(metadata) }
            } catch (e: Exception) {
                runOnUiThread { result.error("video_inspect_failed", e.message ?: "Cannot inspect selected video.", null) }
            }
        }
    }

    private fun inspect(url: String, result: MethodChannel.Result) {
        ioExecutor.execute {
            try {
                val httpUrl = url.replaceFirst("ws://", "http://").replaceFirst("wss://", "https://")
                    .removeSuffix("/v1/stream") + "/v1/config"
                val connection = java.net.URL(httpUrl).openConnection() as HttpURLConnection
                connection.connectTimeout = 5000
                connection.readTimeout = 5000
                connection.instanceFollowRedirects = false
                val config = try {
                    check(connection.responseCode in 200..299) { "Configuration request returned HTTP " + connection.responseCode }
                    connection.inputStream.use { JsonParser.parseString(readBounded(it, 1024 * 1024).toString(Charsets.UTF_8)).asJsonObject }
                } finally { connection.disconnect() }
                runOnUiThread {
                    emit("config", mapOf("data" to jsonValue(config)))
                    result.success(jsonValue(config))
                }
            } catch (e: Exception) {
                runOnUiThread { result.error("inspect_failed", e.message ?: "Configuration request failed.", null) }
            }
        }
    }

    // Create the connection before source work, but start its worker only after
    // source initialization is enqueued: even immediate network failure then
    // finalizes behind source work on the same serial executor.
    private fun begin(url: String, sourceMode: String): StreamSession {
        requireIdle()
        stopRequested.set(false)
        sourceFailure.set(null)
        serverReady = null
        sourceReceipt = JsonObject()
        finalReceipt = null
        captureFile = null
        traceFrames = 0
        traceBytes = 0
        mode = sourceMode
        stopReason = ""
        synchronized(responses) { responses.asList().clear(); responseLogOmitted = 0 }
        val stream = StreamSession(url,
            onReady = { hello ->
                serverReady = hello.deepCopy()
                emit("ready", mapOf("data" to jsonValue(hello)))
                emitDiagnostics()
            },
            onResult = { response ->
                synchronized(responses) {
                    if (responses.size() < 500) responses.add(response.deepCopy()) else responseLogOmitted++
                }
                emit("result", mapOf("data" to jsonValue(response)))
                emitDiagnostics()
            },
            onFinished = { error ->
                stopRequested.set(true)
                runOnUiThread {
                    analyzer?.clearAnalyzer()
                    provider?.unbindAll()
                    captureExecutor.execute {
                        try { finishCapture() }
                        catch (e: Exception) { sourceFailed("Capture finalization failed: " + e.message) }
                        val receipt = receipt()
                        runOnUiThread {
                            finalReceipt = receipt
                            active = false
                            val problem = error ?: sourceFailure.get()
                            status(if (problem == null) "completed" else "failed",
                                if (problem == null) "Completed: flush acknowledged; socket close requested."
                                else "Failed: $problem. Inspect diagnostics; no automatic retry.")
                            emitDiagnostics()
                            if (isDestroyed) captureExecutor.shutdown()
                        }
                    }
                }
            })
        session = stream
        active = true
        status("connecting", "Opening a fresh stream session.")
        return stream
    }

    private fun startCamera(url: String, target: Int) {
        check(preview != null) { "Wait for the camera preview to be ready." }
        val stream = begin(url, "live")
        captureExecutor.execute {
            try {
                if (stopRequested.get()) return@execute
                captureFile = File.createTempFile("vsl-flutter-capture-", ".jsonl", cacheDir)
                captureWriter = captureFile!!.bufferedWriter(Charsets.UTF_8)
                capture = LandmarkCapture(this, target, true,
                    onFrame = { frame ->
                        if (!stopRequested.get()) {
                            val line = frame.toString() + "\n"
                            val size = line.toByteArray(Charsets.UTF_8).size
                            require(traceBytes + size <= MAX_TRACE_BYTES) {
                                "Capture reached 20 MiB trace limit. Export this session and start another."
                            }
                            if (stream.offer(frame)) {
                                captureWriter!!.append(line)
                                traceFrames++
                                traceBytes += size
                            }
                        }
                    },
                    onError = { error ->
                        sourceFailed("Capture failure: " + error.message)
                        stopRequested.set(true)
                        runOnUiThread { stop("capture_failure") }
                    })
                runOnUiThread {
                    if (session !== stream || stopRequested.get() || isDestroyed) return@runOnUiThread
                    val future = ProcessCameraProvider.getInstance(this)
                    future.addListener({
                        try {
                            if (session !== stream || stopRequested.get() || isDestroyed) return@addListener
                            provider = future.get()
                            require(provider!!.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)) { "Front camera unavailable." }
                            val cameraPreview = requireNotNull(preview) { "Camera preview was removed." }
                            val livePreview = Preview.Builder().build().also { it.setSurfaceProvider(cameraPreview.surfaceProvider) }
                            analyzer = ImageAnalysis.Builder()
                                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                                .also { it.setAnalyzer(captureExecutor, requireNotNull(capture)) }
                            provider!!.bindToLifecycle(this, CameraSelector.DEFAULT_FRONT_CAMERA, livePreview, analyzer)
                            status("capturing", if (serverReady == null)
                                "Front camera active; waiting for the server handshake."
                                else "Front camera active. Landmarks stream to the configured server.")
                            emitDiagnostics()
                        } catch (e: Exception) {
                            sourceFailed("Camera start failed: " + e.message)
                            stop("camera_start_failed")
                        }
                    }, ContextCompat.getMainExecutor(this))
                }
            } catch (e: Exception) {
                sourceFailed("Capture initialization failed: " + e.message)
                stopRequested.set(true)
                stream.requestStop()
            }
        }
        stream.start()
    }

    private fun startReplay(url: String, uri: Uri) {
        val stream = begin(url, "replay")
        captureExecutor.execute {
            try {
                val bytes = requireNotNull(contentResolver.openInputStream(uri)) { "Cannot read the selected file." }
                    .use { readBounded(it, MAX_TRACE_BYTES.toInt()) }
                sourceReceipt.addProperty("schema_version", 1)
                sourceReceipt.addProperty("extractor_profile", "replay_input_unspecified")
                sourceReceipt.addProperty("frames_sha256", sha(bytes))
                sourceReceipt.addProperty("replay_pacing", "acknowledgment_bounded; not original wall-clock FPS")
                val text = bytes.toString(Charsets.UTF_8).trim().removePrefix("\uFEFF")
                val parsed = if (text.startsWith("[")) JsonParser.parseString(text) else null
                val wrapped = if (text.startsWith("{")) runCatching { JsonParser.parseString(text).asJsonObject }
                    .getOrNull()?.takeIf { it.has("frames") } else null
                val frames = when {
                    parsed != null -> parsed.asJsonArray.map { it.asJsonObject }
                    wrapped != null -> wrapped.getAsJsonArray("frames").map { it.asJsonObject }
                    else -> text.lineSequence().filter { it.isNotBlank() }
                        .map { JsonParser.parseString(it).asJsonObject }.toList()
                }
                require(frames.isNotEmpty()) { "No canonical frames in the selected file." }
                sourceReceipt.addProperty("input_frames", frames.size)
                status("replaying", "Replaying canonical frames with acknowledgment-paced admission.")
                for (frame in frames) {
                    if (stopRequested.get()) break
                    stream.offerBlocking(frame)
                }
                sourceReceipt.addProperty("replay_interrupted", stopRequested.get())
            } catch (e: Exception) {
                if (stopRequested.get()) sourceReceipt.addProperty("replay_interrupted", true)
                else {
                    sourceReceipt.addProperty("replay_error", e.message)
                    sourceFailed("Replay stopped: " + e.message)
                }
            } finally {
                runOnUiThread {
                    if (active && session === stream) status("stopping", "Draining admitted frames and waiting for flush acknowledgment.")
                }
                stream.requestStop()
            }
        }
        stream.start()
    }

    private fun stop(reason: String) {
        if (!active) {
            if (phase == "awaiting_permission") status("idle", "Camera start cancelled.")
            return
        }
        if (stopReason.isEmpty()) stopReason = reason
        stopRequested.set(true)
        analyzer?.clearAnalyzer()
        provider?.unbindAll()
        session?.requestStop()
        status("stopping", "Capture stopped. Draining admitted frames and waiting for flush acknowledgment.")
    }

    private fun finishCapture() {
        val detector = capture
        capture = null
        try { detector?.let { sourceReceipt = it.receipt(); it.close() } }
        finally {
            val writer = captureWriter
            captureWriter = null
            writer?.close()
        }
        captureFile?.takeIf { it.exists() }?.let { file ->
            sourceReceipt.getAsJsonObject("sampling")?.addProperty("trace_frames", traceFrames)
            sourceReceipt.addProperty("trace_bytes", file.length())
            sourceReceipt.addProperty("trace_limit_bytes", MAX_TRACE_BYTES)
            sourceReceipt.addProperty("trace_matches_admitted_frames",
                traceFrames == session?.diagnostics()?.get("enqueued")?.asLong)
            sourceReceipt.addProperty("frames_sha256", file.inputStream().use { input ->
                val digest = MessageDigest.getInstance("SHA-256")
                val buffer = ByteArray(65536)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    digest.update(buffer, 0, count)
                }
                digest.digest().joinToString("") { "%02x".format(it) }
            })
            sourceReceipt.addProperty("trace_scope",
                "frames admitted to transport queue; inspect acknowledged/uncertain counters before parity claims")
        }
    }

    private fun receipt() = sourceReceipt.deepCopy().apply {
        addProperty("schema_version", 1)
        if (!has("extractor_profile")) addProperty("extractor_profile",
            if (mode == "live") LandmarkCapture.PROFILE else "replay_input_unspecified")
        add("android_client", JsonObject().apply {
            addProperty("application_id", BuildConfig.APPLICATION_ID)
            addProperty("version_name", BuildConfig.VERSION_NAME)
            addProperty("version_code", BuildConfig.VERSION_CODE)
            addProperty("build_type", BuildConfig.BUILD_TYPE)
            addProperty("client_variant", "flutter_demo_native_bridge")
            addProperty("device_manufacturer", Build.MANUFACTURER)
            addProperty("device_model", Build.MODEL)
            addProperty("android_release", Build.VERSION.RELEASE)
            addProperty("android_sdk", Build.VERSION.SDK_INT)
        })
        add("transport", session?.diagnostics() ?: JsonObject())
        add("server_ready", serverReady?.deepCopy())
        addProperty("source_failure", sourceFailure.get())
        addProperty("stop_reason", stopReason.ifEmpty { "source_completed_or_transport_terminated" })
        synchronized(responses) {
            add("responses", responses.deepCopy())
            addProperty("response_log_omitted", responseLogOmitted)
        }
        addProperty("device_measurements_validated", false)
    }

    private fun chooseExport(kind: String) {
        requireIdle()
        check(finalReceipt != null) { "No completed session to export." }
        if (kind == "frames") check(captureFile?.exists() == true) { "This session has no captured camera trace." }
        exporting = true
        pickerBusy = true
        emit("export", mapOf("kind" to kind, "status" to "choosing", "message" to "Choose an export destination."))
        try {
            if (kind == "receipt") {
                pendingReceipt = requireNotNull(finalReceipt).toString().toByteArray(Charsets.UTF_8)
                receiptPicker.launch("vsl-capture-receipt.json")
            } else {
                pendingTrace = captureFile
                framesPicker.launch("vsl-capture.jsonl")
            }
        } catch (e: Exception) {
            pendingReceipt = null
            pendingTrace = null
            pickerBusy = false
            finishExport(kind, "failed", e.message ?: "Cannot open export picker.")
            throw e
        }
    }

    private fun writeExport(kind: String, uri: Uri, write: (java.io.OutputStream) -> Unit) {
        emit("export", mapOf("kind" to kind, "status" to "writing", "message" to "Writing the frozen session artifact."))
        ioExecutor.execute {
            try {
                requireNotNull(contentResolver.openOutputStream(uri, "wt")) { "Cannot open export destination." }.use(write)
                finishExport(kind, "completed", "Export completed.")
            } catch (e: Exception) {
                finishExport(kind, "failed", "Export failed: " + e.message + ". Destination may be incomplete; retry export.")
            }
        }
    }

    private fun finishExport(kind: String, state: String, text: String) {
        runOnUiThread {
            exporting = false
            emit("export", mapOf("kind" to kind, "status" to state, "message" to text))
        }
    }

    private fun readBounded(input: java.io.InputStream, limit: Int): ByteArray {
        val output = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(65536)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            require(output.size() + count <= limit) { "Input exceeds the " + limit + "-byte limit." }
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }

    private fun sha(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    override fun onStop() {
        if (active) stop("activity_backgrounded")
        super.onStop()
    }

    override fun onDestroy() {
        pendingLive = null
        if (active) stop("activity_destroyed") else captureExecutor.shutdown()
        ioExecutor.shutdown()
        eventSink = null
        super.onDestroy()
    }

    companion object { private const val MAX_TRACE_BYTES = 20L * 1024 * 1024 }
}
