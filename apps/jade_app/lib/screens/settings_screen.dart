import 'package:flutter/material.dart';
import '../models/jade_settings.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';

class SettingsScreen extends StatefulWidget {
  final JadeSettings settings;

  const SettingsScreen({super.key, required this.settings});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final name = TextEditingController(text: widget.settings.assistantName);
  late final base = TextEditingController(text: widget.settings.apiBase);
  late final key = TextEditingController(text: widget.settings.apiKey);

  late bool useAi = widget.settings.useAi;
  late bool voiceReplies = widget.settings.voiceReplies;

  @override
  void dispose() {
    name.dispose();
    base.dispose();
    key.dispose();
    super.dispose();
  }

  Future<void> save() async {
    final updated = JadeSettings(
      assistantName: name.text.trim().isEmpty ? 'Jade' : name.text.trim(),
      apiBase: base.text.trim(),
      apiKey: key.text.trim(),
      useAi: useAi,
      voiceReplies: voiceReplies,
    );

    await SettingsService().save(updated);

    if (!mounted) return;
    Navigator.pop(context, updated);
  }

  Future<void> testConnection() async {
    final testSettings = JadeSettings(
      apiBase: base.text.trim(),
      apiKey: key.text.trim(),
      assistantName: name.text.trim(),
      useAi: useAi,
      voiceReplies: voiceReplies,
    );

    try {
      final res = await ApiService().health(testSettings);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            res['statusCode'] == 200
                ? 'JamesOS is online.'
                : 'Health failed: ${res['statusCode']}',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Connection failed: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        actions: [TextButton(onPressed: save, child: const Text('Save'))],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: name,
            decoration: const InputDecoration(
              labelText: 'Assistant name',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: base,
            decoration: const InputDecoration(
              labelText: 'JamesOS API URL',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: key,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'API key',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          SwitchListTile(
            title: const Text('Use AI'),
            subtitle: const Text('Turn off for faster tool-only testing.'),
            value: useAi,
            onChanged: (v) => setState(() => useAi = v),
          ),
          SwitchListTile(
            title: const Text('Voice replies'),
            subtitle: const Text('Prepared for text-to-speech replies.'),
            value: voiceReplies,
            onChanged: (v) => setState(() => voiceReplies = v),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: testConnection,
            icon: const Icon(Icons.wifi_tethering),
            label: const Text('Test connection'),
          ),
        ],
      ),
    );
  }
}
