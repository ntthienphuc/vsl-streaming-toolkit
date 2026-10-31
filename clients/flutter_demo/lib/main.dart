import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'session_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VslApp());
}

const ink = Color(0xFF0B1F33);
const muted = Color(0xFF4A6578);
const blue = Color(0xFF006BFF);

class VslApp extends StatelessWidget {
  const VslApp({
    super.key,
    this.controller,
    this.initialize = true,
    this.enableCameraView = true,
  });
  final SessionController? controller;
  final bool initialize, enableCameraView;

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'VSL Toolkit',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: blue,
        primary: blue,
        surface: Colors.white,
        onSurface: ink,
      ),
      scaffoldBackgroundColor: const Color(0xFFF3F7FA),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFFF3F7FA),
        foregroundColor: ink,
        scrolledUnderElevation: 0,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFFF3F7FA),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
      textTheme: const TextTheme(bodyMedium: TextStyle(height: 1.35)),
    ),
    home: StudioScreen(
      controller: controller,
      initialize: initialize,
      enableCameraView: enableCameraView,
    ),
  );
}

class StudioScreen extends StatefulWidget {
  const StudioScreen({
    super.key,
    this.controller,
    required this.initialize,
    required this.enableCameraView,
  });
  final SessionController? controller;
  final bool initialize, enableCameraView;
  @override
  State<StudioScreen> createState() => _StudioScreenState();
}

class _StudioScreenState extends State<StudioScreen> {
  late final SessionController c;
  late final TextEditingController ws, pc;
  final Map<String, PageStorageBucket> _detailStorage = {};
  int tab = 0;

  @override
  void initState() {
    super.initState();
    c = widget.controller ?? SessionController();
    if (widget.controller == null) c.setMode(InputMode.video);
    ws = TextEditingController(text: c.endpoint);
    pc = TextEditingController(text: c.pcEndpoint);
    if (widget.initialize) unawaited(c.initialize());
  }

