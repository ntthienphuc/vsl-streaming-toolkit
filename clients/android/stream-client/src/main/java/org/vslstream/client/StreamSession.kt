package org.vslstream.client

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.gson.JsonArray
import okhttp3.*
import java.util.ArrayDeque
import java.util.UUID
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

/** One connection, one outstanding request. Stop drains accepted frames, waits for
 * flush acknowledgment, then closes. No transparent reconnect or HTTP fallback. */
class StreamSession(
    private val url: String,
    private val capacity: Int = 120,
    private val timeoutSeconds: Long = 30,
    private val onReady: (JsonObject) -> Unit = {},
    private val onResult: (JsonObject) -> Unit = {},
    private val onFinished: (String?) -> Unit = {}
) {
    private val lock = Object()
    private val queue = ArrayDeque<JsonObject>()
    private val ready = CompletableFuture<JsonObject>()
    private var reply: CompletableFuture<JsonObject>? = null
    private var pendingId: String? = null
    private val client = OkHttpClient.Builder().pingInterval(15, TimeUnit.SECONDS).build()
    private var socket: WebSocket? = null
    private var accepting = true
    private var started = false
    private var terminal = false
    private var stopping = false
    private var offered = 0L
    private var enqueued = 0L
    private var dropped = 0L
    private var acked = 0L
    private var aborted = 0L
    private var rejected = 0L
    private var uncertain = 0L
    private var inFlight = 0
    private var inFlightSent = false
    private var requestNo = 0L
    private var flushAcknowledged = false
    private var failure: String? = null
    private val dropSeq = JsonArray()
    private var dropLogTruncated = 0L
    private var lastSeq = -1L
    private var lastTimestamp = -1.0
    private var maxBatch = 5
    private var maxBytes = 1_000_000
    private val prefix = UUID.randomUUID().toString()

    init { require(capacity > 0); require(timeoutSeconds > 0); require(url.startsWith("ws://") || url.startsWith("wss://")) }

    fun start() {
        synchronized(lock) { check(!started); started = true }
        socket = client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val value = JsonParser.parseString(text).asJsonObject
                    if (value.get("type")?.asString == "ready" && !ready.isDone) {
                        require(value.get("protocol_version")?.asInt == 1) { "Unsupported protocol" }
                        ready.complete(value)
                    } else synchronized(lock) {
                        require(reply != null && value.get("request_id")?.asString == pendingId) { "Unmatched server response" }
                        reply!!.complete(value)
                    }
                } catch (error: Exception) { failTransport(error) }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { failTransport(t) }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                synchronized(lock) { if (!terminal) failTransport(IllegalStateException("Disconnected ($code): $reason")) }
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, reason) }
        })
        Thread({ work() }, "vsl-stream-session").start()
    }

    private fun failTransport(error: Throwable) = synchronized(lock) {
        if (terminal) return@synchronized
        accepting = false
        failure = failure ?: (error.message ?: error.javaClass.simpleName)
        ready.completeExceptionally(error)
        reply?.completeExceptionally(error)
        lock.notifyAll()
    }

    /** Source sequence/timestamp are preserved, including gaps from dropped offers. */
    fun offer(frame: JsonObject): Boolean = synchronized(lock) {
        if (!accepting) return false
        validateOrder(frame)
        offered++
        if (queue.size >= capacity) {
            dropped++
            if (dropSeq.size() < 1000) dropSeq.add(frame.get("seq").asLong) else dropLogTruncated++
            return false
        }
        queue.addLast(frame.deepCopy()); enqueued++; lock.notifyAll(); true
    }

    fun offerBlocking(frame: JsonObject) = synchronized(lock) {
        while (accepting && queue.size >= capacity) lock.wait()
        check(accepting) { failure ?: "Session stopped" }
        check(offer(frame))
    }

    private fun validateOrder(frame: JsonObject) {
        val seqNumber = frame.get("seq")?.asBigDecimal ?: error("Missing seq")
        require(frame.get("seq").isJsonPrimitive && frame.getAsJsonPrimitive("seq").isNumber) { "seq must be a JSON number" }
        val seq = seqNumber.longValueExact()
        val time = frame.get("timestamp_ms")?.asDouble ?: error("Missing timestamp_ms")
        require(frame.get("timestamp_ms").isJsonPrimitive && frame.getAsJsonPrimitive("timestamp_ms").isNumber) { "timestamp_ms must be a JSON number" }
        require(seq >= 0 && seq > lastSeq && time.isFinite() && time >= 0 && time > lastTimestamp) {
            "Frames require strictly increasing nonnegative integer seq and finite timestamp_ms"
        }
        lastSeq = seq; lastTimestamp = time
    }

    fun requestStop() = synchronized(lock) { accepting = false; stopping = true; lock.notifyAll() }

    fun diagnostics(): JsonObject = synchronized(lock) {
        JsonObject().apply {
            addProperty("offered", offered); addProperty("enqueued", enqueued)
            addProperty("dropped_queue_full", dropped); add("dropped_seq", dropSeq.deepCopy())
            addProperty("dropped_seq_log_truncated", dropLogTruncated)
            addProperty("acknowledged_frames", acked); addProperty("aborted_queued_frames", aborted)
            addProperty("server_rejected_frames", rejected)
            addProperty("uncertain_in_flight_frames", uncertain); addProperty("queued", queue.size)
            addProperty("in_flight", inFlight); addProperty("queue_capacity", capacity)
            addProperty("flush_acknowledged", flushAcknowledged); addProperty("terminal", terminal)
            addProperty("failure", failure); addProperty("reconnect_policy", "new_session_no_automatic_replay")
        }
    }

    private fun request(message: JsonObject): JsonObject {
        val future = CompletableFuture<JsonObject>()
        val id = "$prefix-${++requestNo}"
        message.addProperty("request_id", id)
        synchronized(lock) { pendingId = id; reply = future }
        val text = message.toString()
        require(text.toByteArray(Charsets.UTF_8).size <= maxBytes) { "Message exceeds server byte limit" }
        synchronized(lock) {
            check(failure == null) { failure!! }
            check(socket!!.send(text)) { "WebSocket send failed" }
            inFlightSent = inFlight > 0
        }
        val result = future.get(timeoutSeconds, TimeUnit.SECONDS)
        synchronized(lock) { reply = null; pendingId = null }
        if (result.get("type")?.asString == "error") {
            synchronized(lock) { rejected += inFlight; inFlight = 0 }
            error("Server rejected request: $result")
        }
        check(result.get("type")?.asString == "result") { "Unexpected server response: $result" }
        check(result.get("events")?.isJsonArray == true && result.get("state")?.isJsonObject == true) {
            "Malformed result response"
        }
        return result
    }

    private fun work() {
        try {
            val hello = ready.get(timeoutSeconds, TimeUnit.SECONDS)
            val settings = hello.getAsJsonObject("settings")
            maxBatch = minOf(5, settings.get("max_batch_frames").asInt)
            maxBytes = settings.get("max_message_bytes").asInt
            require(maxBatch > 0 && maxBytes > 256)
            onReady(hello)
            while (true) {
                val batch = synchronized(lock) {
                    while (queue.isEmpty() && !stopping && failure == null) lock.wait()
                    check(failure == null) { failure!! }
                    if (queue.isEmpty() && stopping) null else JsonArray().apply {
                        var bytes = 256
                        while (queue.isNotEmpty() && size() < maxBatch) {
                            val frameBytes = queue.first.toString().toByteArray(Charsets.UTF_8).size + 1
                            require(frameBytes + 256 <= maxBytes) { "One frame exceeds server message limit" }
                            if (bytes + frameBytes > maxBytes) break
                            add(queue.removeFirst()); inFlight = size(); bytes += frameBytes
                        }
                        inFlight = size(); lock.notifyAll()
                    }
                } ?: break
                val result = request(JsonObject().apply { addProperty("type", "frames"); add("frames", batch) })
                synchronized(lock) { acked += inFlight; inFlight = 0; inFlightSent = false }
                onResult(result)
            }
            val flushed = request(JsonObject().apply { addProperty("type", "flush") })
            synchronized(lock) { flushAcknowledged = true }
            onResult(flushed)
        } catch (error: Exception) {
            synchronized(lock) {
                failure = failure ?: (error.cause?.message ?: error.message ?: error.javaClass.simpleName)
                if (inFlightSent) uncertain += inFlight else aborted += inFlight
                inFlight = 0; inFlightSent = false
                aborted += queue.size; queue.clear()
            }
        } finally {
            synchronized(lock) { accepting = false; terminal = true; lock.notifyAll() }
            socket?.close(1000, "Session finished")
            client.dispatcher.executorService.shutdown()
            client.connectionPool.evictAll()
            onFinished(failure)
        }
    }
}
