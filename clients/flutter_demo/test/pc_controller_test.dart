import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:flutter_demo/session_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory temporary;
  late File clip;
  setUp(() async {
    temporary = await Directory.systemTemp.createTemp('vsl-http-contract-');
    clip = File('${temporary.path}/portrait.mp4');
    await clip.writeAsBytes([0, 1, 2, 3, 4]);
  });
  tearDown(() => temporary.delete(recursive: true));

  test(
    'portrait metadata selects explicit rotation and resets stale results',
    () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      const channel = MethodChannel('vsl-test-video-metadata');
      var fail = false;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            expect(call.method, 'inspectVideo');
            expect(call.arguments['path'], clip.path);
            if (fail) throw PlatformException(code: 'video_inspect_failed');
            return {
              'width': 2224,
              'height': 1080,
              'rotation': 270,
              'duration_ms': 54600,
              'bytes': 5,
            };
          });
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, null),
      );
      final c = SessionController(methods: channel);
      addTearDown(c.dispose);
      c.mode = InputMode.video;
      c.phase = 'complete';
      c.latestEvent = {
        'prediction': {'label': 'old'},
      };
      await c.selectVideo(XFile(clip.path), recorded: true);
      expect(c.phase, 'idle');
      expect(c.rotation, 270);
      expect(c.videoRecorded, isTrue);
      expect(c.videoInfo['bytes'], 5);
      expect(c.latestEvent, isNull);
      fail = true;
      await c.selectVideo(XFile(clip.path));
      expect(
        c.rotation,
        0,
        reason: 'An unreadable new clip cannot retain the previous angle',
      );
      expect(c.videoRecorded, isFalse);
      expect(c.videoInfo, contains('metadata_error'));
      expect(c.message, contains('Check rotation'));
    },
  );

  test(
    'known oversized video blocks start using the advertised PC limit',
    () async {
      final c = SessionController();
      addTearDown(c.dispose);
      c.mode = InputMode.video;
      expect(c.videoUploadLimit, 100 * 1024 * 1024);
      c.config = {
        'capabilities': {'max_upload_bytes': 4},
      };
      await c.selectVideo(XFile(clip.path));
      expect(c.videoUploadLimit, 4);
      expect(c.phase, 'error');
      expect(c.canStart, isFalse);
      expect(c.message, contains('Record a shorter clip'));
    },
  );

  test(
    'stat rejects an oversized file before HTTP and preserves evidence',
    () async {
      var requests = 0;
      final c = SessionController(
        httpClient: MockClient((_) async {
          requests++;
          return http.Response('{}', 200);
        }),
      );
      addTearDown(c.dispose);
      c.mode = InputMode.video;
      c.video = XFile(clip.path);
      c.config = {
        'capabilities': {'max_upload_bytes': 4},
      };
      c.videoReport = {'run_id': 'previous'};
      c.diagnostics = {'session_id': 'native-previous'};
      expect(c.canStart, isTrue, reason: 'The file has not been inspected yet');
      await c.start();
      expect(c.phase, 'error');
      expect(requests, 0);
      expect(c.videoReport?['run_id'], 'previous');
      expect(c.diagnostics['session_id'], 'native-previous');
      expect(c.busy, isFalse);
    },
  );

  test(
    'upload preserves file and explicit fields, blocks duplicate starts, and accepts no segments',
    () async {
      final pending = Completer<http.Response>();
      final requests = <http.Request>[];
      final client = MockClient((request) async {
        requests.add(request);
        return pending.future;
      });
      final c = SessionController(httpClient: client);
      addTearDown(c.dispose);
      c.setMode(InputMode.video);
      c.video = XFile(clip.path);
      c.rotation = 90;
      c.inputMirrored = true;
      c.timestampMode = 'frame-index';
      c.targetFps = 12;
      final native = {
        'server_ready': {'session_id': 'previous-native'},
        'transport': {'acknowledged_frames': 3},
      };
      c.diagnostics = native;
      c.hasReceipt = true;
      final first = c.start();
      while (requests.isEmpty) {
        await Future<void>.delayed(Duration.zero);
      }
      expect(c.busy, isTrue);
      expect(c.canStart, isFalse);
      await c.start();
      expect(requests, hasLength(1));
      final request = requests.single;
      expect(request.method, 'POST');
      expect(request.url.path, '/v1/video');
      final multipart = latin1.decode(request.bodyBytes);
      for (final field in {
        'rotate': '90',
        'input_mirrored': 'true',
        'timestamp_mode': 'frame-index',
        'target_fps': '12',
      }.entries) {
        expect(
          multipart,
          contains('name="${field.key}"\r\n\r\n${field.value}'),
        );
      }
      expect(multipart, contains('filename="portrait.mp4"'));
      expect(multipart, contains(String.fromCharCodes([0, 1, 2, 3, 4])));
      pending.complete(
        http.Response(
          jsonEncode({
            'status': 'completed',
            'run_id': 'new-pc',
            'extractor_profile': 'desktop-test',
            'replay_status': 'no_segments',
            'events': [],
            'artifacts': [],
          }),
          200,
        ),
      );
      await first;
      expect(c.phase, 'complete');
      expect(c.busy, isFalse);
      expect(c.latestEvent, isNull);
      expect(c.videoReport?['replay_status'], 'no_segments');
      expect(c.diagnostics, same(native));
      expect(c.canExportReceipt, isTrue);
    },
  );
}
