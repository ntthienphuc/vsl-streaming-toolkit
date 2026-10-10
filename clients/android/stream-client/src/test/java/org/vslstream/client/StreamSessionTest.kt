package org.vslstream.client

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.Collections

class StreamSessionTest {
    private fun frame(seq: Int) = JsonParser.parseString("""{"seq":$seq,"timestamp_ms":${seq * 66},"pose_landmarks":null,"left_hand_landmarks":null,"right_hand_landmarks":null}""").asJsonObject
    private val ready = """{"type":"ready","session_id":"unit","protocol_version":1,"settings":{"max_batch_frames":2,"max_message_bytes":100000}}"""
    private fun result(message: JsonObject) = """{"type":"result","request_id":"${message.get("request_id").asString}","events":[],"state":{}}"""

    @Test fun boundedAdmissionCountsDropsAndPreservesSequenceGaps() {
        val session = StreamSession("ws://127.0.0.1:1/v1/stream", capacity = 2)
        assertTrue(session.offer(frame(0))); assertTrue(session.offer(frame(1)))
        assertFalse(session.offer(frame(2)))
        val d = session.diagnostics()
        assertEquals(3, d["offered"].asInt); assertEquals(2, d["enqueued"].asInt)
        assertEquals(1, d["dropped_queue_full"].asInt)
        assertEquals(2, d.getAsJsonArray("dropped_seq")[0].asInt)
    }

    @Test fun invalidOrderDoesNotAlterLedger() {
        val session = StreamSession("ws://127.0.0.1:1/v1/stream")
        session.offer(frame(1))
        assertThrows(IllegalArgumentException::class.java) { session.offer(frame(1)) }
        assertEquals(1, session.diagnostics()["offered"].asInt)
    }

    @Test fun numericStringsAreRejectedWithoutConsumingSequence() {
        val session = StreamSession("ws://127.0.0.1:1/v1/stream")
        val invalid = frame(0).apply { addProperty("seq", "0") }
        assertThrows(IllegalArgumentException::class.java) { session.offer(invalid) }
        assertTrue(session.offer(frame(0)))
    }

    @Test fun stopWakesBlockedReplayProducer() {
        val session = StreamSession("ws://127.0.0.1:1/v1/stream", capacity = 1)
        session.offer(frame(0))
        val entered = CountDownLatch(1); val stopped = CountDownLatch(1)
        val producer = Thread {
            entered.countDown()
            try { session.offerBlocking(frame(1)); fail("Stopped producer must not admit another frame") }
            catch (_: IllegalStateException) { stopped.countDown() }
        }
        producer.start(); assertTrue(entered.await(1, TimeUnit.SECONDS))
        session.requestStop()
        assertTrue(stopped.await(1, TimeUnit.SECONDS)); producer.join(1000)
        assertEquals(1, session.diagnostics()["enqueued"].asInt)
    }

