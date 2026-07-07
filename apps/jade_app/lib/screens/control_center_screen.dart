import 'package:flutter/material.dart';
import '../models/jade_settings.dart';
import '../services/api_service.dart';

class ControlCenterScreen extends StatefulWidget {
  final JadeSettings settings;

  const ControlCenterScreen({super.key, required this.settings});

  @override
  State<ControlCenterScreen> createState() => _ControlCenterScreenState();
}

class _ControlCenterScreenState extends State<ControlCenterScreen> {
  final api = ApiService();
  bool loading = true;
  String error = '';
  Map<String, dynamic> summary = {};

  @override
  void initState() {
    super.initState();
    loadSummary();
  }

  Future<void> loadSummary() async {
    setState(() {
      loading = true;
      error = '';
    });
    try {
      final result = await api.controlCenterSummary(widget.settings);
      if (!mounted) return;
      setState(() => summary = result);
    } catch (e) {
      if (!mounted) return;
      setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  List<String> sectionLines(Object? value) {
    if (value is List) return value.map((item) => item.toString()).toList();
    if (value is String) return [value];
    if (value == null) return [];
    return [value.toString()];
  }

  Widget buildSection(String title, Object? value, IconData icon) {
    final lines = sectionLines(value);
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final line in lines)
              Padding(
                padding: const EdgeInsets.only(bottom: 5),
                child: Text(line),
              ),
          ],
        ),
      ),
    );
  }

  IconData iconFor(String title) {
    switch (title) {
      case 'Overall status':
        return Icons.monitor_heart_outlined;
      case 'What is ready':
        return Icons.check_circle_outline;
      case 'What needs attention':
        return Icons.report_problem_outlined;
      case 'Pending approvals':
        return Icons.approval_outlined;
      case 'Active jobs':
        return Icons.work_outline;
      case 'Integrations':
        return Icons.extension_outlined;
      case 'Storage':
        return Icons.folder_outlined;
      case 'Next suggested actions':
        return Icons.playlist_add_check_outlined;
      default:
        return Icons.info_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final rawSections = summary['sections'];
    final sections = rawSections is Map ? rawSections : const {};

    return Scaffold(
      appBar: AppBar(
        title: const Text('Control Center'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: loading ? null : loadSummary,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: loadSummary,
        child: ListView(
          padding: const EdgeInsets.all(12),
          children: [
            if (loading)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (error.isNotEmpty)
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Text(error),
                ),
              ),
            if (!loading && error.isEmpty)
              for (final entry in sections.entries)
                buildSection(
                  entry.key.toString(),
                  entry.value,
                  iconFor(entry.key.toString()),
                ),
          ],
        ),
      ),
    );
  }
}
