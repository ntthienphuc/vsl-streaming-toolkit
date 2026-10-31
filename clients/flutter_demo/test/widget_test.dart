import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_demo/main.dart';
import 'package:flutter_demo/session_controller.dart';
import 'package:image_picker/image_picker.dart';

void main() {
  testWidgets(
    'recorded clip stays compact and metadata rotation updates settings',
    (tester) async {
      final c = SessionController();
      addTearDown(c.dispose);
      c.mode = InputMode.video;
      await tester.pumpWidget(
        VslApp(controller: c, initialize: false, enableCameraView: false),
      );
      await tester.tap(find.text('Settings'));
      await tester.pumpAndSettle();
      c.video = XFile('/cache/very-long-original-camera-identifier.mp4');
      c.videoRecorded = true;
      c.rotation = 270;
      c.videoInfo = {
        'width': 2224,
        'height': 1080,
        'rotation': 270,
        'duration_ms': 3000,
        'bytes': 3 * 1024 * 1024,
      };
      c.changed();
      await tester.pumpAndSettle();
      expect(find.text('270° clockwise'), findsOneWidget);
      await tester.tap(find.text('Session'));
      await tester.pumpAndSettle();
      expect(find.text('Recorded video'), findsOneWidget);
      expect(find.text('3.0 MiB'), findsOneWidget);
      await tester.tap(find.text('Input settings').first);
      await tester.pumpAndSettle();
      expect(find.textContaining('source rotation 270°'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'evidence binds native exports to native identity and reports receipt truncation',
    (tester) async {
      final c = SessionController();
      addTearDown(c.dispose);
      c.mode = InputMode.video;
      c.hasReceipt = c.hasFrames = true;
      c.diagnostics = {
        'server_ready': {'session_id': 'native-session-A'},
        'extractor_profile': 'android-tasks-profile',
        'responses': List.generate(500, (_) => <String, dynamic>{}),
        'response_log_omitted': 12,
        'transport': {
          'enqueued': 1000,
          'acknowledged_frames': 1000,
          'dropped_queue_full': 0,
        },
      };
      c.videoReport = {
        'run_id': 'pc-run-B',
        'extractor_profile': 'pc-profile',
        'replay_status': 'passed',
        'emitted_frames': 7,
        'artifacts': [],
      };
      await tester.pumpWidget(
        VslApp(controller: c, initialize: false, enableCameraView: false),
      );
      await tester.tap(find.text('Evidence'));
      await tester.pumpAndSettle();
      expect(find.text('Native artifacts'), findsOneWidget);
      await tester.tap(find.text('Native session'));
      await tester.pumpAndSettle();
      final identity = tester.widget<SelectableText>(
        find.byKey(const ValueKey('native-artifact-identity')),
      );
      expect(identity.data, contains('native-session-A'));
      expect(identity.data, contains('android-tasks-profile'));
      expect(identity.data, isNot(contains('pc-run-B')));
      final history = tester.widget<Text>(
        find.byKey(const ValueKey('receipt-history-truncation')),
      );
      expect(history.data, contains('500 retained · 12 omitted'));
      expect(history.data, contains('not transport loss'));
      await tester.scrollUntilVisible(
        find.text('PC artifacts · latest run'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('PC artifacts · latest run'), findsOneWidget);
    },
  );
  testWidgets(
    'startup selects video and replay remains reachable from Evidence',
    (tester) async {
      await tester.pumpWidget(
        const VslApp(initialize: false, enableCameraView: false),
      );
      expect(
        tester
            .widget<ChoiceChip>(find.byKey(const ValueKey('mode-video')))
            .selected,
        isTrue,
      );
      expect(find.byKey(const ValueKey('record-video')), findsOneWidget);
      expect(find.byKey(const ValueKey('choose-video')), findsOneWidget);
      expect(find.byKey(const ValueKey('camera-portrait')), findsNothing);
      await tester.tap(find.text('Evidence'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('replay-trace')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('choose-replay')), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('start-session')))
            .onPressed,
        isNull,
      );
    },
  );

  testWidgets(
    'live preview is portrait three by four and actions fit phone screen',
    (tester) async {
      tester.view.physicalSize = const Size(720, 1480);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final c = SessionController()..previewReady = true;
      addTearDown(c.dispose);
      await tester.pumpWidget(
        VslApp(controller: c, initialize: false, enableCameraView: false),
      );
      final preview = tester.getSize(
        find.byKey(const ValueKey('camera-portrait')),
      );
      expect(preview.width / preview.height, closeTo(3 / 4, 0.001));
      expect(preview.height, greaterThan(preview.width));
      expect(
        find.byKey(const ValueKey('start-session')).hitTestable(),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('stop-session')).hitTestable(),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'low score is rendered without filtering and empty response clears it',
    (tester) async {
      final c = SessionController();
      addTearDown(c.dispose);
      c.handleEvent({
        'type': 'result',
        'data': {
          'events': [
            {
              'status': 'predicted',
              'prediction': {
                'label': 'xin chào',
                'confidence': 0.2,
                'top_k': [],
              },
            },
          ],
        },
      });
      await tester.pumpWidget(
        VslApp(controller: c, initialize: false, enableCameraView: false),
      );
      await tester.scrollUntilVisible(
        find.text('Model score 0.2000'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('xin chào'), findsOneWidget);
      expect(find.text('Model score 0.2000'), findsOneWidget);
      c.handleEvent({
        'type': 'result',
        'data': {'events': []},
      });
      await tester.pump();
      expect(find.text('xin chào'), findsNothing);
      expect(
        find.text('No segment emitted in the latest response.'),
        findsOneWidget,
      );
    },
  );
  testWidgets(
    'busy disables Start and export; active capture keeps Stop visible on Evidence',
    (tester) async {
      final c = SessionController();
      addTearDown(c.dispose);
      await tester.pumpWidget(
        VslApp(controller: c, initialize: false, enableCameraView: false),
      );
      c.busy = true;
      c.changed();
      await tester.pump();
      expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('start-session')))
            .onPressed,
        isNull,
      );
      c.busy = false;
      c.active = true;
      c.changed();
      await tester.pump();
      await tester.tap(find.text('Evidence'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<OutlinedButton>(find.byKey(const ValueKey('stop-session')))
            .onPressed,
        isNotNull,
      );
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('export-receipt')),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(
        tester
            .widget<OutlinedButton>(
              find.byKey(const ValueKey('export-receipt')),
            )
            .onPressed,
        isNull,
      );
    },
  );
  testWidgets('all tabs and input cards fit 360 pixels with large text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.6;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final c = SessionController();
    addTearDown(c.dispose);
    await tester.pumpWidget(
      VslApp(controller: c, initialize: false, enableCameraView: false),
    );
    for (final mode in InputMode.values) {
      c.setMode(mode);
      await tester.pump();
      expect(tester.takeException(), isNull, reason: '$mode input should fit');
    }
    for (final name in ['Evidence', 'Settings', 'Session']) {
      await tester.tap(find.text(name));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: '$name tab should fit');
    }
  });
}
