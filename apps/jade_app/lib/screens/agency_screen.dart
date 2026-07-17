import 'package:flutter/material.dart';
import '../models/jade_settings.dart';
import '../services/api_service.dart';

class AgencyScreen extends StatefulWidget {
  const AgencyScreen({super.key, required this.settings, this.catalogOverride});
  final JadeSettings settings;
  final List<Map<String, dynamic>>? catalogOverride;

  @override
  State<AgencyScreen> createState() => _AgencyScreenState();
}

class _AgencyScreenState extends State<AgencyScreen> {
  final search = TextEditingController();
  final api = ApiService();
  List<Map<String, dynamic>> agents = [];
  bool loading = true;
  bool teamOnly = false;

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  Future<void> load() async {
    try {
      final values =
          widget.catalogOverride ?? await api.agencyCatalog(widget.settings);
      if (mounted) {
        setState(() {
          agents = values;
          loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final query = search.text.toLowerCase();
    final shown = agents.where((agent) {
      if (teamOnly && agent['installed'] != true) return false;
      final value =
          '${agent['agent']?['name']} ${agent['agent']?['publisher']} ${agent['category']} ${agent['tags']}'
              .toLowerCase();
      return value.contains(query);
    }).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('The Agency')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(
                      value: false,
                      label: Text('Discover'),
                      icon: Icon(Icons.explore_outlined),
                    ),
                    ButtonSegment(
                      value: true,
                      label: Text('Your Team'),
                      icon: Icon(Icons.groups_outlined),
                    ),
                  ],
                  selected: {teamOnly},
                  onSelectionChanged: (value) =>
                      setState(() => teamOnly = value.first),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: search,
                  onChanged: (_) => setState(() {}),
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    hintText: 'Search agents',
                  ),
                ),
              ],
            ),
          ),
          if (loading) const LinearProgressIndicator(),
          Expanded(
            child: shown.isEmpty && !loading
                ? Center(
                    child: Text(
                      teamOnly ? 'Your team is empty.' : 'No agents found.',
                    ),
                  )
                : ListView.builder(
                    itemCount: shown.length,
                    itemBuilder: (_, index) => _AgentCard(
                      agent: shown[index],
                      settings: widget.settings,
                      onChanged: load,
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _AgentCard extends StatelessWidget {
  const _AgentCard({
    required this.agent,
    required this.settings,
    required this.onChanged,
  });
  final Map<String, dynamic> agent;
  final JadeSettings settings;
  final Future<void> Function() onChanged;

  @override
  Widget build(BuildContext context) {
    final metadata = Map<String, dynamic>.from(agent['agent'] as Map);
    return Card(
      margin: const EdgeInsets.fromLTRB(16, 4, 16, 10),
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.smart_toy_outlined)),
        title: Text(metadata['name']?.toString() ?? 'Agent'),
        subtitle: Text(
          '${metadata['publisher']} • v${metadata['version']} • ${agent['category']}\n${metadata['description']}',
        ),
        isThreeLine: true,
        trailing: Chip(label: Text(_statusLabel(agent['status']?.toString()))),
        onTap: () async {
          await Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) =>
                  AgentManagementScreen(agent: agent, settings: settings),
            ),
          );
          await onChanged();
        },
      ),
    );
  }

  String _statusLabel(String? status) => switch (status) {
    'active' => 'On Duty',
    'off_duty' => 'Off Duty',
    'degraded' => 'Missing setup',
    _ => 'Available',
  };
}

class AgentManagementScreen extends StatefulWidget {
  const AgentManagementScreen({
    super.key,
    required this.agent,
    required this.settings,
  });
  final Map<String, dynamic> agent;
  final JadeSettings settings;

  @override
  State<AgentManagementScreen> createState() => _AgentManagementScreenState();
}

class _AgentManagementScreenState extends State<AgentManagementScreen> {
  final api = ApiService();
  late Map<String, dynamic> agent = widget.agent;

  @override
  void initState() {
    super.initState();
    loadDetails();
  }

  Future<void> loadDetails() async {
    if (widget.settings.apiKey.isEmpty) return;
    final id = (agent['agent'] as Map)['agent_id'].toString();
    try {
      final details = await api.agencyAgent(widget.settings, id);
      if (mounted) setState(() => agent = details);
    } catch (_) {}
  }

  Future<void> hire() async {
    final approved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Hire this agent?'),
        content: const Text(
          'Review its Permissions and Secrets before placing it On Duty.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirm Hire'),
          ),
        ],
      ),
    );
    if (approved != true) return;
    final id = (agent['agent'] as Map)['agent_id'].toString();
    await api.agencyAction(widget.settings, id, 'hire');
    await loadDetails();
  }

  @override
  Widget build(BuildContext context) {
    final metadata = Map<String, dynamic>.from(agent['agent'] as Map);
    return DefaultTabController(
      length: 5,
      child: Scaffold(
        appBar: AppBar(
          title: Text(metadata['name'].toString()),
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: 'Overview'),
              Tab(text: 'Configuration'),
              Tab(text: 'Permissions'),
              Tab(text: 'Secrets'),
              Tab(text: 'Activity'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _section(
              '${metadata['description']}\n\nPublisher: ${metadata['publisher']}\nVersion: ${metadata['version']}\nCategory: ${agent['category']}',
            ),
            ManifestConfigurationView(
              fields: List<Map<String, dynamic>>.from(
                agent['configuration'] ?? const [],
              ),
            ),
            _section(
              'Required and optional permissions are shown here before explicit approval.',
            ),
            _section(
              'Select or create a secret handle. Stored values are never displayed.',
            ),
            _section(
              'Hire, setup, On Duty, Off Duty, and release events appear here.',
            ),
          ],
        ),
        floatingActionButton: agent['installed'] == true
            ? null
            : FloatingActionButton.extended(
                onPressed: widget.settings.apiKey.isEmpty ? null : hire,
                icon: const Icon(Icons.handshake_outlined),
                label: const Text('Hire'),
              ),
      ),
    );
  }

  Widget _section(String text) =>
      ListView(padding: const EdgeInsets.all(20), children: [Text(text)]);
}

class ManifestConfigurationView extends StatelessWidget {
  const ManifestConfigurationView({super.key, required this.fields});
  final List<Map<String, dynamic>> fields;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(20),
    children: fields.map((field) {
      final label = field['label']?.toString() ?? field['name'].toString();
      switch (field['type']) {
        case 'boolean':
          return SwitchListTile(
            title: Text(label),
            value: field['default'] == true,
            onChanged: (_) {},
          );
        case 'enum':
          return DropdownButtonFormField<String>(
            decoration: InputDecoration(labelText: label),
            initialValue: field['default']?.toString(),
            items: (field['choices'] as List)
                .map(
                  (value) => DropdownMenuItem(
                    value: value.toString(),
                    child: Text(value.toString()),
                  ),
                )
                .toList(),
            onChanged: (_) {},
          );
        default:
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: TextFormField(
              initialValue: field['default']?.toString(),
              keyboardType: field['type'] == 'integer'
                  ? TextInputType.number
                  : TextInputType.text,
              decoration: InputDecoration(
                labelText: label,
                helperText: field['type'] == 'url' ? 'HTTPS URL' : null,
              ),
            ),
          );
      }
    }).toList(),
  );
}
