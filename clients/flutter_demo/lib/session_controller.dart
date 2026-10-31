import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

enum InputMode { live, canonical, video }

Map<String, dynamic> jsonMap(dynamic v) =>
    v is Map ? v.map((k, v) => MapEntry(k.toString(), v)) : {};

/// Native code owns capture and transport; Flutter presents their actual output.
class SessionController extends ChangeNotifier {
  SessionController({
    MethodChannel? methods,
    EventChannel? events,
    http.Client? httpClient,
    ImagePicker? imagePicker,
  }) : _methods = methods ?? const MethodChannel('vsl_streaming/bridge'),
       _events = events ?? const EventChannel('vsl_streaming/events'),
       _http = httpClient ?? http.Client(),
       _picker = imagePicker ?? ImagePicker();
  final MethodChannel _methods;
  final EventChannel _events;
  final http.Client _http;
  final ImagePicker _picker;
  StreamSubscription<dynamic>? _subscription;
  bool _disposed = false, _initialized = false;
  InputMode mode = InputMode.live;
  String endpoint = 'ws://127.0.0.1:18081/v1/stream';
  String pcEndpoint = 'http://127.0.0.1:18082';
  int targetFps = 15, rotation = 0;
  bool inputMirrored = false;
  String timestampMode = 'pos-msec';
  String phase = 'idle',
      message = 'Choose an input, inspect the server, then begin.';
  bool busy = false, active = false, stopping = false, exporting = false;
  bool previewReady = false, hasReceipt = false, hasFrames = false;
  bool selecting = false;
  String? replayName;
  XFile? video;
  Map<String, dynamic> videoInfo = {};
  bool videoRecorded = false;
  int get videoUploadLimit {
    final limit = jsonMap(config['capabilities'])['max_upload_bytes'];
    return limit is num && limit > 0 ? limit.toInt() : 100 * 1024 * 1024;
  }

