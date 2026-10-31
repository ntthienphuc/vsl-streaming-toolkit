import 'dart:async';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_demo/session_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('vsl_streaming/bridge');
  late SessionController c;
  final calls = <MethodCall>[];
  setUp(() {
    calls.clear();
    c = SessionController();
    c.previewReady = true;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return {
            'active': false,
            'previewReady': true,
            'hasReceipt': true,
            'hasFrames': true,
          };
        });
  });
  tearDown(() {
    c.dispose();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  Map<String, dynamic> prediction(double score) => {
    'type': 'result',
    'data': {
      'events': [
        {
          'status': 'predicted',
          'prediction': {
            'label': 'xin chào',
            'confidence': score,
            'top_k': [
              {'label': 'xin chào', 'confidence': score},
            ],
          },
        },
      ],
    },
  };
  test('mode change clears previous run status while preserving evidence', () {
    c.phase = 'completed';
    c.message = 'Completed: flush acknowledged; socket close requested.';
    c.hasReceipt = c.hasFrames = true;
    final receipt = {
      'transport': {'terminal': true, 'flush_acknowledged': true},
    };
    final completedPc = {
      'run_id': 'completed-pc',
      'artifacts': [
        {'name': 'frames.jsonl'},
      ],
    };
    c.diagnostics = receipt;
    c.videoReport = completedPc;
    c.handleEvent(prediction(0.2));

    c.setMode(InputMode.video);
    expect(c.phase, 'idle');
    expect(c.message, contains('Record or select one video'));
    expect(c.message, isNot(contains('flush acknowledged')));
    expect(c.latestEvent, isNull);
    expect(c.hasReceipt, isTrue);
    expect(c.hasFrames, isTrue);
    expect(c.diagnostics, same(receipt));
    expect(c.videoReport, same(completedPc));

    c.phase = 'error';
    c.message = 'Video service HTTP 422';
    c.videoFailureReport = {'run_id': 'failed-pc'};
    c.setMode(InputMode.video);
    expect(
      c.phase,
      'error',
      reason: 'Tapping the selected mode must retain its current status.',
    );
    c.setMode(InputMode.canonical);
    expect(c.phase, 'idle');
    expect(c.message, contains('Choose a canonical JSONL trace'));
    expect(c.videoFailureReport?['run_id'], 'failed-pc');
    expect(c.diagnostics, same(receipt));
    expect(c.videoReport, same(completedPc));
  });
  test(
    'native terminal alone cannot enable export before source finalization',
    () async {
      c.active = true;
      c.phase = 'stopping';
      c.handleEvent({
        'type': 'diagnostics',
        'finalized': false,
        'data': {
          'transport': {'terminal': true},
        },
      });
      expect(c.active, isTrue);
      expect(c.hasReceipt, isFalse);
      expect(c.canExportReceipt, isFalse);
      expect(calls, isEmpty);
      c.handleEvent({
        'type': 'diagnostics',
        'finalized': true,
        'data': {
          'transport': {'terminal': true},
        },
      });
      await Future<void>.delayed(Duration.zero);
      expect(calls.single.method, 'snapshot');
      expect(c.active, isFalse);
      expect(c.canExportReceipt, isTrue);
      expect(c.canExportFrames, isTrue);
    },
  );
  test(
    'retains a low model score, clears stale label on empty and rejected responses',
    () {
      c.handleEvent(prediction(0.2));
      expect(c.prediction['confidence'], 0.2);
      expect(c.prediction['label'], 'xin chào');
      c.handleEvent({
        'type': 'result',
        'data': {'events': []},
      });
      expect(c.prediction, isEmpty);
      expect(c.latestEvent, isNull);
      expect(c.eventMessage, contains('No segment'));
      c.handleEvent(prediction(0.2));
      c.handleEvent({
        'type': 'result',
        'data': {
          'events': [
            {
              'status': 'rejected',
              'error': {'code': 'inference_failed', 'message': 'fixture'},
            },
          ],
        },
      });
      expect(c.prediction, isEmpty);
      expect(c.latestEvent?['status'], 'rejected');
      expect(c.rejectedCount, 1);
      expect(c.predictedCount, 2);
    },
  );
  test(
    'only one start while native call is pending; stop remains available during active capture',
    () async {
      final pending = Completer<dynamic>();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            calls.add(call);
            if (call.method == 'startLive') return pending.future;
            return {
              'active': false,
              'phase': 'completed',
              'hasReceipt': true,
              'hasFrames': true,
            };
          });
      final start = c.start();
      await Future<void>.delayed(Duration.zero);
      expect(c.busy, isTrue);
      expect(c.canStart, isFalse);
      c.setMode(InputMode.video);
      expect(c.mode, InputMode.live);
      await c.start();
      expect(calls.where((call) => call.method == 'startLive').length, 1);
      pending.complete({'active': true, 'phase': 'capturing'});
      await start;
      expect(c.canStop, isTrue);
      await c.stop();
      expect(c.active, isFalse);
      expect(c.canExportReceipt, isTrue);
      expect(c.canExportFrames, isTrue);
    },
  );
  test(
    'exports block another export and session until asynchronous completion',
    () async {
      c.hasReceipt = c.hasFrames = true;
      await c.exportReceipt();
      expect(c.exporting, isTrue);
      expect(c.canStart, isFalse);
      expect(c.canExportFrames, isFalse);
      await c.exportFrames();
      expect(calls.map((call) => call.method), ['exportReceipt']);
      c.handleEvent({'type': 'export', 'kind': 'receipt', 'status': 'writing'});
      expect(c.canStart, isFalse);
      c.handleEvent({
        'type': 'export',
        'kind': 'receipt',
        'status': 'completed',
      });
      expect(c.canStart, isTrue);
      expect(c.canExportFrames, isTrue);
    },
  );
  test(
    'canonical requires selection, validates endpoint, and preserves errors',
    () async {
      c.setMode(InputMode.canonical);
      expect(c.canStart, isFalse);
      c.handleEvent({'type': 'selection', 'name': 'trace.jsonl'});
      expect(c.canStart, isTrue);
      c.endpoint = 'not an endpoint';
      await c.start();
      expect(c.phase, 'error');
      expect(c.message, contains('valid ws/wss'));
      expect(calls, isEmpty);
    },
  );
}
