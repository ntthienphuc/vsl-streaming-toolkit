import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:flutter_demo/session_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'multipart preserves explicit extraction settings and no-segment result',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'vsl-upload-test-',
      );
      final file = File('${directory.path}/input.mp4');
      await file.writeAsBytes([1, 2, 3]);
      addTearDown(() async {
        await file.delete();
        await directory.delete();
      });
      var requestCount = 0;
      final client = MockClient((request) async {
        requestCount++;
        expect(request.url.path, '/v1/video');
        expect(request.method, 'POST');
        expect(
          request.headers['content-type'],
          startsWith('multipart/form-data;'),
        );
        for (final field in {
          'rotate': '90',
          'input_mirrored': 'true',
          'target_fps': '12',
          'timestamp_mode': 'frame-index',
        }.entries) {
          expect(
            request.body,
            contains('name="${field.key}"\r\n\r\n${field.value}'),
          );
        }
        expect(request.body, contains('name="video"; filename="input.mp4"'));
        return http.Response(
          jsonEncode({
            'status': 'completed',
            'run_id': 'unit-fixture',
            'extractor_profile': 'fixture',
            'decoded_frames': 5,
            'emitted_frames': 3,
            'events': [],
            'replay_status': 'no_segments',
            'artifacts': [
              {
                'name': 'trace.jsonl',
                'url': '/artifacts/unit-fixture/trace.jsonl',
                'sha256': 'fixture',
                'bytes': 3,
              },
            ],
          }),
          200,
        );
      });
      final c = SessionController(httpClient: client);
      addTearDown(c.dispose);
      c.mode = InputMode.video;
      c.video = XFile(file.path);
      c.rotation = 90;
      c.inputMirrored = true;
      c.targetFps = 12;
      c.timestampMode = 'frame-index';
      await c.start();
      expect(requestCount, 1);
      expect(c.phase, 'complete', reason: c.message);
      expect(c.videoReport?['replay_status'], 'no_segments');
      expect(c.latestEvent, isNull);
      expect(c.prediction, isEmpty);
      expect(c.canStart, isTrue);
    },
  );
  test(
    'server failure keeps last completed artifacts and exposes failure',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'vsl-failed-upload-test-',
      );
      final file = File('${directory.path}/input.mp4');
      await file.writeAsBytes([1]);
      addTearDown(() async {
        await file.delete();
        await directory.delete();
      });
      final c = SessionController(
        httpClient: MockClient(
          (_) async => http.Response(
            '{"status":"failed","run_id":"failed-run","replay_status":"failed","artifacts":[{"name":"failure.json","url":"/artifacts/failed-run/failure.json","sha256":"fixture","bytes":2}]}',
            422,
          ),
        ),
      );
      addTearDown(c.dispose);
      c.mode = InputMode.video;
      c.video = XFile(file.path);
      c.videoReport = {
        'run_id': 'previous-completed',
        'artifacts': [
          {'name': 'old-trace.jsonl'},
        ],
      };
      await c.start();
      expect(c.phase, 'error');
      expect(c.message, contains('HTTP 422'));
      expect(c.videoReport?['run_id'], 'previous-completed');
      expect(c.videoFailureReport?['run_id'], 'failed-run');
      expect(
        (c.videoFailureReport?['artifacts'] as List).first['name'],
        'failure.json',
      );
      expect(c.prediction, isEmpty);
      expect(c.busy, isFalse);
    },
  );
}