  Map<String, dynamic> config = {}, ready = {}, diagnostics = {};
  Map<String, dynamic>? latestEvent, videoReport, videoFailureReport;
  String eventMessage = 'No result yet. Model output will appear here.';
  int responseCount = 0, predictedCount = 0, rejectedCount = 0;
  String exportMessage =
      'After a session, save both the receipt and its frames.';
  bool get locked =>
      active ||
      busy ||
      exporting ||
      selecting ||
      phase == 'awaiting_permission';
  bool get canStart =>
      !locked &&
      ((mode == InputMode.live && previewReady) ||
          (mode == InputMode.canonical && replayName != null) ||
          (mode == InputMode.video &&
              video != null &&
              !(videoInfo['bytes'] is num &&
                  videoInfo['bytes'] > videoUploadLimit)));
  bool get canStop => active && !stopping;
  bool get canExportReceipt => !locked && hasReceipt;
  bool get canExportFrames => !locked && hasFrames;
  Map<String, dynamic> get transport => jsonMap(diagnostics['transport']);
  Map<String, dynamic> get prediction => jsonMap(latestEvent?['prediction']);
  void changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    _subscription = _events.receiveBroadcastStream().listen(
      handleEvent,
      onError: (Object error) {
        message = 'Native events: $error';
        changed();
      },
    );
    await refreshSnapshot();
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      try {
        final recovered = await _picker.retrieveLostData();
        if (recovered.files?.isNotEmpty == true) {
          await selectVideo(recovered.files!.first);
        }
      } catch (error) {
        message = 'Could not restore video picker: $error';
        changed();
      }
    }
  }

  void setMode(InputMode value) {
    if (locked || value == mode) return;
    mode = value;
    phase = 'idle';
    message = switch (value) {
      InputMode.live =>
        'Frame your face and both hands, inspect the stream server, then start a new session.',
      InputMode.canonical =>
        replayName == null
            ? 'Choose a canonical JSONL trace, inspect the stream server, then start replay.'
            : 'Selected $replayName. Inspect the stream server, then start a new replay.',
      InputMode.video =>
        video == null
            ? 'Record or select one video, then review the PC extraction settings before upload.'
            : 'Selected ${video!.name}. Review the PC extraction settings before upload.',
    };
    latestEvent = null;
    eventMessage = 'No result for this input yet.';
    changed();
  }

  void _snapshot(Map<String, dynamic> value) {
    phase = value['phase']?.toString() ?? phase;
    message = value['message']?.toString() ?? message;
    active = value['active'] == true;
    previewReady = value['previewReady'] == true;
    replayName = value['replayName']?.toString() ?? replayName;
    exporting = value['exporting'] == true;
    selecting = value['selecting'] == true;
    hasReceipt = value['hasReceipt'] == true;
    hasFrames = value['hasFrames'] == true;
    if (value['diagnostics'] is Map) {
      diagnostics = jsonMap(value['diagnostics']);
    }
    if (!active) stopping = false;
    changed();
  }

  @visibleForTesting
  void handleEvent(dynamic raw) {
    final e = jsonMap(raw);
    switch (e['type']) {
      case 'status':
        phase = e['phase']?.toString() ?? phase;
        message = e['message']?.toString() ?? message;
        if (e.containsKey('active')) active = e['active'] == true;
        if (!active) stopping = false;
      case 'config':
        config = jsonMap(e['data']);
      case 'ready':
        ready = jsonMap(e['data']);
      case 'result':
        _acceptResponse(jsonMap(e['data']));
      case 'diagnostics':
        diagnostics = jsonMap(e['data']);
        if (e['finalized'] == true) {
          hasReceipt = true;
          unawaited(refreshSnapshot());
        }
      case 'selection':
        replayName = e['name']?.toString();
        selecting = e['selecting'] == true;
      case 'export':
        final status = e['status']?.toString() ?? 'unknown';
        exporting = status == 'choosing' || status == 'writing';
        exportMessage =
            '${e['kind'] ?? 'Export'} · $status${e['message'] == null ? '' : '\n${e['message']}'}';
      case 'cameraPreviewReady':
        previewReady = e['ready'] == true;
    }
    changed();
  }

  Future<void> refreshSnapshot() async {
    try {
      _snapshot(jsonMap(await _methods.invokeMethod<dynamic>('snapshot')));
    } catch (error) {
      message = 'Android bridge unavailable: $error';
      changed();
    }
  }

  void _acceptResponse(Map<String, dynamic> response) {
    responseCount++;
    final events = response['events'];
    latestEvent =
        null; // Empty and rejected responses must never retain a stale label.
    if (events is! List || events.isEmpty) {
      eventMessage = 'No segment emitted in the latest response.';
      return;
    }
    for (final raw in events) {
      final e = jsonMap(raw);
      if (e['status'] == 'predicted') predictedCount++;
      if (e['status'] == 'rejected') rejectedCount++;
    }
    latestEvent = jsonMap(events.last);
    eventMessage = latestEvent!['status'] == 'predicted'
        ? 'Latest model output · not a verified translation'
        : 'Segment ${latestEvent!['status'] ?? 'without prediction'}';
  }

  void _clearResults() {
    latestEvent = null;
    responseCount = predictedCount = rejectedCount = 0;
    eventMessage = 'Waiting for a server response…';
  }

  Future<void> _action(Future<void> Function() action) async {
    if (locked) return;
    busy = true;
    changed();
    try {
      await action();
    } catch (error) {
      phase = 'error';
      message = error.toString();
    } finally {
      busy = false;
      changed();
    }
  }

  void _validate(String value, List<String> schemes) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null || !schemes.contains(uri.scheme) || uri.host.isEmpty) {
      throw FormatException('Enter a valid ${schemes.join('/')} endpoint.');
    }
  }

  Future<void> inspect() => _action(() async {
    if (mode == InputMode.video) {
      _validate(pcEndpoint, ['http', 'https']);
      final r = await _http
          .get(_pcUri('/health'))
          .timeout(const Duration(seconds: 20));
      if (r.statusCode != 200) {
        throw StateError('PC health HTTP ${r.statusCode}: ${r.body}');
      }
      config = jsonMap(jsonDecode(r.body));
      message = 'PC service responded. Review its configuration in Evidence.';
    } else {
      _validate(endpoint, ['ws', 'wss']);
      config = jsonMap(
        await _methods.invokeMethod<dynamic>('inspect', {
          'endpoint': endpoint.trim(),
        }),
      );
      message = 'Server configuration loaded. Review it in Evidence.';
    }
  });
  Future<void> selectReplay() => _action(() async {
    await _methods.invokeMethod<void>('selectReplay');
  });
  Future<void> pickVideo(ImageSource source) => _action(() async {
    final selected = await _picker.pickVideo(
      source: source,
      maxDuration: const Duration(minutes: 2),
    );
    if (selected != null) {
      await selectVideo(selected, recorded: source == ImageSource.camera);
    }
  });
  @visibleForTesting
  Future<void> selectVideo(XFile selected, {bool recorded = false}) async {
    video = selected;
    videoRecorded = recorded;
    videoInfo = {'bytes': await selected.length()};
    rotation = 0;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      try {
        final info = jsonMap(
          await _methods.invokeMethod<dynamic>('inspectVideo', {
            'path': selected.path,
          }),
        );
        final sourceRotation = info['rotation'];
        if (sourceRotation is! int ||
            ![0, 90, 180, 270].contains(sourceRotation)) {
          throw const FormatException('Unsupported video rotation.');
        }
        videoInfo.addAll(info);
        rotation = sourceRotation;
      } catch (error) {
        videoInfo['metadata_error'] = error.toString();
      }
    }
    _clearResults();
    phase = 'idle';
    message = videoInfo.containsKey('metadata_error')
        ? 'Video selected. Check rotation in Input settings; metadata unavailable.'
        : 'Video ready. Review Input settings if needed.';
    if (videoInfo['bytes'] > videoUploadLimit) {
      phase = 'error';
      message = _videoLimitMessage;
    }
    changed();
  }

  String get _videoLimitMessage =>
      'Video exceeds PC limit (${(videoUploadLimit / (1024 * 1024)).toStringAsFixed(0)} MiB). Record a shorter clip.';
  Future<void> start() async {
    if (!canStart) return;
    await _action(() async {
      _clearResults();
      if (mode == InputMode.video) {
        await _uploadVideo();
        return;
      }
      _validate(endpoint, ['ws', 'wss']);
      diagnostics = {};
      ready = {};
      hasReceipt = hasFrames = false;
      _snapshot(
        jsonMap(
          await _methods.invokeMethod<dynamic>(
            mode == InputMode.live ? 'startLive' : 'startReplay',
            {
              'endpoint': endpoint.trim(),
              if (mode == InputMode.live) 'targetFps': targetFps,
            },
          ),
        ),
      );
    });
  }

  Future<void> stop() async {
    if (!canStop) return;
    stopping = true;
    message = 'Stopping capture, draining the queue, and awaiting flush…';
    changed();
    try {
      _snapshot(jsonMap(await _methods.invokeMethod<dynamic>('stop')));
    } catch (error) {
      stopping = false;
      message = 'Stop failed: $error';
      changed();
    }
  }

  Future<void> exportReceipt() => _export('exportReceipt', canExportReceipt);
  Future<void> exportFrames() => _export('exportFrames', canExportFrames);
  Future<void> _export(String method, bool available) async {
    if (!available) return;
    exporting = true;
    changed();
    try {
      await _methods.invokeMethod<void>(method);
    } catch (error) {
      exporting = false;
      exportMessage = 'Export failed: $error';
      changed();
    }
  }

  Uri _pcUri(String path) =>
      Uri.parse('${pcEndpoint.trim().replaceFirst(RegExp(r'/+$'), '')}$path');
  Future<void> _uploadVideo() async {
    _validate(pcEndpoint, ['http', 'https']);
    if (await video!.length() > videoUploadLimit) {
      throw StateError(_videoLimitMessage);
    }
    phase = 'uploading';
    message =
        'Uploading one video, then extracting on the PC. Keep the app open; this can take several minutes.';
    changed();
    final request = http.MultipartRequest('POST', _pcUri('/v1/video'));
    request.fields.addAll({
      'rotate': '$rotation',
      'input_mirrored': '$inputMirrored',
      'target_fps': '$targetFps',
      'timestamp_mode': timestampMode,
    });
    request.files.add(
      await http.MultipartFile.fromPath(
        'video',
        video!.path,
        filename: video!.name.replaceAll('\\', '/').split('/').last,
      ),
    );
    final response = await (() async {
      final streamed = await _http.send(request);
      return http.Response.fromStream(streamed);
    })().timeout(const Duration(minutes: 20));
    if (response.statusCode != 200) {
      try {
        final failure = jsonMap(jsonDecode(response.body));
        if (failure['artifacts'] is List) videoFailureReport = failure;
      } on FormatException {
        // A proxy may return plain text; the HTTP error preserves that body.
      }
      throw StateError(
        'Video service HTTP ${response.statusCode}: ${response.body}',
      );
    }
    final report = jsonMap(jsonDecode(response.body));
    if (report['status'] != 'completed') {
      throw StateError(
        'Video service did not report completion: ${response.body}',
      );
    }
    videoReport = report;
    videoFailureReport = null;
    _acceptResponse({'events': report['events'] ?? []});
    phase = 'complete';
    message =
        'PC processing complete · replay ${report['replay_status'] ?? 'unspecified'}. Artifact links are in Evidence.';
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(_subscription?.cancel());
    _http.close();
    super.dispose();
  }
}