    @Test fun oversizeBatchFramesNeverSentAreAbortedNotUncertain() {
        val server = MockWebServer(); val finished = CountDownLatch(1)
        server.enqueue(MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { ws.send(ready) }
            override fun onClosing(ws: WebSocket, code: Int, reason: String) { ws.close(code, reason) }
        }))
        server.start()
        try {
            val session = StreamSession(server.url("/v1/stream").toString().replace("http://", "ws://"), onFinished = { finished.countDown() })
            session.offer(frame(0))
            session.offer(frame(1).apply { addProperty("oversize", "x".repeat(100000)) })
            session.start(); assertTrue(finished.await(5, TimeUnit.SECONDS))
            val d = session.diagnostics()
            assertEquals(2, d["aborted_queued_frames"].asInt)
            assertEquals(0, d["uncertain_in_flight_frames"].asInt)
            assertEquals(0, d["acknowledged_frames"].asInt)
        } finally { server.shutdown() }
    }

    @Test fun matchingRequestIdWithMalformedResultIsNotAnAcknowledgment() {
        val server = MockWebServer(); val finished = CountDownLatch(1)
        server.enqueue(MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { ws.send(ready) }
            override fun onMessage(ws: WebSocket, text: String) {
                val request = JsonParser.parseString(text).asJsonObject
                ws.send("""{"type":"result","request_id":${request["request_id"]},"events":null,"state":{}}""")
            }
            override fun onClosing(ws: WebSocket, code: Int, reason: String) { ws.close(code, reason) }
        }))
        server.start()
        try {
            val session = StreamSession(server.url("/v1/stream").toString().replace("http://", "ws://"), onFinished = { finished.countDown() })
            session.offer(frame(0)); session.start(); assertTrue(finished.await(5, TimeUnit.SECONDS))
            val d = session.diagnostics()
            assertTrue(d["failure"].asString.contains("Malformed"))
            assertEquals(1, d["uncertain_in_flight_frames"].asInt)
            assertEquals(0, d["acknowledged_frames"].asInt)
        } finally { server.shutdown() }
    }

    @Test fun serverErrorAccountsRejectedBatchAndAbortsRemainingQueue() {
        val server = MockWebServer(); val finished = CountDownLatch(1)
        server.enqueue(MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { ws.send(ready) }
            override fun onMessage(ws: WebSocket, text: String) {
                val request = JsonParser.parseString(text).asJsonObject
                ws.send("""{"type":"error","request_id":${request["request_id"]},"error":{"code":"invalid_frames"}}""")
            }
            override fun onClosing(ws: WebSocket, code: Int, reason: String) { ws.close(code, reason) }
        }))
        server.start()
        try {
            val session = StreamSession(server.url("/v1/stream").toString().replace("http://", "ws://"), onFinished = { finished.countDown() })
            repeat(3) { session.offer(frame(it)) }; session.start()
            assertTrue(finished.await(5, TimeUnit.SECONDS))
            val d = session.diagnostics()
            assertEquals(2, d["server_rejected_frames"].asInt)
            assertEquals(1, d["aborted_queued_frames"].asInt)
            assertEquals(0, d["uncertain_in_flight_frames"].asInt)
            assertFalse(d["flush_acknowledged"].asBoolean)
        } finally { server.shutdown() }
    }

    @Test fun stopDrainsInFlightAndQueueBeforeFlushAck() {
        val server = MockWebServer()
        val messages = Collections.synchronizedList(mutableListOf<String>())
        val gotFrame = CountDownLatch(1); val release = CountDownLatch(1); val finished = CountDownLatch(1)
        server.enqueue(MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { ws.send(ready) }
            override fun onMessage(ws: WebSocket, text: String) {
                val message = JsonParser.parseString(text).asJsonObject
                val type = message["type"].asString; messages.add(type)
                if (type == "frames") { gotFrame.countDown(); release.await(3, TimeUnit.SECONDS) }
                ws.send(result(message))
            }
            override fun onClosing(ws: WebSocket, code: Int, reason: String) { ws.close(code, reason) }
        }))
        server.start()
        try {
            val session = StreamSession(server.url("/v1/stream").toString().replace("http://", "ws://"), onFinished = { finished.countDown() })
            session.offer(frame(0)); session.offer(frame(1)); session.offer(frame(2)); session.start()
            assertTrue(gotFrame.await(3, TimeUnit.SECONDS)); session.requestStop()
            assertFalse(finished.await(100, TimeUnit.MILLISECONDS))
            release.countDown(); assertTrue(finished.await(5, TimeUnit.SECONDS))
            assertEquals(listOf("frames", "frames", "flush"), messages)
            val d = session.diagnostics()
            assertTrue(d["flush_acknowledged"].asBoolean); assertEquals(3, d["acknowledged_frames"].asInt)
            assertEquals(0, d["in_flight"].asInt); assertEquals(0, d["queued"].asInt)
        } finally { release.countDown(); server.shutdown() }
    }

    @Test fun disconnectedInFlightIsExplicitlyUncertainAndDoesNotRetry() {
        val server = MockWebServer(); val finished = CountDownLatch(1)
        server.enqueue(MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { ws.send(ready) }
            override fun onMessage(ws: WebSocket, text: String) { ws.close(1011, "injected failure") }
        }))
        server.start()
        try {
            val session = StreamSession(server.url("/v1/stream").toString().replace("http://", "ws://"), timeoutSeconds = 2, onFinished = { finished.countDown() })
            session.offer(frame(0)); session.start()
            assertTrue(finished.await(5, TimeUnit.SECONDS))
            val d = session.diagnostics()
            assertFalse(d["flush_acknowledged"].asBoolean)
            assertEquals(1, d["uncertain_in_flight_frames"].asInt)
            assertEquals(0, d["acknowledged_frames"].asInt)
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }

    @Test fun wrongRequestIdTerminatesSession() {
        val server = MockWebServer(); val finished = CountDownLatch(1)
        server.enqueue(MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { ws.send(ready) }
            override fun onMessage(ws: WebSocket, text: String) { ws.send("""{"type":"result","request_id":"wrong","events":[]}""") }
            override fun onClosing(ws: WebSocket, code: Int, reason: String) { ws.close(code, reason) }
        }))
        server.start()
        try {
            val session = StreamSession(server.url("/v1/stream").toString().replace("http://", "ws://"), timeoutSeconds = 2, onFinished = { finished.countDown() })
            session.offer(frame(0)); session.start(); assertTrue(finished.await(5, TimeUnit.SECONDS))
            assertTrue(session.diagnostics()["failure"].asString.contains("Unmatched"))
        } finally { server.shutdown() }
    }
}
