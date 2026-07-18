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
  late bool connectionLocked = widget.settings.connectionLocked;

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
      apiBase: connectionLocked ? widget.settings.apiBase : base.text.trim(),
      apiKey: connectionLocked ? widget.settings.apiKey : key.text.trim(),
      useAi: useAi,
      voiceReplies: voiceReplies,
      connectionLocked: connectionLocked,
    );

    await SettingsService().save(updated);

    if (!mounted) return;
    Navigator.pop(context, updated);
  }

  Future<void> confirmUnlockConnection() async {
    final unlocked = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Unlock connection settings?'),
        content: const Text(
          'This allows editing the JamesOS API URL and API key. Keep this locked unless you need to change servers or replace the key.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.pop(dialogContext, true),
            icon: const Icon(Icons.lock_open),
            label: const Text('Unlock'),
          ),
        ],
      ),
    );

    if (unlocked == true) {
      setState(() => connectionLocked = false);
    }
  }

  Future<void> testConnection() async {
    final testSettings = JadeSettings(
      apiBase: base.text.trim(),
      apiKey: key.text.trim(),
      assistantName: name.text.trim(),
      useAi: useAi,
      voiceReplies: voiceReplies,
      connectionLocked: connectionLocked,
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
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Connection failed: $e')));
    }
  }

  Widget sectionTitle(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
      ),
    );
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
          sectionTitle('Assistant'),
          TextField(
            controller: name,
            decoration: const InputDecoration(
              labelText: 'Assistant name',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 18),
          sectionTitle('JamesOS Connection'),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Lock API URL and key'),
            subtitle: const Text(
              'Prevents accidentally clearing the server address or key.',
            ),
            value: connectionLocked,
            secondary: Icon(connectionLocked ? Icons.lock : Icons.lock_open),
            onChanged: (v) {
              if (v) {
                setState(() => connectionLocked = true);
              } else {
                confirmUnlockConnection();
              }
            },
          ),
          TextField(
            controller: base,
            enabled: !connectionLocked,
            decoration: InputDecoration(
              labelText: 'JamesOS API URL',
              helperText: connectionLocked
                  ? 'Locked to prevent accidental changes.'
                  : null,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: key,
            enabled: !connectionLocked,
            obscureText: true,
            decoration: InputDecoration(
              labelText: 'API key',
              helperText: connectionLocked
                  ? 'Locked to prevent accidental changes.'
                  : null,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: testConnection,
            icon: const Icon(Icons.wifi_tethering),
            label: const Text('Test connection'),
          ),
          const SizedBox(height: 18),
          sectionTitle('Behavior'),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Use AI'),
            subtitle: const Text('Turn off for faster tool-only testing.'),
            value: useAi,
            onChanged: (v) => setState(() => useAi = v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Voice replies'),
            subtitle: const Text('Prepared for text-to-speech replies.'),
            value: voiceReplies,
            onChanged: (v) => setState(() => voiceReplies = v),
          ),
          const SizedBox(height: 18),
          sectionTitle('Notifications'),
          Card(
            child: ListTile(
              leading: const Icon(Icons.notifications_outlined),
              title: const Text('Push notifications'),
              subtitle: const Text(
                'Planned. Jade will eventually send proactive alerts from JamesOS signals.',
              ),
              trailing: const Chip(label: Text('Soon')),
              onTap: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text(
                      'Push notifications are planned for the next mobile phase.',
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
