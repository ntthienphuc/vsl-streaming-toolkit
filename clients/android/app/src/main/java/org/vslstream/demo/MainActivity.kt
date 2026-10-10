package org.vslstream.demo

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import org.vslstream.client.LandmarkCapture
import org.vslstream.client.StreamSession
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : ComponentActivity() {
    private lateinit var endpoint: EditText
    private lateinit var fps: EditText
    private lateinit var status: TextView
    private lateinit var preview: PreviewView
    private val executor = Executors.newSingleThreadExecutor()
    private var session: StreamSession? = null
    private var capture: LandmarkCapture? = null
    private var provider: ProcessCameraProvider? = null
    private var analyzer: ImageAnalysis? = null
    private val stopRequested = AtomicBoolean(false)
    private var active = false
    private var sourceReceipt = JsonObject()
    private val events = JsonArray()
    private var eventLogOmitted = 0L
    private var replayUri: Uri? = null
    private var captureFile: File? = null
    private var captureWriter: java.io.BufferedWriter? = null
    private var traceFrames = 0L
    private val selectReplay = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) { replayUri = uri; log("Selected replay file. Press Replay to start a fresh session.") }
    }
    private val exportReceipt = registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) contentResolver.openOutputStream(uri)?.use { it.write(receipt().toString().toByteArray(Charsets.UTF_8)) }
    }
    private val exportTrace = registerForActivityResult(ActivityResultContracts.CreateDocument("application/x-ndjson")) { uri ->
        val file = captureFile
        if (uri != null && file != null && !active) contentResolver.openOutputStream(uri)?.use { output -> file.inputStream().use { it.copyTo(output) } }
    }
    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startCamera() else log("Camera permission denied. File replay remains available.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 24, 24, 24) }
        root.addView(TextView(this).apply { text = "VSL Stream — capture and replay"; textSize = 22f })
        root.addView(TextView(this).apply { text = "Research example. Camera/model compatibility and device latency require validation. Camera frames remain local; landmarks go to the configured server." })
        endpoint = EditText(this).apply { setText("ws://10.0.2.2:8000/v1/stream"); isSingleLine = true; hint = "Server WebSocket URL" }
        root.addView(endpoint)
        fps = EditText(this).apply { setText("15"); hint = "Target capture FPS (1–30)"; inputType = 2 }
        root.addView(fps)
        fun button(label: String, action: () -> Unit) { root.addView(Button(this).apply { text = label; setOnClickListener { action() } }) }
        button("Inspect server / bundle configuration") {
            val url = endpoint.text.toString().trim().replaceFirst("ws://", "http://").replaceFirst("wss://", "https://").removeSuffix("/v1/stream") + "/v1/config"
            Thread {
                try {
                    val connection = java.net.URL(url).openConnection() as java.net.HttpURLConnection
                    connection.connectTimeout = 5000; connection.readTimeout = 5000
                    try { log(connection.inputStream.bufferedReader().use { it.readText() }.take(12000)) }
                    finally { connection.disconnect() }
                } catch (e: Exception) { log("Configuration request failed: ${e.message}") }
            }.start()
        }
        button("Choose canonical frames JSON / JSONL") { if (!active) selectReplay.launch(arrayOf("application/json", "application/octet-stream", "text/plain", "application/x-ndjson")) }
        button("Replay selected file") { replayUri?.let(::startReplay) ?: log("Choose a file first.") }
        button("Start front camera") {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) startCamera()
            else cameraPermission.launch(Manifest.permission.CAMERA)
        }
        button("Stop, drain, flush and close") { stop() }
        button("Export final diagnostics") { if (active) log("Stop and wait for completion first.") else exportReceipt.launch("vsl-capture-receipt.json") }
        button("Export captured canonical frames") { if (active) log("Stop and wait for completion first.") else if (captureFile != null) exportTrace.launch("vsl-capture.jsonl") else log("No camera trace in this session.") }
        preview = PreviewView(this)
        root.addView(preview, LinearLayout.LayoutParams(-1, 360))
        status = TextView(this).apply { text = "Idle. Debug builds allow cleartext LAN. Release builds require WSS."; setTextIsSelectable(true) }
        root.addView(status)
        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun log(message: String) = runOnUiThread {
        status.text = (message + "\n" + status.text).take(12000)
    }

    private fun begin(): StreamSession? {
        if (active) { log("A session is active. Stop it before starting another."); return null }
        val url = endpoint.text.toString().trim()
        if (!url.endsWith("/v1/stream")) { log("Use the server /v1/stream endpoint."); return null }
        if (!BuildConfig.DEBUG && !url.startsWith("wss://")) { log("Release builds require wss://."); return null }
        stopRequested.set(false); sourceReceipt = JsonObject(); events.asList().clear(); eventLogOmitted = 0
        active = true
        return try {
            StreamSession(url, onReady = { hello -> log("Ready: ${hello.get("session_id")}") }, onResult = { result ->
                synchronized(events) { if (events.size() < 500) events.add(result.deepCopy()) else eventLogOmitted++ }
                val output = result.get("events")
                log("Result: $output")
            }, onFinished = { error ->
                // Stop admission immediately; finalize camera data on its own executor.
                stopRequested.set(true)
                runOnUiThread { analyzer?.clearAnalyzer(); provider?.unbindAll() }
                executor.execute {
                    finishCapture()
                    runOnUiThread { active = false; log(if (error == null) "Completed: flush acknowledged, socket closed." else "Failed: $error. See diagnostics; no automatic retry.") }
                }
            }).also { session = it; it.start() }
        } catch (e: Exception) { active = false; log("Cannot start: ${e.message}"); null }
    }

    private fun startReplay(uri: Uri) {
        if (active) { log("Stop the current session first."); return }
        val stream = begin() ?: return
        captureFile = null
        executor.execute {
            try {
                // Bound import memory. This example is for replay fixtures, not arbitrary datasets.
                val bytes = contentResolver.openInputStream(uri)!!.use { input ->
                    val output = java.io.ByteArrayOutputStream()
                    val buffer = ByteArray(65536)
                    while (true) { val n = input.read(buffer); if (n < 0) break
                        require(output.size() + n <= 20 * 1024 * 1024) { "Replay file exceeds 20 MiB" }
                        output.write(buffer, 0, n)
                    }
                    output.toByteArray()
                }
                sourceReceipt.addProperty("schema_version", 1)
                sourceReceipt.addProperty("extractor_profile", "replay_input_unspecified")
                sourceReceipt.addProperty("frames_sha256", sha(bytes))
                sourceReceipt.addProperty("replay_pacing", "acknowledgment_bounded; not original wall-clock FPS")
                val text = bytes.toString(Charsets.UTF_8).trim().removePrefix("\uFEFF")
                val frames = if (text.startsWith("[")) JsonParser.parseString(text).asJsonArray.map { it.asJsonObject }
                    else if (text.startsWith("{") && runCatching { JsonParser.parseString(text).asJsonObject.has("frames") }.getOrDefault(false))
                        JsonParser.parseString(text).asJsonObject.getAsJsonArray("frames").map { it.asJsonObject }
                    else text.lineSequence().filter { it.isNotBlank() }.map { JsonParser.parseString(it).asJsonObject }.toList()
                require(frames.isNotEmpty()) { "No frames" }
                for (frame in frames) { if (stopRequested.get()) break; stream.offerBlocking(frame) }
                sourceReceipt.addProperty("input_frames", frames.size)
            } catch (e: Exception) { sourceReceipt.addProperty("replay_error", e.message); log("Replay stopped: ${e.message}") }
            finally { stream.requestStop() }
        }
    }

    private fun startCamera() {
        if (active) { log("Stop the current session first."); return }
        val target = fps.text.toString().toIntOrNull()
        if (target == null || target !in 1..30) { log("FPS must be 1–30."); return }
        val stream = begin() ?: return
        captureFile = File(cacheDir, "vsl-capture.jsonl")
        traceFrames = 0
        executor.execute {
            try {
                captureWriter = captureFile!!.bufferedWriter(Charsets.UTF_8)
                capture = LandmarkCapture(this, target, true, onFrame = { frame ->
                    if (!stopRequested.get()) {
                        // Enqueued input can be replayed without guessing transport drop positions.
                        if (stream.offer(frame)) {
                            captureWriter!!.append(frame.toString()).append('\n')
                            traceFrames++
                        }
                    }
                }, onError = { error -> log("Extraction failure: ${error.message}"); stopRequested.set(true); runOnUiThread { stop() } })
                runOnUiThread {
                    val future = ProcessCameraProvider.getInstance(this)
                    future.addListener({
                        try {
                            if (stopRequested.get()) return@addListener
                            provider = future.get()
                            require(provider!!.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)) { "Front camera unavailable" }
                            val livePreview = Preview.Builder().build().also { it.setSurfaceProvider(preview.surfaceProvider) }
                            analyzer = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                                .also { it.setAnalyzer(executor, capture!!) }
                            provider!!.bindToLifecycle(this, CameraSelector.DEFAULT_FRONT_CAMERA, livePreview, analyzer)
                        } catch (e: Exception) { log("Camera start failed: ${e.message}"); stop() }
                    }, ContextCompat.getMainExecutor(this))
                }
            } catch (e: Exception) { log("Capture initialization failed: ${e.message}"); stream.requestStop() }
        }
    }

    private fun stop() {
        stopRequested.set(true)
        analyzer?.clearAnalyzer(); provider?.unbindAll()
        executor.execute { finishCapture(); session?.requestStop() }
    }

    private fun finishCapture() {
        capture?.let { sourceReceipt = it.receipt(); it.close() }; capture = null
        captureWriter?.close(); captureWriter = null
        captureFile?.takeIf { it.exists() }?.let { file ->
            sourceReceipt.getAsJsonObject("sampling")?.addProperty("trace_frames", traceFrames)
            sourceReceipt.addProperty("frames_sha256", file.inputStream().use { input ->
                val digest = MessageDigest.getInstance("SHA-256"); val buffer = ByteArray(65536)
                while (true) { val n = input.read(buffer); if (n < 0) break; digest.update(buffer, 0, n) }
                digest.digest().joinToString("") { "%02x".format(it) }
            })
            sourceReceipt.addProperty("trace_scope", "frames admitted to transport queue; inspect acknowledged/uncertain counters before parity claims")
        }
    }

    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private fun receipt() = sourceReceipt.deepCopy().apply {
        addProperty("schema_version", 1)
        add("transport", session?.diagnostics() ?: JsonObject())
        synchronized(events) { add("responses", events.deepCopy()); addProperty("response_log_omitted", eventLogOmitted) }
        addProperty("device_measurements_validated", false)
    }

    override fun onStop() { if (active) stop(); super.onStop() }
    override fun onDestroy() { if (active) stop(); super.onDestroy() }
}
