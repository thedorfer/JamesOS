import 'package:flutter/material.dart';
import '../models/app_mode.dart';
import '../models/chat_message.dart';
import '../models/jade_settings.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/message_input.dart';
import '../widgets/status_chip.dart';
import 'settings_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final input = TextEditingController();
  final scroll = ScrollController();
  final api = ApiService();

  JadeSettings settings = JadeSettings();
  bool loading = false;
  bool serverOnline = false;
  AppMode selectedMode = AppMode.personal;

  final messages = <ChatMessage>[
    ChatMessage(role: 'jade', text: 'Hi James. Jade is ready.'),
  ];

  @override
  void initState() {
    super.initState();
    loadSettings();
  }

  @override
  void dispose() {
    input.dispose();
    scroll.dispose();
    super.dispose();
  }

  Future<void> loadSettings() async {
    final loaded = await SettingsService().load();
    if (!mounted) return;
    setState(() => settings = loaded);
    await refreshStatus();
  }

  Future<void> refreshStatus() async {
    try {
      final res = await api.health(settings);
      if (!mounted) return;
      setState(() => serverOnline = res['statusCode'] == 200);
    } catch (_) {
      if (!mounted) return;
      setState(() => serverOnline = false);
    }
  }

  Future<void> openSettings() async {
    final updated = await Navigator.push<JadeSettings>(
      context,
      MaterialPageRoute(builder: (_) => SettingsScreen(settings: settings)),
    );

    if (updated != null) {
      setState(() => settings = updated);
      await refreshStatus();
    }
  }

  String requestForMode(String question) {
    return '''Mode: ${selectedMode.label}
${selectedMode.directive}

James asked:
$question''';
  }

  Future<void> askJade({String? overrideQuestion, bool applyMode = true}) async {
    final question = (overrideQuestion ?? input.text).trim();
    if (question.isEmpty || loading) return;

    final requestQuestion = applyMode ? requestForMode(question) : question;

    setState(() {
      messages.add(ChatMessage(role: 'user', text: question));
      messages.add(ChatMessage(role: 'jade', text: 'Thinking...'));
      loading = true;
      input.clear();
    });

    scrollToBottom();

    try {
      final response = await api.ask(settings, requestQuestion);
      setState(() => messages[messages.length - 1] = response);
      await refreshStatus();
    } catch (e) {
      setState(() {
        serverOnline = false;
        messages[messages.length - 1] = ChatMessage(
          role: 'jade',
          text: 'I could not reach JamesOS.\n\n`$e`',
          confidenceLabel: '🔴 Low',
          action: 'connection_error',
        );
      });
    } finally {
      setState(() => loading = false);
      Future.delayed(const Duration(milliseconds: 100), scrollToBottom);
    }
  }

  void scrollToBottom() {
    if (!scroll.hasClients) return;
    scroll.animateTo(
      scroll.position.maxScrollExtent,
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeOut,
    );
  }

  void clearChat() {
    setState(() {
      messages.clear();
      messages.add(ChatMessage(role: 'jade', text: 'Fresh chat. I am ready.'));
    });
  }

  void runMode(AppMode mode) {
    setState(() => selectedMode = mode);
    askJade(overrideQuestion: mode.briefingPrompt, applyMode: false);
  }

  IconData modeIcon(AppMode mode) => switch (mode) {
        AppMode.work => Icons.work_outline,
        AppMode.gcu => Icons.school_outlined,
        AppMode.family => Icons.home_outlined,
        AppMode.jamesOS => Icons.memory_outlined,
        AppMode.personal => Icons.auto_awesome_outlined,
      };

  Widget buildStatusRow() {
    return Row(
      children: [
        StatusChip(online: serverOnline, onTap: refreshStatus),
        const Spacer(),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: Colors.tealAccent.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.22)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(modeIcon(selectedMode), size: 15, color: Colors.tealAccent.shade100),
              const SizedBox(width: 6),
              Text(
                '${selectedMode.shortLabel} mode',
                style: TextStyle(
                  color: Colors.tealAccent.shade100,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget modeChip(AppMode mode) {
    final selected = selectedMode == mode;
    return ChoiceChip(
      selected: selected,
      avatar: Icon(modeIcon(mode), size: 18),
      label: Text(mode.label),
      onSelected: (_) => runMode(mode),
      selectedColor: Colors.tealAccent.withValues(alpha: 0.22),
      backgroundColor: Colors.white.withValues(alpha: 0.045),
      side: BorderSide(
        color: selected
            ? Colors.tealAccent.withValues(alpha: 0.48)
            : Colors.white.withValues(alpha: 0.12),
      ),
    );
  }

  Widget buildDashboardCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.teal.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Good afternoon, James',
            style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 10),
          buildStatusRow(),
          const SizedBox(height: 12),
          Text(
            'Currently in ${selectedMode.label} mode. Jade will bias answers toward what matters there.',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: AppMode.values.map(modeChip).toList(),
          ),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: loading
                ? null
                : () => askJade(
                      overrideQuestion: selectedMode.briefingPrompt,
                      applyMode: false,
                    ),
            icon: const Icon(Icons.flash_on),
            label: Text('Brief me in ${selectedMode.label}'),
          ),
        ],
      ),
    );
  }

  Widget buildTopBarTitle() {
    return Row(
      children: [
        Text(settings.assistantName),
        const SizedBox(width: 10),
        Flexible(
          child: StatusChip(
            online: serverOnline,
            label: 'OS',
            onTap: refreshStatus,
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final paired = settings.apiKey.isNotEmpty;

    return Scaffold(
      appBar: AppBar(
        title: buildTopBarTitle(),
        actions: [
          IconButton(onPressed: clearChat, icon: const Icon(Icons.delete_outline)),
          IconButton(onPressed: openSettings, icon: const Icon(Icons.settings)),
        ],
      ),
      body: Column(
        children: [
          if (!paired)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              color: Colors.amber.withValues(alpha: 0.18),
              child: const Text('Add your JamesOS API key in Settings.'),
            ),
          Expanded(
            child: ListView.builder(
              controller: scroll,
              padding: const EdgeInsets.all(16),
              itemCount: messages.length + 1,
              itemBuilder: (_, i) {
                if (i == 0) return buildDashboardCard();
                return ChatBubble(message: messages[i - 1]);
              },
            ),
          ),
          MessageInput(controller: input, loading: loading, onSend: askJade),
        ],
      ),
    );
  }
}