  @override
  void dispose() {
    ws.dispose();
    pc.dispose();
    if (widget.controller == null) c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: c,
    builder: (context, _) => Scaffold(
      appBar: AppBar(
        title: const Text(
          'VSL Toolkit',
          style: TextStyle(fontSize: 21, fontWeight: FontWeight.w700),
        ),
        titleSpacing: 16,
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            Expanded(
              child: IndexedStack(
                index: tab,
                children: [_session(), _evidence(), _settings()],
              ),
            ),
            if (c.active || tab == 0) _sessionControls(),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (value) => setState(() => tab = value),
        backgroundColor: Colors.white,
        indicatorColor: const Color(0xFFE4F0FF),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.videocam_outlined),
            label: 'Session',
          ),
          NavigationDestination(
            icon: Icon(Icons.fact_check_outlined),
            label: 'Evidence',
          ),
          NavigationDestination(
            icon: Icon(Icons.tune_rounded),
            label: 'Settings',
          ),
        ],
      ),
    ),
  );

  Widget _space([double height = 12]) => SizedBox(height: height);
  Widget _page(String name, List<Widget> children) => ListView(
    key: PageStorageKey(name),
    padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
    children: children,
  );
  Widget _card(List<Widget> children) => Material(
    color: Colors.white,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(16),
      side: const BorderSide(color: Color(0xFFE2EBF1)),
    ),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
    ),
  );
  Widget _label(String text) => Text(
    text,
    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
  );
  Widget _detail(String title, List<Widget> children, {Key? key}) =>
      ExpansionTile(
        key: key ?? PageStorageKey('detail-$title'),
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 8),
        title: Text(title, style: const TextStyle(fontSize: 14)),
        children: [
          // SelectableText owns a ScrollPosition. Its stored offset must not
          // share the ExpansionTile boolean state in the surrounding page.
          PageStorage(
            bucket: _detailStorage.putIfAbsent(title, PageStorageBucket.new),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children.indexed
                  .map(
                    (item) => KeyedSubtree(
                      key: PageStorageKey('detail-child-${item.$1}'),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: item.$2,
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      );

  Widget _session() => _page('session-page', [
    Wrap(
      spacing: 8,
      runSpacing: 4,
      children: [
        _modeChip(InputMode.video, 'Video → PC', Icons.video_file_outlined),
        _modeChip(InputMode.live, 'Live', Icons.sensors_rounded),
        if (c.mode == InputMode.canonical)
          const Chip(
            label: Text('Replay JSONL'),
            avatar: Icon(Icons.data_object, size: 18),
          ),
      ],
    ),
    _space(8),
    if (c.mode == InputMode.live) ...[
      const Text(
        'Face and both hands in frame',
        textAlign: TextAlign.center,
        style: TextStyle(color: muted),
      ),
      _space(8),
      _camera(),
    ] else if (c.mode == InputMode.canonical)
      _card([
        _label('Replay trace'),
        _space(8),
        Text(
          c.replayName ?? 'Choose a canonical JSONL file.',
          style: const TextStyle(color: muted),
        ),
        _space(8),
        OutlinedButton.icon(
          key: const ValueKey('choose-replay'),
          onPressed: c.locked ? null : c.selectReplay,
          icon: const Icon(Icons.folder_open),
          label: const Text('Choose JSONL'),
        ),
      ])
    else
      _videoCard(),
    _space(),
    _statusCard(),
    if (c.responseCount > 0 || c.latestEvent != null) ...[
      _space(),
      _resultCard(),
    ],
  ]);

  Widget _modeChip(InputMode mode, String label, IconData icon) => ChoiceChip(
    key: ValueKey('mode-${mode.name}'),
    selected: c.mode == mode,
    onSelected: c.locked ? null : (_) => c.setMode(mode),
    label: Text(label),
    avatar: Icon(icon, size: 18),
    showCheckmark: false,
    selectedColor: const Color(0xFFDCEBFF),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
  );

  Widget _camera() => LayoutBuilder(
    builder: (context, constraints) {
      // Preserve the upright source ratio. Native PreviewView uses FIT_CENTER.
      final heightBudget = (MediaQuery.sizeOf(context).height * 0.49).clamp(
        220.0,
        520.0,
      );
      final width = constraints.maxWidth.clamp(0.0, heightBudget * 3 / 4);
      return Center(
        child: SizedBox(
          width: width,
          child: AspectRatio(
            key: const ValueKey('camera-portrait'),
            aspectRatio: 3 / 4,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  const ColoredBox(color: Color(0xFF102D48)),
                  if (widget.enableCameraView &&
                      !kIsWeb &&
                      defaultTargetPlatform == TargetPlatform.android)
                    const AndroidView(
                      key: ValueKey('native-camera'),
                      viewType: 'vsl_streaming/camera',
                    )
                  else
                    const Center(
                      child: Icon(
                        Icons.person_outline,
                        size: 84,
                        color: Color(0xFF64839D),
                      ),
                    ),
                  if (!c.active)
                    const Center(
                      child: Icon(
                        Icons.videocam_outlined,
                        color: Colors.white,
                        size: 40,
                      ),
                    ),
                  Positioned(
                    top: 10,
                    left: 10,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: const Color(0xAA102D48),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        child: Text(
                          c.active ? 'LIVE' : 'Front camera',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 11,
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    },
  );

  Widget _videoCard() => _card([
    _label('Video input'),
    _space(10),
    Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        OutlinedButton.icon(
          key: const ValueKey('record-video'),
          onPressed: c.locked ? null : () => c.pickVideo(ImageSource.camera),
          icon: const Icon(Icons.videocam_outlined),
          label: const Text('Record'),
        ),
        OutlinedButton.icon(
          key: const ValueKey('choose-video'),
          onPressed: c.locked ? null : () => c.pickVideo(ImageSource.gallery),
          icon: const Icon(Icons.folder_open),
          label: const Text('Choose video'),
        ),
      ],
    ),
    _space(8),
    Text(
      c.video == null
          ? 'No video selected'
          : c.videoRecorded
          ? 'Recorded video'
          : c.video!.name,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: const TextStyle(color: muted),
    ),
    if (c.videoInfo['bytes'] is num)
      Text(
        '${(c.videoInfo['bytes'] / (1024 * 1024)).toStringAsFixed(1)} MiB',
        style: const TextStyle(fontSize: 12, color: muted),
      ),
    _detail('Input settings', [
      if (c.video != null)
        SelectableText(
          c.video!.name,
          style: const TextStyle(fontSize: 12, color: muted),
        ),
      if (c.videoInfo['width'] != null)
        Text(
          '${c.videoInfo['width']} × ${c.videoInfo['height']} stored · ${c.videoInfo['duration_ms']} ms · source rotation ${c.videoInfo['rotation']}°',
          style: const TextStyle(fontSize: 12, color: muted),
        ),
      if (c.videoInfo['metadata_error'] != null)
        const Text(
          'Metadata unavailable. Check rotation before upload.',
          style: TextStyle(fontSize: 12, color: muted),
        ),
      Text(
        '${c.rotation}° · ${c.inputMirrored ? 'mirrored' : 'unmirrored'} · ${c.targetFps} FPS target · ${c.timestampMode}',
        style: const TextStyle(fontSize: 12, color: muted),
      ),
      TextButton(
        onPressed: () => setState(() => tab = 2),
        child: const Text('Edit settings'),
      ),
    ]),
  ]);

  Widget _statusCard() => _card([
    Row(
      children: [
        Icon(
          c.phase == 'error' || c.phase == 'failed'
              ? Icons.error_outline
              : c.active
              ? Icons.radio_button_checked
              : Icons.info_outline,
          color: blue,
          size: 18,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            c.phase == 'idle' ? 'Ready' : c.phase.replaceAll('_', ' '),
            key: const ValueKey('session-status'),
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
      ],
    ),
    if (c.busy || c.stopping || c.exporting || c.selecting) ...[
      _space(8),
      const LinearProgressIndicator(minHeight: 2),
    ],
    if (c.phase == 'error' || c.phase == 'failed') ...[
      _space(8),
      Text(
        c.message,
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontSize: 12, color: muted),
      ),
    ],
    _detail('Details', [
      SelectableText(
        c.message,
        style: const TextStyle(fontSize: 12, color: muted),
      ),
    ]),
  ]);

  Widget _resultCard() {
    final prediction = c.prediction;
    final hasPrediction =
        c.latestEvent?['status'] == 'predicted' && prediction.isNotEmpty;
    final error = jsonMap(c.latestEvent?['error']);
    final top = prediction['top_k'];
    return _card([
      _label('Latest response'),
      _space(8),
      if (hasPrediction) ...[
        Text(
          prediction['label']?.toString() ?? 'Unlabelled output',
          style: const TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w700,
            color: blue,
          ),
        ),
        Text('Model score ${_score(prediction['confidence'])}'),
        if (top is List && top.isNotEmpty)
          _detail(
            'Top candidates',
            top.map((raw) {
              final item = jsonMap(raw);
              return Text('${item['label']} · ${_score(item['confidence'])}');
            }).toList(),
          ),
      ] else
        Text(c.eventMessage, style: const TextStyle(color: muted)),
      if (error.isNotEmpty) ...[
        _space(8),
        Text(
          '${error['code'] ?? 'Error'}: ${error['message'] ?? ''}',
          style: TextStyle(color: Colors.red.shade800),
        ),
      ],
    ]);
  }

  String _score(dynamic value) =>
      value is num ? value.toStringAsFixed(4) : 'unavailable';

  Widget _sessionControls() {
    final start = FilledButton.icon(
      key: const ValueKey('start-session'),
      onPressed: c.canStart ? c.start : null,
      icon: Icon(
        c.mode == InputMode.video ? Icons.upload_outlined : Icons.play_arrow,
      ),
      label: Text(
        c.mode == InputMode.video
            ? 'Upload & process'
            : c.mode == InputMode.canonical
            ? 'Start replay'
            : 'Start',
      ),
    );
    final stop = OutlinedButton.icon(
      key: const ValueKey('stop-session'),
      onPressed: c.canStop ? c.stop : null,
      icon: const Icon(Icons.stop),
      label: Text(c.stopping ? 'Draining…' : 'Stop'),
    );
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      color: const Color(0xFFF3F7FA),
      child: LayoutBuilder(
        builder: (context, size) {
          if (c.mode == InputMode.video && !c.active) {
            return SizedBox(width: double.infinity, child: start);
          }
          if (MediaQuery.textScalerOf(context).scale(14) > 20 ||
              size.maxWidth < 310) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [start, const SizedBox(height: 6), stop],
            );
          }
          return Row(
            children: [
              Expanded(child: start),
              const SizedBox(width: 8),
              Expanded(child: stop),
            ],
          );
        },
      ),
    );
  }

  Widget _evidence() {
    final t = c.transport;
    final nativeReady = jsonMap(c.diagnostics['server_ready']);
    final nativeResponses = c.diagnostics['responses'];
    final retained = nativeResponses is List ? nativeResponses.length : 0;
    final omitted = c.diagnostics['response_log_omitted'];
    return _page('evidence-page', [
      _card([
        _label('Native artifacts'),
        _space(8),
        OutlinedButton.icon(
          key: const ValueKey('export-receipt'),
          onPressed: c.canExportReceipt ? c.exportReceipt : null,
          icon: const Icon(Icons.description_outlined),
          label: const Text('Save receipt'),
        ),
        _space(8),
        OutlinedButton.icon(
          key: const ValueKey('export-frames'),
          onPressed: c.canExportFrames ? c.exportFrames : null,
          icon: const Icon(Icons.data_object),
          label: const Text('Save frames JSONL'),
        ),
        _detail('Native session', [
          SelectableText(
            'Session ${nativeReady['session_id'] ?? 'not recorded'}\nProfile ${c.diagnostics['extractor_profile'] ?? 'not recorded'}',
            key: const ValueKey('native-artifact-identity'),
            style: const TextStyle(fontSize: 12, color: muted),
          ),
        ]),
        if (omitted is num && omitted > 0)
          Text(
            'Receipt history: $retained retained · $omitted omitted.\nHistory is truncated; this is not transport loss.',
            key: const ValueKey('receipt-history-truncation'),
            style: const TextStyle(fontSize: 12, color: muted),
          ),
        if (c.exportMessage !=
            'After a session, save both the receipt and its frames.') ...[
          _space(8),
          Text(
            c.exportMessage,
            style: const TextStyle(fontSize: 12, color: muted),
          ),
        ],
        _space(8),
        OutlinedButton.icon(
          key: const ValueKey('replay-trace'),
          onPressed: c.locked
              ? null
              : () {
                  c.setMode(InputMode.canonical);
                  setState(() => tab = 0);
                },
          icon: const Icon(Icons.replay),
          label: const Text('Replay trace'),
        ),
      ]),
      _space(),
      _card([
        _label('Native transport'),
        _space(8),
        Wrap(
          spacing: 12,
          runSpacing: 6,
          children: [
            _metric('Admitted', t['enqueued']),
            _metric('ACK', t['acknowledged_frames']),
            _metric('Dropped', t['dropped_queue_full']),
            _metric('Uncertain', t['uncertain_in_flight_frames']),
          ],
        ),
        _space(8),
        Text(
          'Flush ${_flag(t['flush_acknowledged'])} · terminal ${_flag(t['terminal'])}',
          style: const TextStyle(color: muted, fontSize: 12),
        ),
        if (t['failure'] != null)
          Text(
            'Transport: ${t['failure']}',
            style: TextStyle(color: Colors.red.shade800),
          ),
        if (c.diagnostics['source_failure'] != null)
          Text('Source: ${c.diagnostics['source_failure']}'),
        _detail('Counters', [
          Text(
            'Queued ${t['queued'] ?? '—'} · in flight ${t['in_flight'] ?? '—'}',
            style: const TextStyle(fontSize: 12),
          ),
        ]),
      ]),
      if (c.videoFailureReport != null) ...[
        _space(),
        _pcReport('PC artifacts · failed run', c.videoFailureReport!),
      ],
      if (c.videoReport != null) ...[
        _space(),
        _pcReport('PC artifacts · latest run', c.videoReport!),
      ],
      _space(),
      _card([
        _detail('Server configuration', [_json(c.config)]),
        _detail('Session configuration', [_json(c.ready)]),
        _detail('Full diagnostics', [_json(c.diagnostics)]),
        _detail('Profile notes', [
          const Text(
            'Android Tasks and PC extraction use distinct profiles. Compare the same recorded input before combining their results. ACK is transport evidence; model scores are not measured accuracy.',
            style: TextStyle(fontSize: 12, color: muted),
          ),
        ]),
      ]),
    ]);
  }

  Widget _metric(String name, dynamic value) =>
      Text('$name ${value ?? '—'}', style: const TextStyle(fontSize: 13));
  String _flag(dynamic value) => value == null
      ? '—'
      : value == true
      ? 'yes'
      : 'no';
  Widget _json(Map<String, dynamic> value) => SelectableText(
    value.isEmpty
        ? 'Not available'
        : const JsonEncoder.withIndent('  ').convert(value),
    style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
  );
  Widget _pcReport(String title, Map<String, dynamic> report) => _card([
    _label(title),
    _space(8),
    SelectableText(
      '${report['run_id']}\n${report['extractor_profile'] ?? 'Profile unavailable'}',
      style: const TextStyle(fontSize: 12, color: muted),
    ),
    Text(
      'Replay ${report['replay_status']} · ${report['emitted_frames'] ?? '—'} frames',
    ),
    if (report['artifacts'] is List)
      ...(report['artifacts'] as List).map((raw) => _artifact(jsonMap(raw))),
    _detail('Run details', [_json(report)]),
  ]);
  String _artifactUrl(dynamic value) =>
      Uri.parse('${c.pcEndpoint}/').resolve(value?.toString() ?? '').toString();
  Widget _artifact(Map<String, dynamic> artifact) =>
      _detail('${artifact['name']} · ${artifact['bytes']} B', [
        SelectableText(
          _artifactUrl(artifact['url']),
          style: const TextStyle(color: blue, fontSize: 12),
        ),
        SelectableText(
          'SHA-256 ${artifact['sha256']}',
          style: const TextStyle(fontSize: 11, color: muted),
        ),
        TextButton.icon(
          onPressed: () => Clipboard.setData(
            ClipboardData(text: _artifactUrl(artifact['url'])),
          ),
          icon: const Icon(Icons.copy, size: 16),
          label: const Text('Copy URL'),
        ),
      ]);

  Widget _settings() => _page('settings-page', [
    _card([
      _label('Connection'),
      _space(12),
      TextField(
        controller: pc,
        enabled: !c.locked,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'PC video URL'),
        onChanged: (value) => c.pcEndpoint = value,
      ),
      _space(12),
      TextField(
        controller: ws,
        enabled: !c.locked,
        autocorrect: false,
        decoration: const InputDecoration(labelText: 'WebSocket URL'),
        onChanged: (value) => c.endpoint = value,
      ),
      _space(8),
      OutlinedButton.icon(
        onPressed: c.locked ? null : c.inspect,
        icon: const Icon(Icons.radar),
        label: Text(
          c.mode == InputMode.video ? 'Inspect PC' : 'Inspect stream',
        ),
      ),
      _detail('USB connection', [
        const Text(
          'adb reverse tcp:18081 tcp:18081\nadb reverse tcp:18082 tcp:18082\nFor Wi-Fi, use your PC address.',
          style: TextStyle(fontSize: 12, color: muted),
        ),
      ]),
    ]),
    _space(),
    _card([
      _label('Input settings'),
      _space(8),
      Text('Target ${c.targetFps} FPS'),
      Slider(
        value: c.targetFps.toDouble(),
        min: 1,
        max: 30,
        divisions: 29,
        label: '${c.targetFps}',
        onChanged: c.locked
            ? null
            : (value) {
                c.targetFps = value.round();
                c.changed();
              },
      ),
      DropdownButtonFormField<int>(
        initialValue: c.rotation,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Video rotation'),
        items: [0, 90, 180, 270]
            .map(
              (value) => DropdownMenuItem(
                value: value,
                child: Text('$value° clockwise'),
              ),
            )
            .toList(),
        onChanged: c.locked
            ? null
            : (value) {
                c.rotation = value!;
                c.changed();
              },
      ),
      _space(8),
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('Mirrored video'),
        value: c.inputMirrored,
        onChanged: c.locked
            ? null
            : (value) {
                c.inputMirrored = value;
                c.changed();
              },
      ),
      _space(8),
      DropdownButtonFormField<String>(
        initialValue: c.timestampMode,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Video clock'),
        items: const [
          DropdownMenuItem(value: 'pos-msec', child: Text('Source time')),
          DropdownMenuItem(
            value: 'frame-index',
            child: Text('Frame index / FPS'),
          ),
        ],
        onChanged: c.locked
            ? null
            : (value) {
                c.timestampMode = value!;
                c.changed();
              },
      ),
      _detail('Extraction details', [
        const Text(
          'Rotation, mirror correction and video clock apply to PC uploads. Live capture records its own orientation and monotonic clock. Target FPS is a sampling setting, not measured throughput.',
          style: TextStyle(color: muted, fontSize: 12),
        ),
      ]),
    ]),
  ]);
}
